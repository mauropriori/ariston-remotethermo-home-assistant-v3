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
    coordinator._verify_pending_writes = False
    coordinator.async_update_listeners = MagicMock()
    return coordinator


class CoordinatorWriteTests(TestCase):
    """Verify serialized writes and passive cloud confirmation."""

    def test_failed_confirmation_never_replays_a_stale_command(self):
        async def run():
            class _Device:
                water_heater_target_temperature = 40
                async_set_water_heater_temperature = AsyncMock()

            device = _Device()
            coordinator = _coordinator_for(device)
            coordinator.pending_writes = {
                "temperature": PendingWrite("temperature", 50),
            }

            await coordinator._async_check_pending_writes()
            return coordinator, device

        coordinator, device = asyncio.run(run())
        self.assertNotIn("temperature", coordinator.pending_writes)
        device.async_set_water_heater_temperature.assert_not_awaited()

    def test_only_scheduled_refresh_verifies_pending_writes(self):
        async def run():
            coordinator = _coordinator_for(MagicMock())
            coordinator._async_device_update_state = AsyncMock(return_value=None)
            coordinator._async_check_pending_writes_locked = AsyncMock()

            coordinator._verify_pending_writes = False
            await coordinator._async_update_and_verify()
            manual_calls = (
                coordinator._async_check_pending_writes_locked.await_count
            )

            coordinator._verify_pending_writes = True
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

    def test_failed_new_command_still_discards_older_confirmation(self):
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
            coordinator._verify_pending_writes = True

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

    def test_write_waits_for_manual_refresh_and_uses_the_new_cloud_state(self):
        async def run():
            poll_updated_mode = asyncio.Event()
            finish_poll = asyncio.Event()
            captured_previous_modes = []

            class _Device:
                water_heater_current_mode_text = "GREEN"

                async def async_set_water_heater_operation_mode(self, value):
                    captured_previous_modes.append(
                        self.water_heater_current_mode_text
                    )
                    self.water_heater_current_mode_text = value

            device = _Device()
            coordinator = _coordinator_for(device)
            coordinator._verify_pending_writes = False

            async def update_state():
                device.water_heater_current_mode_text = "IMEMORY"
                poll_updated_mode.set()
                await finish_poll.wait()

            coordinator._async_device_update_state = update_state
            poll_task = asyncio.create_task(coordinator._async_update_and_verify())
            await poll_updated_mode.wait()
            write_task = asyncio.create_task(
                coordinator.async_execute_tracked_write(
                    "operation_mode",
                    "BOOST",
                    device.async_set_water_heater_operation_mode,
                    track_confirmation=False,
                )
            )
            await asyncio.sleep(0)
            self.assertEqual(captured_previous_modes, [])

            finish_poll.set()
            await asyncio.gather(poll_task, write_task)
            return device, captured_previous_modes

        device, captured_previous_modes = asyncio.run(run())

        self.assertEqual(captured_previous_modes, ["IMEMORY"])
        self.assertEqual(device.water_heater_current_mode_text, "BOOST")
