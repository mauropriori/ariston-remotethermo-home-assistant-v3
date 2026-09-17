"""Tests for Ariston climate mode exposure."""

from unittest import TestCase

from homeassistant.components.climate import HVACMode

from custom_components.ariston.climate import AristonThermostat


class _FakeDevice:
    """Minimal climate device used by the HVAC mode tests."""

    def __init__(self, *, plant_mode_supported: bool, zone_off_supported: bool):
        self.plant_mode_supported = plant_mode_supported
        self._zone_off_supported = zone_off_supported

    def is_zone_mode_options_contains_manual(self, zone: int) -> bool:
        return False

    def is_zone_mode_options_contains_time_program(self, zone: int) -> bool:
        return False

    def is_zone_mode_options_contains_off(self, zone: int) -> bool:
        return self._zone_off_supported


def _entity_for(device: _FakeDevice) -> AristonThermostat:
    entity = AristonThermostat.__new__(AristonThermostat)
    entity.device = device
    entity.zone = 1
    return entity


class ClimateModesTests(TestCase):
    """Verify when Home Assistant's OFF mode is exposed."""

    def test_nimbus_exposes_off_when_zone_does_not_report_it(self):
        entity = _entity_for(
            _FakeDevice(plant_mode_supported=True, zone_off_supported=False)
        )

        self.assertIn(HVACMode.OFF, entity.hvac_modes)

    def test_zone_off_is_kept_for_devices_without_plant_modes(self):
        entity = _entity_for(
            _FakeDevice(plant_mode_supported=False, zone_off_supported=True)
        )

        self.assertIn(HVACMode.OFF, entity.hvac_modes)

    def test_unsupported_off_is_not_advertised(self):
        entity = _entity_for(
            _FakeDevice(plant_mode_supported=False, zone_off_supported=False)
        )

        self.assertNotIn(HVACMode.OFF, entity.hvac_modes)
