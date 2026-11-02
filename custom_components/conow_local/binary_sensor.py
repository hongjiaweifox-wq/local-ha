"""Modbus binary sensor entities."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ConowLocalCoordinator
from .entity_factory import (
    build_binary_sensor_description,
    build_device_info,
)
from .map_router import MAP_V2
from .panel import panel_map
from .panel.panel_coordinator import ConowPanelCoordinator, get_panel_coordinator
from .panel.panel_entities import (
    build_panel_binary_sensor_description,
    is_panel_binary_sensor,
    panel_unique_code,
)
from .register_map import EntityDef, get_entities


class ConowModbusBinarySensor(
    CoordinatorEntity[ConowLocalCoordinator], BinarySensorEntity
):
    """Binary sensor for system status bits."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ConowLocalCoordinator,
        entry: ConfigEntry,
        entity: EntityDef,
    ) -> None:
        """Initialize binary sensor."""
        super().__init__(coordinator)
        self._bit_name = entity.code
        self.entity_description = build_binary_sensor_description(entity)
        self._attr_unique_id = f"{entry.entry_id}_status_{entity.code}"
        self._attr_device_info = build_device_info(coordinator.hass, entry)

    @property
    def is_on(self) -> bool | None:
        """Return parsed status bit."""
        return self.coordinator.get_status_bit(self._bit_name)


class ConowPanelBinarySensor(
    CoordinatorEntity[ConowPanelCoordinator], BinarySensorEntity
):
    """Read-only on/off register from the October panel map."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ConowPanelCoordinator,
        entry: ConfigEntry,
        register: panel_map.PanelRegister,
        unique_code: str,
    ) -> None:
        """Initialize the panel-backed binary sensor."""
        super().__init__(coordinator)
        self._register = register
        self.entity_description = build_panel_binary_sensor_description(register)
        self._attr_unique_id = f"{entry.entry_id}_{unique_code}"
        self._attr_device_info = build_device_info(coordinator.hass, entry)

    @property
    def is_on(self) -> bool | None:
        """Return the register's raw 0/1 state."""
        raw = (self.coordinator.data or {}).get(self._register.code, {}).get("raw")
        if not isinstance(raw, int):
            return None
        return bool(raw)


async def _async_add_panel_binary_sensors(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one binary sensor per read-only boolean register of the map."""
    coordinator = get_panel_coordinator(hass, entry.entry_id)
    if coordinator is None:
        return
    v1_codes = {entity.code for entity in get_entities("binary_sensor")}
    async_add_entities(
        ConowPanelBinarySensor(
            coordinator,
            entry,
            register,
            unique_code=panel_unique_code(register, v1_codes),
        )
        for register in panel_map.get_registers()
        if is_panel_binary_sensor(register)
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Modbus binary sensors from the active register map."""
    coordinator: ConowLocalCoordinator = entry.runtime_data
    if coordinator.map_version != MAP_V2:
        async_add_entities(
            ConowModbusBinarySensor(coordinator, entry, entity_def)
            for entity_def in get_entities("binary_sensor")
        )
        return
    await _async_add_panel_binary_sensors(hass, entry, async_add_entities)
