"""Config flow for Conow Local."""

from functools import partial
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .client import (
    ConowModbusError,
    ConowVerificationError,
    probe_connection,
    probe_direct_connection,
)
from .const import (
    CONF_DEVICE_NAME,
    CONF_MODBUS_BAUDRATE,
    CONF_MODBUS_HOST,
    CONF_MODBUS_MODE,
    CONF_MODBUS_PORT,
    CONF_MODBUS_SLAVE,
    CONF_MODBUS_TCP_PORT,
    CONF_TCP_VERIFY_CODE,
    DEFAULT_BAUDRATE,
    DEFAULT_SLAVE,
    DEFAULT_TCP_PORT,
    DOMAIN,
    MODBUS_MODE_RTU,
    MODBUS_MODE_TCP,
    MODBUS_MODE_TCP_DIRECT,
)

MODBUS_MODES = {
    MODBUS_MODE_RTU: "Modbus RTU (RS-485 serial)",
    MODBUS_MODE_TCP: "Modbus TCP (RS-485↔Ethernet adapter)",
    MODBUS_MODE_TCP_DIRECT: "Modbus TCP (direct to all-in-one machine)",
}


def _is_valid_verify_code(value: str) -> bool:
    """Return whether the value is exactly six decimal digits."""
    text = str(value).strip()
    return len(text) == 6 and text.isdigit()

class ConowLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle Conow Local config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the Modbus connection mode."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_MODBUS_MODE, default=MODBUS_MODE_RTU
                        ): vol.In(MODBUS_MODES),
                    }
                ),
            )

        mode = user_input[CONF_MODBUS_MODE]
        if mode == MODBUS_MODE_TCP_DIRECT:
            return await self.async_step_tcp_direct()
        if mode == MODBUS_MODE_TCP:
            return await self.async_step_tcp()
        return await self.async_step_rtu()

    def _rtu_schema(
        self, device_name: str = "CONOW Energy", port: str = "", slave: int = DEFAULT_SLAVE,
        baudrate: int = DEFAULT_BAUDRATE,
    ) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_DEVICE_NAME, default=device_name): str,
                vol.Required(CONF_MODBUS_PORT, default=port): str,
                vol.Optional(CONF_MODBUS_SLAVE, default=slave): int,
                vol.Optional(CONF_MODBUS_BAUDRATE, default=baudrate): int,
            }
        )

    def _tcp_schema(
        self, device_name: str = "CONOW Energy", host: str = "",
        tcp_port: int = DEFAULT_TCP_PORT, slave: int = DEFAULT_SLAVE,
    ) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_DEVICE_NAME, default=device_name): str,
                vol.Required(CONF_MODBUS_HOST, default=host): str,
                vol.Optional(CONF_MODBUS_TCP_PORT, default=tcp_port): int,
                vol.Optional(CONF_MODBUS_SLAVE, default=slave): int,
            }
        )

    def _tcp_direct_schema(
        self, device_name: str = "CONOW Energy", host: str = "",
        tcp_port: int = DEFAULT_TCP_PORT, slave: int = DEFAULT_SLAVE,
        verify_code: str = "",
    ) -> vol.Schema:
        return self._tcp_schema(device_name, host, tcp_port, slave).extend(
            {
                vol.Required(CONF_TCP_VERIFY_CODE, default=verify_code): str,
            }
        )

    async def async_step_rtu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a Modbus RTU serial connection."""
        errors: dict[str, str] = {}
        if user_input is not None:
            port = user_input[CONF_MODBUS_PORT]
            slave = user_input[CONF_MODBUS_SLAVE]
            baudrate = user_input[CONF_MODBUS_BAUDRATE]
            await self.async_set_unique_id(f"modbus_rtu_{port}_{slave}_{baudrate}")
            self._abort_if_unique_id_configured()
            try:
                await self.hass.async_add_executor_job(
                    partial(probe_connection, port, slave=slave, baudrate=baudrate)
                )
            except ConowModbusError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_DEVICE_NAME],
                    data={
                        CONF_MODBUS_MODE: MODBUS_MODE_RTU,
                        CONF_DEVICE_NAME: user_input[CONF_DEVICE_NAME],
                        CONF_MODBUS_PORT: port,
                        CONF_MODBUS_SLAVE: slave,
                        CONF_MODBUS_BAUDRATE: baudrate,
                    },
                )

            return self.async_show_form(
                step_id="rtu",
                data_schema=self._rtu_schema(
                    user_input.get(CONF_DEVICE_NAME, "CONOW Energy"),
                    port,
                    slave,
                    baudrate,
                ),
                errors=errors,
            )

        return self.async_show_form(step_id="rtu", data_schema=self._rtu_schema())

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a Modbus TCP connection via an RS-485↔Ethernet adapter."""
        return await self._async_step_tcp(
            user_input, MODBUS_MODE_TCP, "tcp", "modbus_tcp"
        )

    async def async_step_tcp_direct(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a Modbus TCP connection to the all-in-one machine."""
        return await self._async_step_tcp(
            user_input, MODBUS_MODE_TCP_DIRECT, "tcp_direct", "modbus_tcp_direct"
        )

    async def _async_step_tcp(
        self,
        user_input: dict[str, Any] | None,
        mode: str,
        step_id: str,
        unique_prefix: str,
    ) -> ConfigFlowResult:
        """Shared Modbus TCP form for adapters and direct device connections."""
        errors: dict[str, str] = {}
        direct = mode == MODBUS_MODE_TCP_DIRECT
        if user_input is not None:
            host = user_input[CONF_MODBUS_HOST]
            tcp_port = user_input[CONF_MODBUS_TCP_PORT]
            slave = user_input[CONF_MODBUS_SLAVE]
            verify_code = str(user_input.get(CONF_TCP_VERIFY_CODE, "")).strip()
            if direct and not _is_valid_verify_code(verify_code):
                errors["base"] = "invalid_verify_code"
            else:
                await self.async_set_unique_id(
                    f"{unique_prefix}_{host}_{tcp_port}_{slave}"
                )
                self._abort_if_unique_id_configured()
                try:
                    if direct:
                        await self.hass.async_add_executor_job(
                            partial(
                                probe_direct_connection,
                                host,
                                tcp_port=tcp_port,
                                slave=slave,
                                verify_code=verify_code,
                            )
                        )
                    else:
                        await self.hass.async_add_executor_job(
                            partial(
                                probe_connection,
                                None,
                                host=host,
                                tcp_port=tcp_port,
                                slave=slave,
                            )
                        )
                except ConowVerificationError:
                    errors["base"] = "verification_failed"
                except ConowModbusError:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=user_input[CONF_DEVICE_NAME],
                        data={
                            CONF_MODBUS_MODE: mode,
                            CONF_DEVICE_NAME: user_input[CONF_DEVICE_NAME],
                            CONF_MODBUS_HOST: host,
                            CONF_MODBUS_TCP_PORT: tcp_port,
                            CONF_MODBUS_SLAVE: slave,
                        },
                    )

            return self.async_show_form(
                step_id=step_id,
                data_schema=(
                    self._tcp_direct_schema(
                        user_input.get(CONF_DEVICE_NAME, "CONOW Energy"),
                        host,
                        tcp_port,
                        slave,
                        verify_code,
                    )
                    if direct
                    else self._tcp_schema(
                        user_input.get(CONF_DEVICE_NAME, "CONOW Energy"),
                        host,
                        tcp_port,
                        slave,
                    )
                ),
                errors=errors,
            )

        return self.async_show_form(
            step_id=step_id,
            data_schema=(
                self._tcp_direct_schema() if direct else self._tcp_schema()
            ),
        )
