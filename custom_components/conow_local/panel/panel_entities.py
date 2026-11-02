"""Entity descriptions for panel-backed read-only registers (v2 map).

The October map marks each register read-only or writable. Writable on/off
registers become switches and writable ``hhmm`` registers become time
entities; every other read-only register is exposed as a sensor or binary
sensor so the Home Assistant device page shows the same values as the panel.
Writable numeric registers get a hidden mirror sensor: writes still go
through the grouping panel, but the entity gives the panel row a history.
"""

from __future__ import annotations

from functools import lru_cache

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import EntityCategory

from . import panel_map

# Device page groups that hold identification/hardware details rather than
# live telemetry; HA renders these under the diagnostic section.
DIAGNOSTIC_GROUPS = frozenset({"device_info"})

# Map unit strings from panel_registers.json onto HA units.  device_class and
# state_class are read from the map itself, never inferred here.
HA_UNITS: dict[str, str] = {
    "W": UnitOfPower.WATT,
    "kWh": UnitOfEnergy.KILO_WATT_HOUR,
    "V": UnitOfElectricPotential.VOLT,
    "A": UnitOfElectricCurrent.AMPERE,
    "Hz": UnitOfFrequency.HERTZ,
    "%": PERCENTAGE,
    "℃": UnitOfTemperature.CELSIUS,
    "°C": UnitOfTemperature.CELSIUS,
    "dBm": SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
}

SENSOR_DEVICE_CLASSES: dict[str, SensorDeviceClass] = {
    "power": SensorDeviceClass.POWER,
    "energy": SensorDeviceClass.ENERGY,
    "energy_storage": SensorDeviceClass.ENERGY_STORAGE,
    "voltage": SensorDeviceClass.VOLTAGE,
    "current": SensorDeviceClass.CURRENT,
    "frequency": SensorDeviceClass.FREQUENCY,
    "temperature": SensorDeviceClass.TEMPERATURE,
    "signal_strength": SensorDeviceClass.SIGNAL_STRENGTH,
    "enum": SensorDeviceClass.ENUM,
    "battery": SensorDeviceClass.BATTERY,
}

SENSOR_STATE_CLASSES: dict[str, SensorStateClass] = {
    "measurement": SensorStateClass.MEASUREMENT,
    "total_increasing": SensorStateClass.TOTAL_INCREASING,
}

BINARY_DEVICE_CLASSES: dict[str, BinarySensorDeviceClass] = {
    "battery_charging": BinarySensorDeviceClass.BATTERY_CHARGING,
    "power": BinarySensorDeviceClass.POWER,
    "problem": BinarySensorDeviceClass.PROBLEM,
    "running": BinarySensorDeviceClass.RUNNING,
}


@lru_cache(maxsize=1)
def _group_ids() -> dict[str, str]:
    """Return ``code -> group id`` for every grouped register."""
    return {
        code: group.id for group in panel_map.get_groups() for code in group.members
    }


def is_panel_setting_sensor(register: panel_map.PanelRegister) -> bool:
    """Return whether a writable numeric register needs a mirror sensor.

    Writable numbers have no editable HA entity (writes must go through the
    grouping panel), but the panel row can only open the more-info/history
    dialog when an entity id backs it.  A hidden sensor mirrors the register
    value so history is recorded and the row is clickable.
    """
    return (
        register.writable
        and not register.boolean
        and not register.is_time
        and not register.values
        and register.dtype != "string"
    )


def is_panel_sensor(register: panel_map.PanelRegister) -> bool:
    """Return whether the register is exposed as a sensor."""
    return (not register.writable and not register.boolean) or (
        is_panel_setting_sensor(register)
    )


def is_panel_binary_sensor(register: panel_map.PanelRegister) -> bool:
    """Return whether the register is exposed as a read-only binary sensor."""
    return not register.writable and register.boolean


def panel_unique_code(
    register: panel_map.PanelRegister, taken: set[str]
) -> str:
    """Return the entity code suffix, prefixed when the v1 map reuses it."""
    return f"panel_{register.code}" if register.code in taken else register.code


def _entity_category(
    register: panel_map.PanelRegister,
) -> EntityCategory | None:
    if _group_ids().get(register.code) in DIAGNOSTIC_GROUPS:
        return EntityCategory.DIAGNOSTIC
    return None


def build_panel_sensor_description(
    register: panel_map.PanelRegister,
) -> SensorEntityDescription:
    """Build a sensor description from a panel register."""
    kwargs: dict[str, object] = {
        "key": register.code,
        "name": register.name,
    }
    if register.writable:
        # Mirror sensor for a panel-only setting: keep the device page clean
        # and hide it from the entity list, but keep it enabled so the panel
        # row can open its history.
        kwargs["entity_registry_visible_default"] = False
    unit = HA_UNITS.get(register.unit)
    if unit is not None:
        kwargs["native_unit_of_measurement"] = unit
    if register.device_class:
        try:
            kwargs["device_class"] = SENSOR_DEVICE_CLASSES[register.device_class]
        except KeyError as err:
            raise ValueError(
                f"{register.code}: unknown device_class {register.device_class!r}"
            ) from err
        if register.device_class == "enum":
            kwargs["options"] = list((register.values or {}).values())
    if register.state_class:
        try:
            kwargs["state_class"] = SENSOR_STATE_CLASSES[register.state_class]
        except KeyError as err:
            raise ValueError(
                f"{register.code}: unknown state_class {register.state_class!r}"
            ) from err
    if (category := _entity_category(register)) is not None:
        kwargs["entity_category"] = category
    return SensorEntityDescription(**kwargs)


def build_panel_binary_sensor_description(
    register: panel_map.PanelRegister,
) -> BinarySensorEntityDescription:
    """Build a binary sensor description from a read-only boolean register."""
    kwargs: dict[str, object] = {
        "key": register.code,
        "name": register.name,
    }
    if register.device_class:
        try:
            kwargs["device_class"] = BINARY_DEVICE_CLASSES[register.device_class]
        except KeyError as err:
            raise ValueError(
                f"{register.code}: unknown binary device_class "
                f"{register.device_class!r}"
            ) from err
    if (category := _entity_category(register)) is not None:
        kwargs["entity_category"] = category
    return BinarySensorEntityDescription(**kwargs)
