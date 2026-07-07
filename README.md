# Conow Local for Home Assistant

Local **Modbus RTU** integration for CONOW balcony-solar / all-in-one energy devices (Lyra, CBE, Atlas). No cloud account required.

Protocol reference: [developer-docs/modbus/balcony-solar-storage.md](https://github.com/conow-labs/developer-docs/blob/main/modbus/balcony-solar-storage.md)

## Features

- Read real-time monitoring registers (battery, grid, PV, energy counters)
- System status binary sensors (charging, fault, running, …)
- Write control registers (power limits, off-grid switch, force charge/discharge)

## Prerequisites

Complete **all** of the following before adding the integration.

### 1. Activate the device in the App

The device must be commissioned and online in the **CONOW ECO App** at least once. RS-485 will not work on a factory-fresh device that has never been activated.

### 2. Enable DIY Mode in the App

Modbus RTU is disabled until you turn on external control in the app. Use **one** of the following:

**Option A — DIY Mode (recommended)**

1. Open **CONOW ECO App** → **Devices**
2. Tap your device to open the device panel
3. Go to **Settings → Operation Mode**
4. Select **DIY Mode**

**Option B — Enable External Control**

1. Open **CONOW ECO App** → **Devices**
2. Tap your device → **Settings**
3. Turn on **Enable External Control**

Until DIY Mode or External Control is enabled, the device will not respond to Modbus commands.

### 3. RS-485 wiring

Connect an RS-485 to USB adapter between the Home Assistant host and the device RS-485 port (A/B polarity must match the device label).

### 4. Serial parameters

Use the factory defaults unless you have changed them in manufacturer setup software:

| Parameter | Value |
|-----------|-------|
| Baud rate | **38400** |
| Data bits | 8 |
| Parity | None |
| Stop bits | 1 (8N1) |
| Slave address | **160** (hex **0xA0**) |

## Install (HACS)

1. Add `https://github.com/hongjiaweifox-wq/local-ha` as a custom repository (Integration)
2. Install **Conow Local**
3. Restart Home Assistant

## Configure

**Settings → Devices & Services → Add Integration → Conow Local**

| Field | Value |
|-------|-------|
| Device name | Any label you prefer |
| Serial port | Host path, e.g. `/dev/ttyUSB0` (Linux), `/dev/cu.usbserial-130` (macOS) |
| Slave address | **`160`** |
| Baud rate | **`38400`** |

If setup fails with *cannot connect*, or sensor values look wrong (e.g. extremely large numbers), check:

1. DIY Mode (or External Control) is **on** in the App
2. Slave address is **`160`** and baud rate is **`38400`**
3. Only one program is using the serial port at a time
4. RS-485 A/B wiring and USB adapter driver are correct

## Polling & control read-back

### Scheduled polling (automatic read)

The integration polls the device on a fixed interval and refreshes all entities:

| Constant | Default | Meaning |
|----------|---------|---------|
| `MODBUS_POLL_INTERVAL` | **5 s** | Background read of monitoring + control registers (`read_all`) |

Protocol docs require a polling interval of **at least 2 s**; the default is **5 s** to reduce RS-485 bus load when communication is unstable.

Each poll issues two Modbus reads (FC `0x03`):

1. Registers **10000–10036** (monitoring)
2. After **0.15 s** inter-frame delay → registers **10100–10107** (control)

### After a control write (UI / service call)

When you change a number, switch, or select, the integration does **not** wait for the next 5 s poll. In one locked serial session it:

1. **Writes** the control register(s) (FC `0x06`; force charge/discharge writes **10106 → 10105 → 10107**)
2. Waits **0.3 s** (`POST_WRITE_DELAY_S`)
3. **Reads back** the full monitoring + control blocks (`read_all`) and updates entities immediately

## Logging & Modbus frames

Enable integration logs in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.conow_local: info
```

For read-request hex dumps (background poll), also set:

```yaml
    custom_components.conow_local.client: debug
```

View logs: **Settings → System → Logs**, then filter by `conow_local` or `Modbus write`.

### Key log messages

| Level | Message | When |
|-------|---------|------|
| INFO | `Coordinator: executing Modbus write then read-back` | You change a control entity |
| INFO | `Control write <name>: addr=... physical=... raw=...` | Before FC `0x06` |
| INFO | `Modbus write TX (FC 0x06): A0 06 ...` | **Outgoing RTU frame** (hex) |
| INFO | `Modbus write OK: ... expected RX echo: ...` | Device acknowledged the write |
| ERROR | `Modbus write failed: ... TX=...` | No reply or Modbus error |
| ERROR | `Read failed after 3 attempts ...` | Poll or read-back failed |
| INFO | `Modbus read OK: ... RX=...` | Read response RTU frame (hex) + decoded registers |
| DEBUG | `Modbus read TX (FC 0x03): A0 03 ...` | Scheduled poll read request |

### Example write frame (discharge power limit 700 W → register 10101)

```text
A0 06 27 75 02 BC 8B 04
│  │  └───┘  └───┘  └───┘
│  │    │      │      └── CRC16 (little-endian)
│  │    │      └── Value: 700 (0x02BC)
│  │    └── Address: 10101 (0x2775)
│  └── FC 0x06
└── Slave 160 (0xA0)
```

On success, the device normally **echoes the same 8 bytes** as the response.

Register map (Excel): [docs/register-map.xlsx](docs/register-map.xlsx)

## Adding registers & entities

After installation, **new Modbus points only require editing two places**:

1. **`custom_components/conow_local/registers.json`** — register address, scale, HA platform, options, etc.
2. **Translations** — `strings.json`, `translations/en.json`, `translations/zh-Hans.json` (entity display names)

No Python changes are needed for typical sensor / number / switch / binary_sensor entries.

### `registers.json` structure

| Section | Purpose |
|---------|---------|
| `blocks` | Modbus read block start addresses (`monitoring`, `control`); read count is **auto-calculated** from register addresses |
| `sequences` | Special multi-register write order (e.g. `force_mode`) |
| `registers` | Modbus definitions: `code`, `address`, `block`, `dtype`, `scale`, `unit`, `writable` |
| `entities` | Home Assistant entities: `platform`, `register`, `device_class`, `min`/`max`, `bit`, `options` |

### Example — add a read-only sensor

In `registers`:

```json
{
  "code": "new_metric",
  "address": 10037,
  "block": "monitoring",
  "dtype": "uint16",
  "scale": 0.1,
  "unit": "W"
}
```

In `entities`:

```json
{
  "code": "new_metric",
  "platform": "sensor",
  "register": "new_metric",
  "device_class": "power"
}
```

Add `"new_metric": { "name": "..." }` under `entity.sensor` in all three translation files, then **reload the integration**.

### Platform-specific JSON fields

| Platform | Extra `entities` fields |
|----------|-------------------------|
| `sensor` | `device_class`, `state_class`, `suggested_display_precision`, `entity_category` |
| `binary_sensor` | `register` (bitmask source), `bit`, `device_class` |
| `number` | `min`, `max`, `step` |
| `switch` | — (writes `0` / `1`) |
| `select` | `options` (`"label": raw_value`), optional `write_handler`: `"force_mode"` |

## Related

- Cloud integration (Tuya / Energy API): [conow-labs/home-assistant](https://github.com/conow-labs/home-assistant)
- Modbus protocol & register map: [developer-docs/modbus](https://github.com/conow-labs/developer-docs/tree/main/modbus)
- Standalone CLI for field testing: [developer-docs/examples/python](https://github.com/conow-labs/developer-docs/tree/main/examples/python)

## License

MIT
