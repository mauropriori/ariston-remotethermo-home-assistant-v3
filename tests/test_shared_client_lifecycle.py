"""Tests for shared Ariston account client lifecycle."""

import asyncio
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from ariston import Ariston, DeviceAttribute
from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_USERNAME
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.util.unit_system import METRIC_SYSTEM

from custom_components.ariston import (
    _async_release_shared_client,
    _SharedAristonClient,
    async_setup_entry,
)
from custom_components.ariston.const import DOMAIN, SHARED_CLIENTS


def _entry(entry_id: str):
    return SimpleNamespace(
        entry_id=entry_id,
        unique_id=f"gateway-{entry_id}",
        data={
            CONF_USERNAME: "owner@example.test",
            CONF_PASSWORD: "secret",
            CONF_DEVICE: {
                DeviceAttribute.GW: f"gateway-{entry_id}",
                DeviceAttribute.NAME: entry_id,
            },
        },
        options={},
    )


def _hass():
    return SimpleNamespace(
        data={},
        config=SimpleNamespace(units=METRIC_SYSTEM),
    )


class SharedClientLifecycleTests(TestCase):
    """Verify account clients live exactly as long as their config entries."""

    def test_client_is_removed_only_after_last_entry_unloads(self):
        async def run():
            shared_client = _SharedAristonClient()
            shared_client.entry_ids.update({"nimbus-entry", "lydos-entry"})
            domain_data = {SHARED_CLIENTS: {"account-key": shared_client}}

            await _async_release_shared_client(
                domain_data, "account-key", "nimbus-entry"
            )
            after_first = domain_data[SHARED_CLIENTS].get("account-key")

            await _async_release_shared_client(
                domain_data, "account-key", "lydos-entry"
            )
            after_second = domain_data[SHARED_CLIENTS].get("account-key")
            return shared_client, after_first, after_second

        shared_client, after_first, after_second = asyncio.run(run())
        self.assertIs(after_first, shared_client)
        self.assertIsNone(after_second)

    def test_cancelled_login_releases_shared_client_reference(self):
        async def run():
            login_started = asyncio.Event()
            never_finish = asyncio.Event()
            entry = _entry("lydos-entry")
            hass = _hass()

            async def blocked_connect(*args, **kwargs):
                login_started.set()
                await never_finish.wait()

            with patch.object(Ariston, "async_connect", blocked_connect):
                setup_task = asyncio.create_task(async_setup_entry(hass, entry))
                await login_started.wait()
                setup_task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await setup_task

            return hass, entry

        hass, entry = asyncio.run(run())
        self.assertEqual(hass.data[DOMAIN][SHARED_CLIENTS], {})
        self.assertNotIn(entry.unique_id, hass.data[DOMAIN])

    def test_cancelled_first_refresh_cleans_runtime_and_client(self):
        async def run():
            refresh_started = asyncio.Event()
            never_finish = asyncio.Event()
            entry = _entry("nimbus-entry")
            hass = _hass()
            device = MagicMock()
            device.async_get_features = AsyncMock(return_value=None)

            class _BlockedCoordinator:
                def __init__(self, *args, **kwargs):
                    pass

                async def async_config_entry_first_refresh(self):
                    refresh_started.set()
                    await never_finish.wait()

            with patch.object(
                Ariston, "async_connect", new=AsyncMock(return_value=True)
            ), patch.object(
                Ariston, "async_hello", new=AsyncMock(return_value=device)
            ), patch(
                "custom_components.ariston.DeviceDataUpdateCoordinator",
                _BlockedCoordinator,
            ):
                setup_task = asyncio.create_task(async_setup_entry(hass, entry))
                await refresh_started.wait()
                setup_task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await setup_task

            return hass, entry

        hass, entry = asyncio.run(run())
        self.assertEqual(hass.data[DOMAIN][SHARED_CLIENTS], {})
        self.assertNotIn(entry.unique_id, hass.data[DOMAIN])

    def test_cancellation_while_error_cleanup_waits_for_lock(self):
        async def run():
            refresh_started = asyncio.Event()
            fail_refresh = asyncio.Event()
            entry = _entry("cancelled-error-entry")
            hass = _hass()
            device = MagicMock()
            device.async_get_features = AsyncMock(return_value=None)

            class _FailingCoordinator:
                def __init__(self, *args, **kwargs):
                    pass

                async def async_config_entry_first_refresh(self):
                    refresh_started.set()
                    await fail_refresh.wait()
                    raise ConfigEntryNotReady("simulated state failure")

            with patch.object(
                Ariston, "async_connect", new=AsyncMock(return_value=True)
            ), patch.object(
                Ariston, "async_hello", new=AsyncMock(return_value=device)
            ), patch(
                "custom_components.ariston.DeviceDataUpdateCoordinator",
                _FailingCoordinator,
            ):
                setup_task = asyncio.create_task(async_setup_entry(hass, entry))
                await refresh_started.wait()
                shared_client = next(
                    iter(hass.data[DOMAIN][SHARED_CLIENTS].values())
                )
                await shared_client.lock.acquire()
                try:
                    fail_refresh.set()
                    await asyncio.sleep(0)
                    setup_task.cancel()
                    await asyncio.sleep(0)
                    self.assertFalse(setup_task.done())
                finally:
                    shared_client.lock.release()

                with self.assertRaises(asyncio.CancelledError):
                    await setup_task

            return hass, entry

        hass, entry = asyncio.run(run())
        self.assertEqual(hass.data[DOMAIN][SHARED_CLIENTS], {})
        self.assertNotIn(entry.unique_id, hass.data[DOMAIN])
