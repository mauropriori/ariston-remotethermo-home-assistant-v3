"""Support for Ariston sensors."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ariston import SystemType
from ariston.const import ConsumptionType, DeviceFeatures, WheType

from .const import (
    ARISTON_SENSOR_TYPES,
    DOMAIN,
    ENERGY_COORDINATOR,
    AristonSensorEntityDescription,
)
from .coordinator import DeviceDataUpdateCoordinator
from .entity import AristonEntity

_LOGGER = logging.getLogger(__name__)

_LYDOS_HYBRID_ENERGY_FEATURES = {
    ConsumptionType.DOMESTIC_HOT_WATER_HEATING_PUMP_ELECTRICITY.name,
    ConsumptionType.DOMESTIC_HOT_WATER_RESISTOR_ELECTRICITY.name,
}


def _is_known_lydos_hybrid_energy_sensor(
    coordinator: DeviceDataUpdateCoordinator,
    description: AristonSensorEntityDescription,
) -> bool:
    """Keep known Lydos energy sensors subscribed after an initial HTTP 500."""
    required_features = set(description.device_features or [])
    return (
        description.coordinator == ENERGY_COORDINATOR
        and coordinator.device.system_type == SystemType.VELIS
        and coordinator.device.whe_type == WheType.LydosHybrid
        and DeviceFeatures.HAS_METERING in required_features
        and bool(required_features & _LYDOS_HYBRID_ENERGY_FEATURES)
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston sensors from config entry."""
    ariston_sensors: list[AristonSensor] = []

    for description in ARISTON_SENSOR_TYPES:
        coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
            description.coordinator
        ]
        if (
            coordinator
            and coordinator.device
            and (
                coordinator.device.are_device_features_available(
                    description.device_features,
                    description.system_types,
                    description.whe_types,
                )
                or _is_known_lydos_hybrid_energy_sensor(coordinator, description)
            )
        ):
            ariston_sensors.append(
                AristonSensor(
                    coordinator,
                    description,
                )
            )

    async_add_entities(ariston_sensors)


class AristonSensor(AristonEntity, SensorEntity):
    """Base class for specific ariston sensors."""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonSensorEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description)

    @property
    def native_value(self):
        """Return value of sensor."""
        return self.entity_description.get_native_value(self)

    @property
    def native_unit_of_measurement(self):
        """Return the nateive unit of measurement."""
        if self.entity_description.get_native_unit_of_measurement is not None:
            return self.entity_description.get_native_unit_of_measurement(self)

        if self.entity_description.native_unit_of_measurement is not None:
            return self.entity_description.native_unit_of_measurement

        return None

    @property
    def last_reset(self) -> datetime | None:
        """Return the time when the sensor was last reset, if any."""
        if self.entity_description.get_last_reset is not None:
            return self.entity_description.get_last_reset(self)

        return None
