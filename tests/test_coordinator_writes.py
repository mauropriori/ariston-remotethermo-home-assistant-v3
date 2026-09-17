"""Tests for serialized Lydos writes and pending confirmations."""

import asyncio
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock

from custom_components.ariston_net.coordinator import (
    DeviceDataUpdateCoordinator,
    PendingWrite,
)


def _coordinator_for(device) -> DeviceDataUpdateCoordinator:
    coordinator = DeviceDataUpdateCoordinator.__new__(DeviceDataUpdateCoordinator)
    coordinator.device = device
    coordinator.pending_writes = {}
    coordinator.write_lock = asyncio.Lock()
    coordinator._retry_pending_writes = False
    coordinator.async_update_listeners = MagicMock()
    return coordinator


class CoordinatorWriteTests(TestCase):
    """Verify that stale retries cannot override a newer user command."""

    def test_boost_waits_for_old_retries_and_remains_the_final_command(self):
        async def run():
            temperature_retry_started = asyncio.Event()
            release_temperature_retry = asyncio.Event()
            mode_calls = []

            class _Device:
                water_heater_target_temperature = 40
                water_heater_current_mode_text = "MANUAL"

                async def async_set_water_heater_temperature(self, value):
                    temperature_retry_started.set()
                    await release_temperature_retry.wait()
                    self.water_heater_target_temperature = value

                async def async_set_water_heater_operation_mode(self, value):
                    mode_calls.append(value)
                    self.water_heater_current_mode_text = value

            device = _Device()
            coordinator = _coordinator_for(device)
            coordinator.pending_writes = {
                "temperature": PendingWrite("temperature", 50),
                "operation_mode": PendingWrite("operation_mode", "GREEN"),
            }

            retry_task = asyncio.create_task(
                coordinator._async_check_pending_writes()
            )
            await temperature_retry_started.wait()
            boost_task = asyncio.create_task(
                coordinator.async_execute_tracked_write(
                    "operation_mode",
                    "BOOST",
                    device.async_set_water_heater_operation_mode,
                    track_confirmation=False,
                )
            )
            await asyncio.sleep(0)
            release_temperature_retry.set()
            await asyncio.gather(retry_task, boost_task)

            return coordinator, device, mode_calls

        coordinator, device, mode_calls = asyncio.run(run())
        self.assertEqual(mode_calls, ["GREEN", "BOOST"])
        self.assertEqual(device.water_heater_current_mode_text, "BOOST")
        self.assertNotIn("operation_mode", coordinator.pending_writes)
        coordinator.async_update_listeners.assert_called_once_with()

    def test_manual_refresh_does_not_consume_pending_retries(self):
        async def run():
            coordinator = _coordinator_for(MagicMock())
            coordinator._async_device_update_state = AsyncMock(return_value=None)
            coordinator._async_check_pending_writes_locked = AsyncMock()

            coordinator._retry_pending_writes = False
            await coordinator._async_update_and_verify()
            manual_calls = (
                coordinator._async_check_pending_writes_locked.await_count
            )

            coordinator._retry_pending_writes = True
            await coordinator._async_update_and_verify()
            scheduled_calls = (
                coordinator._async_check_pending_writes_locked.await_count
            )
            return manual_calls, scheduled_calls

        manual_calls, scheduled_calls = asyncio.run(run())
        self.assertEqual(manual_calls, 0)
        self.assertEqual(scheduled_calls, 1)

    def test_tracked_write_notifies_every_coordinator_listener(self):
        async def run():
            device = MagicMock()
            coordinator = _coordinator_for(device)
            write = AsyncMock()
            await coordinator.async_execute_tracked_write(
                "operation_mode", "GREEN", write
            )
            return coordinator, write

        coordinator, write = asyncio.run(run())
        write.assert_awaited_once_with("GREEN")
        self.assertEqual(
            coordinator.pending_writes["operation_mode"].expected, "GREEN"
        )
        coordinator.async_update_listeners.assert_called_once_with()

    def test_failed_new_command_still_discards_older_pending_retry(self):
        async def run():
            coordinator = _coordinator_for(MagicMock())
            coordinator.pending_writes["operation_mode"] = PendingWrite(
                "operation_mode", "GREEN"
            )
            write = AsyncMock(side_effect=RuntimeError("cloud response lost"))
            with self.assertRaises(RuntimeError):
                await coordinator.async_execute_tracked_write(
                    "operation_mode",
                    "BOOST",
                    write,
                    track_confirmation=False,
                )
            return coordinator

        coordinator = asyncio.run(run())
        self.assertNotIn("operation_mode", coordinator.pending_writes)
        coordinator.async_update_listeners.assert_not_called()

    def test_write_during_poll_is_not_confirmed_from_optimistic_local_state(self):
        async def run():
            poll_received_old_value = asyncio.Event()
            finish_poll = asyncio.Event()

            class _Device:
                water_heater_target_temperature = 40

                async def async_set_water_heater_temperature(self, value):
                    self.water_heater_target_temperature = value

            device = _Device()
            coordinator = _coordinator_for(device)
            coordinator._retry_pending_writes = True

            async def update_state():
                device.water_heater_target_temperature = 40
                poll_received_old_value.set()
                await finish_poll.wait()

            coordinator._async_device_update_state = update_state
            poll_task = asyncio.create_task(coordinator._async_update_and_verify())
            await poll_received_old_value.wait()
            write_task = asyncio.create_task(
                coordinator.async_execute_tracked_write(
                    "temperature",
                    55,
                    device.async_set_water_heater_temperature,
                )
            )
            await asyncio.sleep(0)
            finish_poll.set()
            await asyncio.gather(poll_task, write_task)
            return coordinator

        coordinator = asyncio.run(run())
        self.assertIn("temperature", coordinator.pending_writes)
        self.assertEqual(coordinator.pending_writes["temperature"].expected, 55)
