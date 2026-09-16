"""Coordinator class for Ariston module."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ariston import ConnectionException, RateLimitException
from ariston.base_device import AristonBaseDevice

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEVICE_WRITE_PROPS: dict[str, tuple[str, str]] = {
    "temperature": (
        "water_heater_target_temperature",
        "async_set_water_heater_temperature",
    ),
    "operation_mode": (
        "water_heater_current_mode_text",
        "async_set_water_heater_operation_mode",
    ),
}


@dataclass
class PendingWrite:
    """A write that must be confirmed by a later regular state poll."""

    prop: str
    expected: Any
    retries: int = 0
    max_retries: int = 2


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

    async def _async_update_and_verify(self):
        """Poll once, normalize cloud failures, then verify pending writes."""
        try:
            data = await self._async_device_update_state()
        except RateLimitException as error:
            raise UpdateFailed(
                f"Ariston cloud rate limited; retry after {error.retry_after} seconds"
            ) from error
        except (ConnectionException, ClientError, TimeoutError) as error:
            raise UpdateFailed(f"Ariston cloud request failed: {error}") from error

        await self._async_check_pending_writes()
        return data

    async def _async_check_pending_writes(self) -> None:
        """Retry a rejected water-heater write on later regular polls only."""
        for prop, pending in list(self.pending_writes.items()):
            property_names = DEVICE_WRITE_PROPS.get(prop)
            if property_names is None:
                del self.pending_writes[prop]
                continue

            read_attribute, write_method = property_names
            actual = getattr(self.device, read_attribute, None)
            if actual == pending.expected:
                del self.pending_writes[prop]
                continue

            if pending.retries >= pending.max_retries:
                _LOGGER.warning(
                    "Ariston write verification for %s gave up after %s retries "
                    "(actual %s, expected %s)",
                    prop,
                    pending.max_retries,
                    actual,
                    pending.expected,
                )
                del self.pending_writes[prop]
                continue

            pending.retries += 1
            try:
                await getattr(self.device, write_method)(pending.expected)
            except Exception as error:  # noqa: BLE001 - retry must not stop polling
                _LOGGER.warning(
                    "Retrying Ariston write for %s failed; it will be tried on "
                    "the next regular poll: %s",
                    prop,
                    error,
                )
