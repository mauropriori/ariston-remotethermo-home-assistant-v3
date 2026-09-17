"""Coordinator class for Ariston module."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from aiohttp import ClientError
from ariston_net_api import ConnectionException, RateLimitException
from ariston_net_api.base_device import AristonBaseDevice
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEVICE_WRITE_PROPS: dict[str, str] = {
    "temperature": "water_heater_target_temperature",
    "operation_mode": "water_heater_current_mode_text",
}


@dataclass
class PendingWrite:
    """A write that must be confirmed by a later regular state poll."""

    prop: str
    expected: Any


class DeviceDataUpdateCoordinator(DataUpdateCoordinator):
    """Manages polling for state changes from the device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: AristonBaseDevice,
        scan_interval_seconds: int,
        coordinator_name: str,
        async_update_state: Callable,
    ) -> None:
        """Initialize the data update coordinator."""
        self._async_device_update_state = async_update_state
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{device.name}-{coordinator_name}",
            update_interval=timedelta(seconds=scan_interval_seconds),
            update_method=self._async_update_and_verify,
        )

        self.device = device
        self.pending_writes: dict[str, PendingWrite] = {}
        self.write_lock = asyncio.Lock()
        self._verify_pending_writes = False

    async def _async_refresh(
        self,
        log_failures: bool = True,
        raise_on_auth_failed: bool = False,
        scheduled: bool = False,
        raise_on_entry_error: bool = False,
    ) -> None:
        """Track whether Home Assistant initiated a scheduled poll."""
        previous_verification_state = self._verify_pending_writes
        self._verify_pending_writes = scheduled
        try:
            await super()._async_refresh(
                log_failures=log_failures,
                raise_on_auth_failed=raise_on_auth_failed,
                scheduled=scheduled,
                raise_on_entry_error=raise_on_entry_error,
            )
        finally:
            self._verify_pending_writes = previous_verification_state

    async def _async_update_and_verify(self):
        """Poll once, normalize cloud failures, then verify pending writes."""
        # Keep every cloud snapshot atomic with respect to optimistic local
        # changes made by user commands. Only scheduled polls consume pending
        # confirmations, but manual refreshes must use the same lock.
        async with self.write_lock:
            data = await self._async_update_device_state()
            if self._verify_pending_writes:
                await self._async_check_pending_writes_locked()
            return data

    async def _async_update_device_state(self):
        """Poll once and normalize cloud failures for Home Assistant."""
        try:
            return await self._async_device_update_state()
        except RateLimitException as error:
            raise UpdateFailed(
                f"Ariston cloud rate limited; retry after {error.retry_after} seconds"
            ) from error
        except (ConnectionException, ClientError, TimeoutError) as error:
            raise UpdateFailed(f"Ariston cloud request failed: {error}") from error

    async def async_execute_tracked_write(
        self,
        prop: str,
        expected: Any,
        write_method: Callable[[Any], Awaitable[None]],
        *,
        track_confirmation: bool = True,
    ) -> None:
        """Serialize a device write with its pending confirmation state."""
        async with self.write_lock:
            # A new user command supersedes any older confirmation even if the
            # cloud response for the new command is lost or reports an error.
            self.pending_writes.pop(prop, None)
            await write_method(expected)
            if track_confirmation:
                self.pending_writes[prop] = PendingWrite(
                    prop=prop,
                    expected=expected,
                )

        # The library updates its local device model after a successful write.
        # Notify every entity backed by this coordinator without another request.
        self.async_update_listeners()

    async def _async_check_pending_writes(self) -> None:
        """Passively verify a water-heater write on a later regular poll."""
        async with self.write_lock:
            await self._async_check_pending_writes_locked()

    async def _async_check_pending_writes_locked(self) -> None:
        """Verify pending writes while the caller owns the device write lock."""
        for prop, pending in list(self.pending_writes.items()):
            # A user command may have replaced or removed this pending write
            # before the lock was acquired. Never replay a stale command.
            if self.pending_writes.get(prop) is not pending:
                continue

            read_attribute = DEVICE_WRITE_PROPS.get(prop)
            if read_attribute is None:
                self.pending_writes.pop(prop, None)
                continue

            actual = getattr(self.device, read_attribute, None)
            self.pending_writes.pop(prop, None)
            if actual == pending.expected:
                continue

            _LOGGER.warning(
                "Ariston write for %s was not confirmed by the next regular "
                "poll (actual %s, expected %s); it will not be retried",
                prop,
                actual,
                pending.expected,
            )
