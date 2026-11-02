"""Entity descriptions for panel-backed read-only registers (v2 map).

The October map marks each register read-only or writable. Writable on/off
registers become switches and writable ``hhmm`` registers become time
entities; every other read-only register is exposed as a sensor or binary
sensor so the Home Assistant device page shows the same values as the panel.
"""

from __future__ import annotations

from functools import lru_cache

from homeassistant.components.binary_sensor import BinarySensorEntityDescription
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

# Map unit strings from panel_registers.json onto HA units/device classes.
UNITS: dict[str, tuple[str, SensorDeviceClass | None]] = {
    "W": (UnitOfPower.WATT, SensorDeviceClass.POWER),
    "kWh": (UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY),
    "V": (UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
    "A": (UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
    "Hz": (UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY),
    "%": (PERCENTAGE, None),
    "℃": (UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    "°C": (UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    "dBm": (
        SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        SensorDeviceClass.SIGNAL_STRENGTH,
    ),
}


@lru_cache(maxsize=1)
def _group_ids() -> dict[str, str]:
    """Return ``code -> group id`` for every grouped register."""
    return {
        code: group.id for group in panel_map.get_groups() for code in group.members
    }


def is_panel_sensor(register: panel_map.PanelRegister) -> bool:
    """Return whether the register is exposed as a read-only sensor."""
    return not register.writable and not register.boolean


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
    """Build a sensor description from a read-only panel register."""
    kwargs: dict[str, object] = {
        "key": register.code,
        "name": register.name,
    }
    if register.values:
        # Enum registers carry their label as the state, so they have no unit.
        kwargs["device_class"] = SensorDeviceClass.ENUM
        kwargs["options"] = list(register.values.values())
    else:
        unit, device_class = UNITS.get(register.unit, (None, None))
        if unit is not None:
            kwargs["native_unit_of_measurement"] = unit
        if device_class is not None:
            kwargs["device_class"] = device_class
        if device_class == SensorDeviceClass.ENERGY:
            if _group_ids().get(register.code) == "capacity":
                # Design/remaining capacity is a stored-energy level, not a
                # counter; HA requires a different class for a measurement.
                kwargs["device_class"] = SensorDeviceClass.ENERGY_STORAGE
                kwargs["state_class"] = SensorStateClass.MEASUREMENT
            else:
                # Lifetime counters and per-string PV counters only grow.
                kwargs["state_class"] = SensorStateClass.TOTAL_INCREASING
        elif unit is not None or device_class is not None:
            kwargs["state_class"] = SensorStateClass.MEASUREMENT
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
    if (category := _entity_category(register)) is not None:
        kwargs["entity_category"] = category
    return BinarySensorEntityDescription(**kwargs)
