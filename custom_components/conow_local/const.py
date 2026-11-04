"""Constants for Conow Local (Modbus RTU) integration."""

import logging

from homeassistant.const import Platform

DOMAIN = "conow_local"
LOGGER = logging.getLogger(__package__)

# Frontend panel registered by panel/panel_api.py; used as the device page
# "Visit" link so every device under this integration can open the panel.
PANEL_URL_PATH = "conow-local-panel"

CONF_MODBUS_MODE = "modbus_mode"
CONF_MODBUS_PORT = "modbus_port"
CONF_MODBUS_HOST = "modbus_host"
CONF_MODBUS_TCP_PORT = "modbus_tcp_port"
CONF_MODBUS_SLAVE = "modbus_slave"
CONF_MODBUS_BAUDRATE = "modbus_baudrate"
CONF_DEVICE_NAME = "device_name"
CONF_TCP_VERIFY_CODE = "tcp_verify_code"

MODBUS_MODE_RTU = "rtu"
MODBUS_MODE_TCP = "tcp"
MODBUS_MODE_TCP_DIRECT = "tcp_direct"
MODBUS_TCP_MODES = (MODBUS_MODE_TCP, MODBUS_MODE_TCP_DIRECT)
DEFAULT_TCP_PORT = 502

MODBUS_POLL_INTERVAL = 5

DEFAULT_SLAVE = 0xA0
DEFAULT_BAUDRATE = 38400

# One spec-driven entity layer for both maps.  Every writable register is
# visible as a control (number/select/switch/time); the platform actions
# refuse to write and point at the grouping panel instead.
PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.TIME,
]

