"""The Ariston integration."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_DEVICE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.util.unit_system import METRIC_SYSTEM

from ariston_net_api import Ariston, DeviceAttribute, SystemType
from ariston_net_api.const import ARISTON_API_URL, ARISTON_USER_AGENT

from .const import (
    API_URL_SETTING,
    API_USER_AGENT,
    BUS_ERRORS_COORDINATOR,
    BUS_ERRORS_SCAN_INTERVAL,
    COORDINATOR,
    DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    DEFAULT_ENABLE_BUS_ERRORS,
    DEFAULT_ENABLE_ENERGY,
    DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    ENABLE_BUS_ERRORS,
    ENABLE_ENERGY,
    ENERGY_COORDINATOR,
    ENERGY_SCAN_INTERVAL,
    MIN_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    MIN_ENERGY_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_SECONDS,
    SHARED_CLIENTS,
)
from .coordinator import DeviceDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
_SHARED_CLIENT_KEY = "shared_client_key"


@dataclass
class _SharedAristonClient:
    """One authenticated client shared by entries using the same account."""

    ariston: Ariston = field(default_factory=Ariston)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    connected: bool = False
    entry_ids: set[str] = field(default_factory=set)


def _client_key(entry: ConfigEntry, api_url: str, user_agent: str) -> str:
    """Build a non-reversible key for sharing one account client."""
    credentials = "\0".join(
        (
            entry.data[CONF_USERNAME].strip().casefold(),
            entry.data[CONF_PASSWORD],
            api_url,
            user_agent,
        )
    )
    return hashlib.sha256(credentials.encode()).hexdigest()


async def _async_release_shared_client(
    domain_data: dict, client_key: str, entry_id: str
) -> None:
    """Release an entry's reference to a shared account client."""
    shared_clients: dict[str, _SharedAristonClient] = domain_data.get(
        SHARED_CLIENTS, {}
    )
    shared_client = shared_clients.get(client_key)
    if shared_client is None:
        return

    async with shared_client.lock:
        shared_client.entry_ids.discard(entry_id)
        if (
            not shared_client.entry_ids
            and shared_clients.get(client_key) is shared_client
        ):
            shared_clients.pop(client_key, None)


async def _async_cleanup_failed_setup(
    domain_data: dict, client_key: str, entry: ConfigEntry
) -> None:
    """Remove runtime state and the client reference for a failed setup."""
    domain_data.pop(entry.unique_id, None)
    await _async_release_shared_client(domain_data, client_key, entry.entry_id)


async def _async_cleanup_failed_setup_safely(
    domain_data: dict, client_key: str, entry: ConfigEntry
) -> None:
    """Complete failed-setup cleanup before propagating cancellation."""
    cleanup_task = asyncio.create_task(
        _async_cleanup_failed_setup(domain_data, client_key, entry)
    )
    cancelled = False
    while not cleanup_task.done():
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            cancelled = True

    # Propagate any cleanup failure before restoring cancellation semantics.
    cleanup_task.result()
    if cancelled:
        raise asyncio.CancelledError


async def _async_optional_first_refresh(
    coordinator: DeviceDataUpdateCoordinator, data_name: str
) -> None:
    """Refresh optional cloud data without preventing core entity setup."""
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady as error:
        _LOGGER.warning(
            "Could not fetch optional Ariston %s data; core controls remain "
            "available and the coordinator will retry later: %s",
            data_name,
            error,
        )

PLATFORMS: list[str] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]

SERVICE_SET_ITEM_BY_ID = "set_item_by_id"
ATTR_ITEM_ID = "item_id"
ATTR_ZONE = "zone"
ATTR_VALUE = "value"

SET_ITEM_BY_ID_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_ITEM_ID): cv.string,
        vol.Required(ATTR_ZONE): cv.positive_int,
        vol.Required(ATTR_VALUE): vol.Coerce(float),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ariston from a config entry."""
    domain_data: dict | None = None
    client_key: str | None = None
    shared_client: _SharedAristonClient | None = None
    client_registered = False
    try:
        api_url_setting = entry.data.get(API_URL_SETTING, ARISTON_API_URL)

        api_user_agent = entry.data.get(API_USER_AGENT, ARISTON_USER_AGENT)

        domain_data = hass.data.setdefault(DOMAIN, {})
        shared_clients: dict[str, _SharedAristonClient] = domain_data.setdefault(
            SHARED_CLIENTS, {}
        )
        client_key = _client_key(entry, api_url_setting, api_user_agent)
        shared_client = shared_clients.setdefault(
            client_key,
            _SharedAristonClient(),
        )
        shared_client.entry_ids.add(entry.entry_id)
        client_registered = True

        async with shared_client.lock:
            if not shared_client.connected:
                response = await shared_client.ariston.async_connect(
                    entry.data[CONF_USERNAME],
                    entry.data[CONF_PASSWORD],
                    api_url_setting,
                    api_user_agent,
                )
                if not response:
                    _LOGGER.error(
                        "Failed to connect to Ariston with device: %s",
                        entry.data[CONF_DEVICE].get(DeviceAttribute.NAME),
                    )
                    raise ConfigEntryAuthFailed
                shared_client.connected = True

            gateway = entry.data[CONF_DEVICE].get(DeviceAttribute.GW)
            is_metric = hass.config.units is METRIC_SYSTEM
            device = await shared_client.ariston.async_hello(gateway, is_metric)
            if device is None:
                # The account client can outlive one entry reload. Refresh its
                # discovery cache once in case devices changed in the cloud.
                await shared_client.ariston.async_discover()
                device = await shared_client.ariston.async_hello(gateway, is_metric)
        if device is None:
            raise ConfigEntryNotReady(f"Ariston device {gateway} was not discovered")

        await device.async_get_features()

        scan_interval_seconds = max(
            MIN_SCAN_INTERVAL_SECONDS,
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        coordinator = DeviceDataUpdateCoordinator(
            hass, device, scan_interval_seconds, COORDINATOR, device.async_update_state
        )

        entry_data = domain_data.setdefault(entry.unique_id, {})
        entry_data.setdefault(COORDINATOR, None)
        entry_data.setdefault(ENERGY_COORDINATOR, None)
        entry_data.setdefault(BUS_ERRORS_COORDINATOR, None)
        entry_data[COORDINATOR] = coordinator
        entry_data[_SHARED_CLIENT_KEY] = client_key

        await coordinator.async_config_entry_first_refresh()

        if entry.options.get(ENABLE_BUS_ERRORS, DEFAULT_ENABLE_BUS_ERRORS):
            bus_errors_scan_interval_seconds = max(
                MIN_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
                entry.options.get(
                    BUS_ERRORS_SCAN_INTERVAL,
                    DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
                ),
            )
            bus_errors_coordinator = DeviceDataUpdateCoordinator(
                hass,
                device,
                bus_errors_scan_interval_seconds,
                BUS_ERRORS_COORDINATOR,
                device.async_get_bus_errors,
            )
            entry_data[BUS_ERRORS_COORDINATOR] = bus_errors_coordinator
            await _async_optional_first_refresh(bus_errors_coordinator, "bus error")

        if device.has_metering and entry.options.get(
            ENABLE_ENERGY, DEFAULT_ENABLE_ENERGY
        ):
            energy_interval_minutes = max(
                MIN_ENERGY_SCAN_INTERVAL_MINUTES,
                entry.options.get(
                    ENERGY_SCAN_INTERVAL, DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES
                ),
            )
            energy_coordinator = DeviceDataUpdateCoordinator(
                hass,
                device,
                energy_interval_minutes * 60,
                ENERGY_COORDINATOR,
                device.async_update_energy,
            )
            entry_data[ENERGY_COORDINATOR] = energy_coordinator
            await _async_optional_first_refresh(energy_coordinator, "energy")

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        entry.async_on_unload(entry.add_update_listener(update_listener))

        if device.system_type == SystemType.GALEVO:

            async def async_set_item_by_id_service(service_call):
                """Create a vacation on the target device."""
                device_id = service_call.data.get(ATTR_DEVICE_ID)
                item_id = service_call.data.get(ATTR_ITEM_ID)
                zone = service_call.data.get(ATTR_ZONE)
                value = service_call.data.get(ATTR_VALUE)

                device_registry = dr.async_get(hass)
                device = device_registry.devices[device_id]

                entry = hass.config_entries.async_get_entry(
                    next(iter(device.config_entries))
                )
                coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][
                    entry.unique_id
                ][COORDINATOR]
                await coordinator.device.async_set_item_by_id(item_id, value, zone)

            hass.services.async_register(
                DOMAIN,
                SERVICE_SET_ITEM_BY_ID,
                async_set_item_by_id_service,
                schema=SET_ITEM_BY_ID_SCHEMA,
            )
    except asyncio.CancelledError:
        if client_registered and domain_data is not None and client_key is not None:
            # Finish releasing the shared account reference even while Home
            # Assistant is cancelling setup during shutdown or reload.
            await _async_cleanup_failed_setup_safely(
                domain_data, client_key, entry
            )
        raise
    except (ConfigEntryAuthFailed, ConfigEntryNotReady):
        if client_registered and domain_data is not None and client_key is not None:
            await _async_cleanup_failed_setup_safely(
                domain_data, client_key, entry
            )
        raise
    except Exception as error:
        if client_registered and domain_data is not None and client_key is not None:
            await _async_cleanup_failed_setup_safely(
                domain_data, client_key, entry
            )
        _LOGGER.exception("")
        raise ConfigEntryNotReady from error

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        domain_data = hass.data[DOMAIN]
        entry_data = domain_data.pop(entry.unique_id, {})
        client_key = entry_data.get(_SHARED_CLIENT_KEY)
        if client_key is not None:
            await _async_release_shared_client(
                domain_data,
                client_key,
                entry.entry_id,
            )

    return unload_ok
