"""Generate the panel i18n JSON and the Home Assistant entity strings.

Run from the repository root:
    python tools/i18n/build_panel_i18n.py

Chinese names/labels come straight from the map JSON files; English, German
and Dutch are looked up here so the panel and the device page can follow the
Home Assistant language instead of always rendering Chinese.

This is the single translation catalog: one run writes
``panel/frontend/i18n/{en,de,nl,zh-Hans}.json`` and the ``entity`` section of
``strings.json`` / ``translations/*.json``.  Missing entries are hard errors —
the tool never falls back to a previous output file.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
COMPONENT_DIR = ROOT / "custom_components/conow_local"
OUT_DIR = COMPONENT_DIR / "panel/frontend/i18n"

# Import the integration's stdlib-only layer-1+2 package (maps.registry,
# maps.model, maps.entity_model) without installing Home Assistant.
if "conow_local" not in sys.modules:
    _package = types.ModuleType("conow_local")
    _package.__path__ = [str(COMPONENT_DIR)]
    sys.modules["conow_local"] = _package

from conow_local.maps import entity_model, registry  # noqa: E402

LANGS = ("en", "de", "nl")
ALL_LANGS = ("en", "de", "nl", "zh-Hans")

# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------
# One entry per category column of each table.  Both maps now share the same
# category names, so most ids are used by v1 and v2 alike.
GROUPS = {
    "system": ("System", "System", "Systeem"),
    "realtime": ("Real-time Monitoring", "Echtzeitüberwachung", "Realtime bewaking"),
    "monitor_detail": (
        "Detailed Monitoring",
        "Detaillierte Überwachung",
        "Gedetailleerde bewaking",
    ),
    "device_info": (
        "Operating Parameters & Device Information",
        "Betriebsparameter & Geräteinformationen",
        "Bedrijfsparameters & apparaatinformatie",
    ),
    "lifetime_energy": ("Cumulative Energy", "Kumulierte Energie", "Cumulatieve energie"),
    "power_limit": (
        "Power & SoC Settings",
        "Leistungs- & SoC-Einstellungen",
        "Vermogen & SoC-instellingen",
    ),
    "force_control": ("Real-time Control", "Echtzeitsteuerung", "Realtime besturing"),
    "work_strategy": ("Work Strategy", "Arbeitsstrategie", "Werkstrategie"),
    "generator_do": ("Generator & DO", "Generator & DO", "Generator & DO"),
    "base_load": ("Base Load", "Grundlast", "Basislast"),
    "base_load_schedule": (
        "Base Load Schedule",
        "Grundlast-Zeitplan",
        "Basislast-schema",
    ),
    "tou_schedule": ("TOU Schedule", "TOU-Zeitplan", "TOU-schema"),
    "time_sync": ("Time Calibration", "Zeitkalibrierung", "Tijdkalibratie"),
}

SUBGROUPS = {
    "en": {"slot": "Slot {n}", "strategy": "Strategy {n}"},
    "de": {"slot": "Zeitfenster {n}", "strategy": "Strategie {n}"},
    "nl": {"slot": "Tijdslot {n}", "strategy": "Strategie {n}"},
}

# ---------------------------------------------------------------------------
# Register names: code -> (en, de, nl)
# ---------------------------------------------------------------------------
REGISTERS = {
    "device_status": ("Device Status", "Gerätestatus", "Apparaatstatus"),
    "device_fault_code": ("Device Fault Code", "Gerätefehlercode", "Apparaatfoutcode"),
    "device_clock": ("Device Clock", "Geräteuhr", "Apparaatklok"),
    "system_soc": ("System SoC", "System-SoC", "Systeem-SoC"),
    "meter_connection_state": (
        "Meter Connection State",
        "Zählerverbindungsstatus",
        "Meterverbindingsstatus",
    ),
    "meter_total_power": (
        "Meter Total Power",
        "Zählergesamtleistung",
        "Metertotaalvermogen",
    ),
    "grid_active_power": (
        "Grid Active Power",
        "Netz-Wirkleistung",
        "Net actief vermogen",
    ),
    "pv_total_power": ("PV Total Power", "PV-Gesamtleistung", "PV-totaalvermogen"),
    "battery_work_state": (
        "Battery Work State",
        "Batteriebetriebsstatus",
        "Accuwerkstatus",
    ),
    "battery_power": ("Battery Power", "Batterieleistung", "Accuvermogen"),
    "bypass_switch_state": (
        "Bypass Switch State",
        "Bypass-Schaltstatus",
        "Bypass-schakelstatus",
    ),
    "bypass_power": ("Bypass Power", "Bypass-Leistung", "Bypass-vermogen"),
    "grid_voltage": ("Grid Voltage", "Netzspannung", "Netspanning"),
    "grid_current": ("Grid Current", "Netzstrom", "Netstroom"),
    "grid_frequency": ("Grid Frequency", "Netzfrequenz", "Netfrequentie"),
    "phase_a_power": ("Phase A Power", "Phase-A-Leistung", "Fase A vermogen"),
    "phase_b_power": ("Phase B Power", "Phase-B-Leistung", "Fase B vermogen"),
    "phase_c_power": ("Phase C Power", "Phase-C-Leistung", "Fase C vermogen"),
    "pv_string_count": ("PV String Count", "Anzahl PV-Strings", "Aantal PV-strings"),
    "pv1_voltage": ("PV1 Voltage", "PV1-Spannung", "PV1-spanning"),
    "pv1_current": ("PV1 Current", "PV1-Strom", "PV1-stroom"),
    "pv1_energy": ("PV1 Energy", "PV1-Energie", "PV1-energie"),
    "pv2_voltage": ("PV2 Voltage", "PV2-Spannung", "PV2-spanning"),
    "pv2_current": ("PV2 Current", "PV2-Strom", "PV2-stroom"),
    "pv2_energy": ("PV2 Energy", "PV2-Energie", "PV2-energie"),
    "pv3_voltage": ("PV3 Voltage", "PV3-Spannung", "PV3-spanning"),
    "pv3_current": ("PV3 Current", "PV3-Strom", "PV3-stroom"),
    "pv3_energy": ("PV3 Energy", "PV3-Energie", "PV3-energie"),
    "pv4_voltage": ("PV4 Voltage", "PV4-Spannung", "PV4-spanning"),
    "pv4_current": ("PV4 Current", "PV4-Strom", "PV4-stroom"),
    "pv4_energy": ("PV4 Energy", "PV4-Energie", "PV4-energie"),
    "battery_voltage": ("Battery Voltage", "Batteriespannung", "Accuspanning"),
    "battery_current": ("Battery Current", "Batteriestrom", "Accustroom"),
    "cell_temp_max": (
        "Max. Cell Temperature",
        "Max. Zelltemperatur",
        "Max. celtemperatuur",
    ),
    "cell_temp_min": (
        "Min. Cell Temperature",
        "Min. Zelltemperatur",
        "Min. celtemperatuur",
    ),
    "battery_max_charge_power": (
        "Current Max. Battery Charge Power",
        "Aktuelle max. Batterieladeleistung",
        "Huidig max. acculaadvermogen",
    ),
    "battery_max_discharge_power": (
        "Current Max. Battery Discharge Power",
        "Aktuelle max. Batterieentladeleistung",
        "Huidig max. accuontlaadvermogen",
    ),
    "bypass_voltage": ("Bypass Voltage", "Bypass-Spannung", "Bypass-spanning"),
    "bypass_current": ("Bypass Current", "Bypass-Strom", "Bypass-stroom"),
    "bypass_frequency": ("Bypass Frequency", "Bypass-Frequenz", "Bypass-frequentie"),
    "design_capacity": (
        "Design Capacity",
        "Auslegungskapazität",
        "Ontwerpcapaciteit",
    ),
    "remaining_capacity": (
        "Remaining Capacity",
        "Restkapazität",
        "Resterende capaciteit",
    ),
    "system_backup_soc": (
        "System Backup SoC",
        "System-Reserve-SoC",
        "Systeem-reserve-SoC",
    ),
    "soh": ("SOH", "SOH", "SOH"),
    "hardware_max_ac_charge_power": (
        "Hardware Max. AC Charge Power",
        "Hardware max. AC-Ladeleistung",
        "Hardware max. AC-laadvermogen",
    ),
    "hardware_max_ac_discharge_power": (
        "Hardware Max. AC Discharge Power",
        "Hardware max. AC-Entladeleistung",
        "Hardware max. AC-ontlaadvermogen",
    ),
    "grid_code_export_limit": (
        "Grid Code Export Limit",
        "Netzeinspeise-Grenzwert",
        "Netcode-exportlimiet",
    ),
    "global_ac_charge_power_limit": (
        "Global Max. AC Charge Power",
        "Globale max. AC-Ladeleistung",
        "Globaal max. AC-laadvermogen",
    ),
    "global_ac_discharge_power_limit": (
        "Global Max. AC Discharge Power",
        "Globale max. AC-Entladeleistung",
        "Globaal max. AC-ontlaadvermogen",
    ),
    "wifi_signal": (
        "Wi-Fi Signal Strength",
        "Wi-Fi-Signalstärke",
        "Wi-Fi-signaalsterkte",
    ),
    "device_serial": (
        "Device Serial Number",
        "Geräteseriennummer",
        "Serienummer apparaat",
    ),
    "firmware_version": ("Firmware Version", "Firmware-Version", "Firmwareversie"),
    "grid_import_energy_total": (
        "Total Grid Import Energy",
        "Netzbezug gesamt",
        "Totaal netimport",
    ),
    "grid_export_energy_total": (
        "Total Grid Export Energy",
        "Netzeinspeisung gesamt",
        "Totaal netexport",
    ),
    "meter_import_energy_total": (
        "Meter Total Import Energy",
        "Zählerbezug gesamt",
        "Totaal meterimport",
    ),
    "meter_export_energy_total": (
        "Meter Total Export Energy",
        "Zählereinspeisung gesamt",
        "Totaal meterexport",
    ),
    "pv_energy_total": ("Total PV Energy", "PV-Gesamtenergie", "Totaal PV-energie"),
    "battery_charge_energy_total": (
        "Total Battery Charge Energy",
        "Batterie-Ladeenergie gesamt",
        "Totaal acculaadenergie",
    ),
    "battery_discharge_energy_total": (
        "Total Battery Discharge Energy",
        "Batterie-Entladeenergie gesamt",
        "Totaal accuontlaadenergie",
    ),
    "bypass_output_energy_total": (
        "Total Bypass Output Energy",
        "Bypass-Ausgangsenergie gesamt",
        "Totaal bypass-uitgangsenergie",
    ),
    "bypass_input_energy_total": (
        "Total Bypass Input Energy",
        "Bypass-Eingangsenergie gesamt",
        "Totaal bypass-ingangsenergie",
    ),
    "ac_charge_power_limit": (
        "AC Charge Power Limit",
        "AC-Ladeleistungsgrenze",
        "AC-laadvermogenlimiet",
    ),
    "ac_discharge_power_limit": (
        "AC Discharge Power Limit",
        "AC-Entladeleistungsgrenze",
        "AC-ontlaadvermogenlimiet",
    ),
    "safety_soc": ("Safety SoC", "Sicherheits-SoC", "Veiligheids-SoC"),
    "charge_discharge_direction": (
        "Charge/Discharge Direction",
        "Lade-/Entladerichtung",
        "Laad-/ontlaadrichting",
    ),
    "battery_target_power": (
        "Target Charge/Discharge Power",
        "Ziel-Lade-/Entladeleistung",
        "Doel laad-/ontlaadvermogen",
    ),
    "charge_discharge_cutoff_soc": (
        "Charge/Discharge Cutoff SoC",
        "Lade-/Entlade-Abschalt-SoC",
        "Laad-/ontlaadafslag-SoC",
    ),
    "battery_cutoff_soc": (
        "Charge/Discharge Cutoff SoC",
        "Lade-/Entlade-Abschalt-SoC",
        "Laad-/ontlaadafslag-SoC",
    ),
    "charge_discharge_duration": (
        "Charge/Discharge Duration",
        "Lade-/Entladedauer",
        "Laad-/ontlaadduur",
    ),
    "work_mode": ("Work Mode", "Arbeitsmodus", "Werkmodus"),
    "base_load_setpoint": ("Base Load", "Grundlast", "Basislast"),
    "backup_soc": ("Backup SoC", "Reserve-SoC", "Reserve-SoC"),
    "allow_reverse_power": (
        "Allowed Reverse Power",
        "Zulässige Rückspeiseleistung",
        "Toegestaan terugleververmogen",
    ),
    "allow_battery_export": (
        "Allow Battery Export",
        "Batterieeinspeisung erlauben",
        "Accu-export toestaan",
    ),
    "bypass_enable": ("Bypass长开开关", "Bypass长开开关", "Bypass长开开关"),
    "off_grid_output_enable": (
        "Off-Grid Output Switch",
        "Off-Grid-Ausgangsschalter",
        "Off-grid-uitgangsschakelaar",
    ),
    "pv_curtailment_enable": (
        "PV Curtailment",
        "PV-Abregelung",
        "PV-beperking",
    ),
    "modbus_timeout": ("Modbus Timeout", "Modbus-Timeout", "Modbus-time-out"),
    "generator_enable": ("Generator Switch", "Generator-Schalter", "Generator-schakelaar"),
    "generator_start_time": (
        "Generator Start Time",
        "Generator-Startzeit",
        "Generator-starttijd",
    ),
    "generator_end_time": (
        "Generator End Time",
        "Generator-Endzeit",
        "Generator-eindtijd",
    ),
    "generator_power": ("Generator Power", "Generatorleistung", "Generatorvermogen"),
    "generator_start_soc": (
        "Generator Start SoC",
        "Generator-Start-SoC",
        "Generator-start-SoC",
    ),
    "generator_stop_soc": (
        "Generator Stop SoC",
        "Generator-Stopp-SoC",
        "Generator-stop-SoC",
    ),
    "do1_state": ("DO1 Control", "DO1-Steuerung", "DO1-besturing"),
    "do2_state": ("DO2 Control", "DO2-Steuerung", "DO2-besturing"),
    "base_load_slot_count": (
        "Base Load Slot Count",
        "Anzahl Grundlast-Zeitfenster",
        "Aantal basislast-tijdsloten",
    ),
    "tou_slot_count": ("TOU Slot Count", "Anzahl TOU-Zeitfenster", "Aantal TOU-tijdsloten"),
}

# v1-only register names (registers.json used to carry them in entities[]).
REGISTERS.update(
    {
        "system_status": ("System Status", "Systemstatus", "Systeemstatus"),
        "fault_code": ("Fault Code", "Fehlercode", "Foutcode"),
        "battery_soc": ("Battery SoC", "Batterie-SoC", "Accu-SoC"),
        "battery_design_capacity": (
            "Battery Rated Capacity",
            "Nennkapazität der Batterie",
            "Nominale batterijcapaciteit",
        ),
        "battery_cell_temp_max": (
            "Max Cell Temperature",
            "Maximale Zelltemperatur",
            "Maximale celtemperatuur",
        ),
        "battery_cell_temp_min": (
            "Min Cell Temperature",
            "Minimale Zelltemperatur",
            "Minimale celtemperatuur",
        ),
        "battery_cumulative_charge_energy": (
            "Battery Total Charged Energy",
            "Gesamt geladene Batterieenergie",
            "Totaal geladen batterij-energie",
        ),
        "battery_cumulative_discharge_energy": (
            "Battery Total Discharged Energy",
            "Gesamt entladene Batterieenergie",
            "Totaal ontladen batterij-energie",
        ),
        "grid_cumulative_import_energy": (
            "Grid Total Import Energy",
            "Netzbezug gesamt",
            "Totaal netafname",
        ),
        "grid_cumulative_export_energy": (
            "Grid Total Export Energy",
            "Netzeinspeisung gesamt",
            "Totaal netteruglevering",
        ),
        "backup_load_power": (
            "Backup Load Power",
            "Notstromlast-Leistung",
            "Noodstroombelasting-vermogen",
        ),
        "backup_load_cumulative_export_energy": (
            "Backup Load Total Output Energy",
            "Notstromlast Gesamtausgangsenergie",
            "Noodstroombelasting totale uitgangsenergie",
        ),
        "backup_load_cumulative_import_energy": (
            "Backup Load Total Input Energy",
            "Notstromlast Gesamteingangsenergie",
            "Noodstroombelasting totale ingangsenergie",
        ),
        "pv_total_cumulative_energy": (
            "PV Total Generated Energy",
            "PV-Gesamtenergie",
            "PV totale energie",
        ),
        "pv1_power": ("PV1 Power", "PV1-Leistung", "PV1-vermogen"),
        "pv1_cumulative_energy": (
            "PV1 Total Generated Energy",
            "PV1-Gesamtenergie",
            "PV1 totale energie",
        ),
        "pv2_power": ("PV2 Power", "PV2-Leistung", "PV2-vermogen"),
        "pv2_cumulative_energy": (
            "PV2 Total Generated Energy",
            "PV2-Gesamtenergie",
            "PV2 totale energie",
        ),
        "pv3_power": ("PV3 Power", "PV3-Leistung", "PV3-vermogen"),
        "pv3_cumulative_energy": (
            "PV3 Total Generated Energy",
            "PV3-Gesamtenergie",
            "PV3 totale energie",
        ),
        "pv4_power": ("PV4 Power", "PV4-Leistung", "PV4-vermogen"),
        "pv4_cumulative_energy": (
            "PV4 Total Generated Energy",
            "PV4-Gesamtenergie",
            "PV4 totale energie",
        ),
        "grid_charge_power_limit": (
            "Grid Charge Power Limit",
            "Netzladungsleistungsgrenze",
            "Netlaadvermogenslimiet",
        ),
        "battery_discharge_power_limit": (
            "Battery Discharge Power Limit",
            "Batterieentladungsleistungsgrenze",
            "Batterij-ontlaadvermogenslimiet",
        ),
    }
)

# Formulaic slot registers (1-8) are generated.
BASE_SLOT_TEMPLATES = {
    "start": (
        "Base Load Slot {n} Start Time",
        "Grundlast Zeitfenster {n} Startzeit",
        "Basislast tijdslot {n} starttijd",
    ),
    "end": (
        "Base Load Slot {n} End Time",
        "Grundlast Zeitfenster {n} Endzeit",
        "Basislast tijdslot {n} eindtijd",
    ),
    "power": (
        "Base Load Slot {n} Power",
        "Grundlast Zeitfenster {n} Leistung",
        "Basislast tijdslot {n} vermogen",
    ),
}
TOU_SLOT_TEMPLATES = {
    "start": (
        "Manual Charge/Discharge Strategy {n} Start Time",
        "Manuelle Lade-/Entladestrategie {n} Startzeit",
        "Handmatige laad-/ontlaadstrategie {n} starttijd",
    ),
    "end": (
        "Manual Charge/Discharge Strategy {n} End Time",
        "Manuelle Lade-/Entladestrategie {n} Endzeit",
        "Handmatige laad-/ontlaadstrategie {n} eindtijd",
    ),
    "mode": (
        "Manual Charge/Discharge Strategy {n} Work Mode",
        "Manuelle Lade-/Entladestrategie {n} Arbeitsmodus",
        "Handmatige laad-/ontlaadstrategie {n} werkmodus",
    ),
    "target_soc": (
        "Manual Charge/Discharge Strategy {n} Target SoC",
        "Manuelle Lade-/Entladestrategie {n} Ziel-SoC",
        "Handmatige laad-/ontlaadstrategie {n} doel-SoC",
    ),
    "power": (
        "Manual Charge/Discharge Strategy {n} Discharge Power",
        "Manuelle Lade-/Entladestrategie {n} Entladeleistung",
        "Handmatige laad-/ontlaadstrategie {n} ontlaadvermogen",
    ),
}

for _n in range(1, 9):
    for _field, _templates in BASE_SLOT_TEMPLATES.items():
        REGISTERS[f"base_load_slot{_n}_{_field}"] = tuple(
            value.format(n=_n) for value in _templates
        )
    for _field, _templates in TOU_SLOT_TEMPLATES.items():
        REGISTERS[f"tou_slot{_n}_{_field}"] = tuple(
            value.format(n=_n) for value in _templates
        )

# ---------------------------------------------------------------------------
# Bit entities: binary sensors split out of the v1 system_status bitmask
# ---------------------------------------------------------------------------
# The panel renders each bit as its own read-only row, so these codes need
# names and on/off labels in every language even though they are not registers.
# Each entry: code -> language -> (name, off label, on label).
BITS = {
    "system_status_standby": {
        "en": ("System–Standby", "Not in standby", "Standby"),
        "de": ("System–Standby", "Nicht im Standby", "Standby"),
        "nl": ("Systeem–Stand-by", "Niet in stand-by", "Stand-by"),
        "zh-Hans": ("系统-待机", "未待机", "待机中"),
    },
    "system_status_fault": {
        "en": ("System–Fault", "OK", "Fault"),
        "de": ("System–Fehler", "OK", "Fehler"),
        "nl": ("Systeem–Fout", "OK", "Storing"),
        "zh-Hans": ("系统-故障", "OK", "故障"),
    },
    "system_status_charging": {
        "en": ("System–Charging", "Not charging", "Charging"),
        "de": ("System–Laden", "Nicht ladend", "Ladend"),
        "nl": ("Systeem–Laden", "Niet aan het laden", "Aan het laden"),
        "zh-Hans": ("系统-充电中", "未充电", "充电中"),
    },
    "system_status_discharging": {
        "en": ("System–Discharging", "Not discharging", "Discharging"),
        "de": ("System–Entladen", "Nicht entladend", "Entladend"),
        "nl": ("Systeem–Ontladen", "Niet aan het ontladen", "Aan het ontladen"),
        "zh-Hans": ("系统-放电中", "未放电", "放电中"),
    },
}

# ---------------------------------------------------------------------------
# Home Assistant entity names (device page): code -> (en, de, nl, zh-Hans)
# ---------------------------------------------------------------------------
# Seeded from the names the integration shipped before the maps were merged, so
# existing device pages keep their wording.  Codes missing here fall back to
# the panel catalog (REGISTERS/BITS) below.
ENTITY_NAMES = {
    "fault_code": ("Fault Code", "Fehlercode", "Foutcode", "故障码"),
    "battery_voltage": ("Battery Voltage", "Batteriespannung", "Accuspanning", "电池电压"),
    "battery_soc": ("Battery SoC", "Batterie-SoC", "Accu-SoC", "电池 SOC"),
    "battery_design_capacity": (
        "Design Capacity",
        "Nennkapazität",
        "Ontwerpcapaciteit",
        "电池设计容量",
    ),
    "battery_cell_temp_max": (
        "Max. Cell Temperature",
        "Max. Zelltemperatur",
        "Max. celtemperatuur",
        "电芯最高温度",
    ),
    "battery_cell_temp_min": (
        "Min. Cell Temperature",
        "Min. Zelltemperatur",
        "Min. celtemperatuur",
        "电芯最低温度",
    ),
    "battery_cumulative_charge_energy": (
        "Total Charge Energy",
        "Gesamte Ladeenergie",
        "Totale laadenergie",
        "电池累计充电电量",
    ),
    "battery_cumulative_discharge_energy": (
        "Total Discharge Energy",
        "Gesamte Entladeenergie",
        "Totale ontlaadenergie",
        "电池累计放电电量",
    ),
    "grid_active_power": (
        "Grid Active Power",
        "Netz-Wirkleistung",
        "Net actief vermogen",
        "电网有功功率",
    ),
    "grid_frequency": ("Grid Frequency", "Netzfrequenz", "Netfrequentie", "电网频率"),
    "grid_cumulative_import_energy": (
        "Total Grid Import",
        "Gesamter Netzbezug",
        "Totale netafname",
        "累计电网取电电量",
    ),
    "grid_cumulative_export_energy": (
        "Total Grid Export",
        "Gesamte Netzeinspeisung",
        "Totale netinjectie",
        "累计电网馈电电量",
    ),
    "backup_load_power": ("Bypass Power", "Bypass-Leistung", "Bypass-vermogen", "旁路功率"),
    "backup_load_cumulative_export_energy": (
        "Total Bypass Output",
        "Gesamter Bypass-Ausgang",
        "Totale bypass-output",
        "旁路累计输出电量",
    ),
    "backup_load_cumulative_import_energy": (
        "Total Bypass Input",
        "Gesamter Bypass-Eingang",
        "Totale bypass-input",
        "旁路累计输入电量",
    ),
    "pv_total_power": (
        "Total PV Input Power",
        "PV-Gesamteingangsleistung",
        "Totaal PV-ingangsvermogen",
        "PV 总输入功率",
    ),
    "pv_total_cumulative_energy": (
        "Total PV Yield",
        "Gesamter PV-Ertrag",
        "Totale PV-opbrengst",
        "PV 累计总发电量",
    ),
    "pv1_power": ("PV1 Input Power", "PV1-Eingangsleistung", "PV1-ingangsvermogen", "PV1 输入功率"),
    "pv1_cumulative_energy": (
        "PV1 Total Yield",
        "PV1-Gesamtertrag",
        "PV1 totale opbrengst",
        "PV1 累计发电量",
    ),
    "pv2_power": ("PV2 Input Power", "PV2-Eingangsleistung", "PV2-ingangsvermogen", "PV2 输入功率"),
    "pv2_cumulative_energy": (
        "PV2 Total Yield",
        "PV2-Gesamtertrag",
        "PV2 totale opbrengst",
        "PV2 累计发电量",
    ),
    "pv3_power": ("PV3 Input Power", "PV3-Eingangsleistung", "PV3-ingangsvermogen", "PV3 输入功率"),
    "pv3_cumulative_energy": (
        "PV3 Total Yield",
        "PV3-Gesamtertrag",
        "PV3 totale opbrengst",
        "PV3 累计发电量",
    ),
    "pv4_power": ("PV4 Input Power", "PV4-Eingangsleistung", "PV4-ingangsvermogen", "PV4 输入功率"),
    "pv4_cumulative_energy": (
        "PV4 Total Yield",
        "PV4-Gesamtertrag",
        "PV4 totale opbrengst",
        "PV4 累计发电量",
    ),
    "system_status_standby": (
        "System–Standby",
        "System–Standby",
        "Systeem–Standby",
        "系统-待机",
    ),
    "system_status_fault": ("System–Fault", "System–Fehler", "Systeem–Fout", "系统-故障"),
    "system_status_charging": (
        "System–Charging",
        "System–Lädt",
        "Systeem–Opladen",
        "系统-充电中",
    ),
    "system_status_discharging": (
        "System–Discharging",
        "System–Entlädt",
        "Systeem–Ontladen",
        "系统-放电中",
    ),
    "grid_charge_power_limit": (
        "AC Charge Power Limit",
        "AC-Ladeleistungslimit",
        "AC-laadvermogenlimiet",
        "交流充电功率限制",
    ),
    "battery_discharge_power_limit": (
        "AC Discharge Power Limit",
        "AC-Entladeleistungslimit",
        "AC-Ontlaadvermogenlimiet",
        "交流放电功率限制",
    ),
    "backup_soc": ("Backup SoC", "Backup-SoC", "Back-up SoC", "备电 SOC"),
    "battery_target_power": (
        "Target Charge / Discharge Power",
        "Ziel-Lade-/Entladeleistung",
        "Doel laad-/ontlaadvermogen",
        "目标充放电功率",
    ),
    "battery_cutoff_soc": (
        "Charge / Discharge Cut-off SoC",
        "Lade-/Entlade-Abschalt-SoC",
        "Laad-/Ontlaad-uitschakel-SoC",
        "充放电截止 SOC",
    ),
    "off_grid_output_enable": (
        "Off-Grid Output Switch",
        "Off-Grid-Ausgangsschalter",
        "Off-grid uitgangsschakelaar",
        "离网输出开关",
    ),
    "pv_curtailment_enable": (
        "PV Curtailment Switch",
        "PV-Abregelungsschalter",
        "PV-curtailmentschakelaar",
        "PV 弃光开关",
    ),
}
ENTITY_LANG_INDEX = {lang: index for index, lang in enumerate(ALL_LANGS)}

# ---------------------------------------------------------------------------
# Enum values: code -> raw -> (en, de, nl)
# ---------------------------------------------------------------------------
VALUES = {
    "meter_connection_state": {
        "0": ("Paired & connected", "Gekoppelt & verbunden", "Gekoppeld & verbonden"),
        "1": (
            "Paired, not connected",
            "Gekoppelt, nicht verbunden",
            "Gekoppeld, niet verbonden",
        ),
        "2": (
            "Unpaired, not connected",
            "Nicht gekoppelt, nicht verbunden",
            "Niet gekoppeld, niet verbonden",
        ),
    },
    "battery_work_state": {
        "0": ("Idle", "Leerlauf", "Inactief"),
        "1": ("Charging", "Laden", "Laden"),
        "2": ("Discharging", "Entladen", "Ontladen"),
    },
    "bypass_switch_state": {
        "0": ("Off", "Aus", "Uit"),
        "1": ("On", "An", "Aan"),
    },
    "charge_discharge_direction": {
        "0": ("Idle", "Leerlauf", "Inactief"),
        "1": ("Charging", "Laden", "Laden"),
        "2": ("Discharging", "Entladen", "Ontladen"),
        "3": ("Exit", "Beenden", "Afsluiten"),
    },
    "work_mode": {
        "1": ("Self-consumption", "Eigenverbrauch", "Eigen verbruik"),
        "2": ("Manual schedule", "Manueller Zeitplan", "Handmatig schema"),
        "3": ("Idle", "Leerlauf", "Inactief"),
    },
    "allow_battery_export": {
        "0": (
            "Battery export disabled",
            "Batterieeinspeisung deaktiviert",
            "Accu-export uitgeschakeld",
        ),
        "1": (
            "Battery export enabled",
            "Batterieeinspeisung aktiviert",
            "Accu-export ingeschakeld",
        ),
    },
    "bypass_enable": {
        "0": ("Disabled", "Deaktiviert", "Uitgeschakeld"),
        "1": ("Enabled", "Aktiviert", "Ingeschakeld"),
    },
    "off_grid_output_enable": {
        "0": ("Disabled", "Deaktiviert", "Uitgeschakeld"),
        "1": ("Enabled", "Aktiviert", "Ingeschakeld"),
    },
    "pv_curtailment_enable": {
        "0": ("Disabled", "Deaktiviert", "Uitgeschakeld"),
        "1": ("Enabled", "Aktiviert", "Ingeschakeld"),
    },
    "generator_enable": {
        "0": ("Disabled", "Deaktiviert", "Uitgeschakeld"),
        "1": ("Enabled", "Aktiviert", "Ingeschakeld"),
    },
    "do1_state": {"0": ("Off", "Aus", "Uit"), "1": ("On", "An", "Aan")},
    "do2_state": {"0": ("Off", "Aus", "Uit"), "1": ("On", "An", "Aan")},
}
for _n in range(1, 9):
    VALUES[f"tou_slot{_n}_mode"] = {
        "0": ("Charge", "Laden", "Laden"),
        "1": ("Discharge", "Entladen", "Ontladen"),
    }

# Chinese labels for enums whose map labels are still protocol abbreviations
# ("idle"/"chg"/"disable").  Registers keep their Chinese map label otherwise.
ZH_VALUES = {
    "battery_work_state": {"0": "空闲", "1": "充电", "2": "放电"},
    "bypass_switch_state": {"0": "关", "1": "开"},
    "charge_discharge_direction": {
        "0": "空闲",
        "1": "充电",
        "2": "放电",
        "3": "退出",
    },
    "work_mode": {"3": "空闲"},
    "bypass_enable": {"0": "关闭", "1": "开启"},
    "off_grid_output_enable": {"0": "关闭", "1": "开启"},
    "pv_curtailment_enable": {"0": "关闭", "1": "开启"},
    "generator_enable": {"0": "关闭", "1": "开启"},
    "do1_state": {"0": "关", "1": "开"},
    "do2_state": {"0": "关", "1": "开"},
}

# ---------------------------------------------------------------------------
# UI strings
# ---------------------------------------------------------------------------
UI = {
    "en": {
        "title": "Conow Local Grouped Panel",
        "loadingRegisters": "Reading device registers…",
        "loadingMap": "Loading grouped map…",
        "errorDeviceNotFound": "Device not found or the integration is not loaded.",
        "errorUnknownCommand": (
            "Panel WebSocket commands are not registered — restart Home Assistant "
            "and open this page again."
        ),
        "addressHint": "Address {address} ({hex}) · {dtype}{length} · {access}",
        "addressAccessWritable": "writable",
        "addressAccessReadonly": "read-only",
        "invalidTimeHint": (
            "Device value {raw} is not a valid HH:MM time (00:00–23:59); it is "
            "hidden — set a new time before applying."
        ),
        "entityHint": "Click to open the details of {entity}",
        "valueOn": "On",
        "valueOff": "Off",
        "changedFromTo": "{name}: {old} → {new}",
        "changedSeparator": "; ",
        "codeSeparator": ", ",
        "groupHintInvalidTime": "Invalid time readings, set them again: {codes}",
        "groupHintOutOfRange": "Outside the allowed range, adjust: {codes}",
        "groupHintIncomplete": "Fill in every writable field",
        "groupHintUnchanged": "No changes",
        "noticeInvalidTimes": (
            "Found {count} time registers with invalid readings ({preview}{more}); "
            "their values are hidden — set new times in those groups before applying."
        ),
        "noticeInvalidTimesMore": ", …",
        "warningInvalidTime": "Invalid reading — set again",
        "noticeClamped": "{name} limited to {value} ({min}–{max})",
        "noticeTimeClamped": "Time limited to {value} (valid range 00:00–23:59)",
        "confirmWriteTitle": "Confirm write",
        "confirmWrite": "Write group “{group}” to the device?",
        "actionCancel": "Cancel",
        "actionConfirm": "Confirm",
        "noticeApplied": "{group}: sent",
        "noticeFailed": "{group}: {error}",
        "noticeRejected": (
            "{group}: the device refused the write ({error}). Check the values "
            "and try again."
        ),
        "actionApplying": "Sending…",
        "actionApply": "Apply group",
        "titleExpandGroup": "Expand group",
        "titleCollapseGroup": "Collapse group",
        "mapMismatchV1": (
            "Device firmware {firmware} is below {minimum}, which is required for "
            "the finalized register map (panel_registers.json); entities are read "
            "from registers.json (v1) and the grouped panel is unavailable."
        ),
        "mapUnreadable": (
            "No data could be read from the device. Check that it is online and "
            "that the serial or network connection is working."
        ),
        "mapUnreadableTcpDirect": (
            "No data could be read from the device. Check whether the IP address "
            "or port has changed and whether the verification code is still "
            "correct (Settings → Devices & services → Conow Local → Configure)."
        ),
        "emptyNoGroups": "No matching groups.",
        "comboNoMatch": "No matches",
        "modeTcpDirect": "TCP direct",
        "stateOffline": " (offline)",
        "stateUnloaded": " (not loaded)",
        "allGroups": "All groups",
        "allEntities": "All entities",
        "accessAll": "All (read/write)",
        "accessRw": "Writable only",
        "accessRo": "Read-only only",
        "selectDevice": "Select device…",
        "refresh": "Refresh",
        "pollInterval": "Poll interval",
        "pollIntervalOption": "{seconds} s",
        "noticePollInterval": "Poll interval set to {seconds} s.",
        "noticePollIntervalFailed": "Could not save the poll interval: {error}",
        "entityOption": "{name} ({code})",
        "unknownFirmware": "unknown",
    },
    "de": {
        "title": "Conow Local Gruppenpanel",
        "loadingRegisters": "Geräteregister werden gelesen…",
        "loadingMap": "Gruppierte Zuordnung wird geladen…",
        "errorDeviceNotFound": "Gerät nicht gefunden oder Integration nicht geladen.",
        "errorUnknownCommand": (
            "Panel-WebSocket-Befehle sind nicht registriert – starten Sie Home "
            "Assistant neu und öffnen Sie diese Seite erneut."
        ),
        "addressHint": "Adresse {address} ({hex}) · {dtype}{length} · {access}",
        "addressAccessWritable": "beschreibbar",
        "addressAccessReadonly": "nur lesen",
        "invalidTimeHint": (
            "Gerätewert {raw} ist keine gültige Uhrzeit (00:00–23:59); er wird "
            "ausgeblendet – stellen Sie vor dem Senden eine neue Zeit ein."
        ),
        "entityHint": "Klicken, um die Details von {entity} zu öffnen",
        "valueOn": "An",
        "valueOff": "Aus",
        "changedFromTo": "{name}: {old} → {new}",
        "changedSeparator": "; ",
        "codeSeparator": ", ",
        "groupHintInvalidTime": "Ungültige Zeitwerte, bitte erneut einstellen: {codes}",
        "groupHintOutOfRange": (
            "Außerhalb des zulässigen Bereichs, bitte anpassen: {codes}"
        ),
        "groupHintIncomplete": "Füllen Sie alle beschreibbaren Felder aus",
        "groupHintUnchanged": "Keine Änderungen",
        "noticeInvalidTimes": (
            "{count} Zeitregister mit ungültigen Werten gefunden ({preview}{more}); "
            "die Werte werden ausgeblendet – stellen Sie in diesen Gruppen neue "
            "Zeiten ein, bevor Sie senden."
        ),
        "noticeInvalidTimesMore": " usw.",
        "warningInvalidTime": "Ungültiger Wert – erneut einstellen",
        "noticeClamped": "{name} auf {value} begrenzt ({min}–{max})",
        "noticeTimeClamped": "Zeit auf {value} begrenzt (gültig 00:00–23:59)",
        "confirmWriteTitle": "Schreiben bestätigen",
        "confirmWrite": "Gruppe „{group}“ auf das Gerät schreiben?",
        "actionCancel": "Abbrechen",
        "actionConfirm": "Bestätigen",
        "noticeApplied": "{group}: gesendet",
        "noticeFailed": "{group}: {error}",
        "noticeRejected": (
            "{group}: Das Gerät hat das Schreiben abgelehnt ({error}). Prüfe "
            "die Werte und versuche es erneut."
        ),
        "actionApplying": "Wird gesendet…",
        "actionApply": "Gruppe senden",
        "titleExpandGroup": "Gruppe ausklappen",
        "titleCollapseGroup": "Gruppe einklappen",
        "mapMismatchV1": (
            "Die Gerätefirmware {firmware} ist niedriger als die für die "
            "endgültigen Registerzuordnung (panel_registers.json) erforderliche Version "
            "{minimum}; Entitäten werden aus registers.json (v1) gelesen und das "
            "Gruppenpanel ist nicht verfügbar."
        ),
        "mapUnreadable": (
            "Es konnten keine Gerätedaten gelesen werden. Prüfen Sie, ob das Gerät "
            "online ist und die serielle bzw. Netzwerkverbindung funktioniert."
        ),
        "mapUnreadableTcpDirect": (
            "Es konnten keine Gerätedaten gelesen werden. Prüfen Sie, ob sich "
            "IP-Adresse oder Port geändert haben und ob der Verifizierungscode noch "
            "stimmt (Einstellungen → Geräte & Dienste → Conow Local → Konfigurieren)."
        ),
        "emptyNoGroups": "Keine passenden Gruppen.",
        "comboNoMatch": "Keine Treffer",
        "modeTcpDirect": "TCP direkt",
        "stateOffline": " (offline)",
        "stateUnloaded": " (nicht geladen)",
        "allGroups": "Alle Gruppen",
        "allEntities": "Alle Entitäten",
        "accessAll": "Alle (lesen/schreiben)",
        "accessRw": "Nur beschreibbar",
        "accessRo": "Nur lesen",
        "selectDevice": "Gerät auswählen…",
        "refresh": "Aktualisieren",
        "pollInterval": "Abfrageintervall",
        "pollIntervalOption": "{seconds} s",
        "noticePollInterval": "Abfrageintervall auf {seconds} s gesetzt.",
        "noticePollIntervalFailed": "Abfrageintervall konnte nicht gespeichert werden: {error}",
        "entityOption": "{name} ({code})",
        "unknownFirmware": "unbekannt",
    },
    "nl": {
        "title": "Conow Local groepenpaneel",
        "loadingRegisters": "Apparaatregisters lezen…",
        "loadingMap": "Gegroepeerde map laden…",
        "errorDeviceNotFound": (
            "Apparaat niet gevonden of integratie niet geladen."
        ),
        "errorUnknownCommand": (
            "Paneel-WebSocket-opdrachten zijn niet geregistreerd — herstart Home "
            "Assistant en open deze pagina opnieuw."
        ),
        "addressHint": "Adres {address} ({hex}) · {dtype}{length} · {access}",
        "addressAccessWritable": "beschrijfbaar",
        "addressAccessReadonly": "alleen lezen",
        "invalidTimeHint": (
            "Apparaatwaarde {raw} is geen geldige tijd (00:00–23:59); deze is "
            "verborgen — stel een nieuwe tijd in voordat u verzendt."
        ),
        "entityHint": "Klik om de details van {entity} te openen",
        "valueOn": "Aan",
        "valueOff": "Uit",
        "changedFromTo": "{name}: {old} → {new}",
        "changedSeparator": "; ",
        "codeSeparator": ", ",
        "groupHintInvalidTime": "Ongeldige tijdwaarden, stel ze opnieuw in: {codes}",
        "groupHintOutOfRange": "Buiten het toegestane bereik, pas aan: {codes}",
        "groupHintIncomplete": "Vul alle beschrijfbare velden in",
        "groupHintUnchanged": "Geen wijzigingen",
        "noticeInvalidTimes": (
            "{count} tijdregisters met ongeldige waarden gevonden ({preview}{more}); "
            "de waarden zijn verborgen — stel in die groepen nieuwe tijden in "
            "voordat u verzendt."
        ),
        "noticeInvalidTimesMore": " enz.",
        "warningInvalidTime": "Ongeldige waarde — opnieuw instellen",
        "noticeClamped": "{name} beperkt tot {value} ({min}–{max})",
        "noticeTimeClamped": "Tijd beperkt tot {value} (geldig 00:00–23:59)",
        "confirmWriteTitle": "Schrijven bevestigen",
        "confirmWrite": "Groep “{group}” naar het apparaat schrijven?",
        "actionCancel": "Annuleren",
        "actionConfirm": "Bevestigen",
        "noticeApplied": "{group}: verzonden",
        "noticeFailed": "{group}: {error}",
        "noticeRejected": (
            "{group}: Het apparaat heeft de schrijfactie geweigerd ({error}). "
            "Controleer de waarden en probeer opnieuw."
        ),
        "actionApplying": "Verzenden…",
        "actionApply": "Groep verzenden",
        "titleExpandGroup": "Groep uitvouwen",
        "titleCollapseGroup": "Groep invouwen",
        "mapMismatchV1": (
            "Apparaatfirmware {firmware} is lager dan {minimum}, de vereiste versie "
            "voor de definitieve registermap (panel_registers.json); entiteiten worden "
            "uit registers.json (v1) gelezen en het groepenpaneel is niet beschikbaar."
        ),
        "mapUnreadable": (
            "Er konden geen apparaatgegevens worden gelezen. Controleer of het "
            "apparaat online is en of de seriële of netwerkverbinding werkt."
        ),
        "mapUnreadableTcpDirect": (
            "Er konden geen apparaatgegevens worden gelezen. Controleer of het "
            "IP-adres of de poort is gewijzigd en of de verificatiecode nog klopt "
            "(Instellingen → Apparaten & diensten → Conow Local → Configureren)."
        ),
        "emptyNoGroups": "Geen overeenkomende groepen.",
        "comboNoMatch": "Geen resultaten",
        "modeTcpDirect": "TCP direct",
        "stateOffline": " (offline)",
        "stateUnloaded": " (niet geladen)",
        "allGroups": "Alle groepen",
        "allEntities": "Alle entiteiten",
        "accessAll": "Alles (lezen/schrijven)",
        "accessRw": "Alleen beschrijfbaar",
        "accessRo": "Alleen lezen",
        "selectDevice": "Selecteer apparaat…",
        "refresh": "Vernieuwen",
        "pollInterval": "Poll-interval",
        "pollIntervalOption": "{seconds} s",
        "noticePollInterval": "Poll-interval ingesteld op {seconds} s.",
        "noticePollIntervalFailed": "Poll-interval opslaan mislukt: {error}",
        "entityOption": "{name} ({code})",
        "unknownFirmware": "onbekend",
    },
    "zh-Hans": {
        "title": "Conow Local 分组面板",
        "loadingRegisters": "读取设备寄存器…",
        "loadingMap": "加载分组表…",
        "errorDeviceNotFound": "设备不存在或集成未加载。",
        "errorUnknownCommand": (
            "面板 WebSocket 命令未注册 —— 请重启 Home Assistant 后再打开本页。"
        ),
        "addressHint": "地址 {address}（{hex}）· {dtype}{length} · {access}",
        "addressAccessWritable": "可写",
        "addressAccessReadonly": "只读",
        "invalidTimeHint": (
            "设备读数 {raw} 不是合法的时分（范围 00:00–23:59），已隐藏，"
            "请重新设置后下发"
        ),
        "entityHint": "点击查看 {entity} 的实体详情",
        "valueOn": "开",
        "valueOff": "关",
        "changedFromTo": "{name}：从 {old} 到 {new}",
        "changedSeparator": "；",
        "codeSeparator": "、",
        "groupHintInvalidTime": "时间读数非法，请重新设置：{codes}",
        "groupHintOutOfRange": "超出允许范围，请调整：{codes}",
        "groupHintIncomplete": "请填写完整所有可写字段",
        "groupHintUnchanged": "无改动",
        "noticeInvalidTimes": (
            "检测到 {count} 个时间寄存器读数非法（{preview}{more}），已隐藏原值；"
            "请在对应分组重新设置时间后再下发。"
        ),
        "noticeInvalidTimesMore": " 等",
        "warningInvalidTime": "读数非法，请重新设置",
        "noticeClamped": "{name} 已限制为 {value}（{min}–{max}）",
        "noticeTimeClamped": "时间已限制为 {value}（有效范围 00:00–23:59）",
        "confirmWriteTitle": "确认下发",
        "confirmWrite": "确认把分组「{group}」写入设备？",
        "actionCancel": "取消",
        "actionConfirm": "确认",
        "noticeApplied": "{group}：已下发",
        "noticeFailed": "{group}：{error}",
        "noticeRejected": (
            "{group}：设备拒绝了本次写入（{error}），请检查数值后重试。"
        ),
        "actionApplying": "下发中…",
        "actionApply": "批量下发",
        "titleExpandGroup": "展开分组",
        "titleCollapseGroup": "折叠分组",
        "mapMismatchV1": (
            "设备固件版本 {firmware}，低于启用定稿寄存器映射"
            "（panel_registers.json）所需的 {minimum}；已按 registers.json（v1）"
            "读取实体，分组面板不可用。"
        ),
        "mapUnreadable": (
            "读取不到设备数据。请检查设备是否在线、串口或网络连接是否正常。"
        ),
        "mapUnreadableTcpDirect": (
            "读取不到设备数据。请检查 IP、端口是否有变更，以及验证码是否已更新"
            "（设置 → 设备与服务 → Conow Local → 配置）。"
        ),
        "emptyNoGroups": "没有匹配的分组。",
        "comboNoMatch": "没有匹配项",
        "modeTcpDirect": "TCP 直连",
        "stateOffline": "（离线）",
        "stateUnloaded": "（未加载）",
        "allGroups": "全部分组",
        "allEntities": "全部实体",
        "accessAll": "全部读写",
        "accessRw": "仅可写",
        "accessRo": "仅只读",
        "selectDevice": "选择设备…",
        "refresh": "刷新",
        "pollInterval": "轮询间隔",
        "pollIntervalOption": "{seconds} 秒",
        "noticePollInterval": "轮询间隔已设为 {seconds} 秒。",
        "noticePollIntervalFailed": "轮询间隔保存失败：{error}",
        "entityOption": "{name}（{code}）",
        "unknownFirmware": "未知",
    },
}


def _localized_value(
    code: str, raw: int, lang: str, fallback: str
) -> str:
    """Return the catalog translation of one enum label, if it exists."""
    if lang == "zh-Hans":
        return ZH_VALUES.get(code, {}).get(str(raw), fallback)
    options = VALUES.get(code)
    if options is not None and str(raw) in options:
        return options[str(raw)][LANGS.index(lang)]
    return fallback


def _entity_name(code: str, lang: str, zh_registers: dict[str, str]) -> str:
    """Return the device-page name of an entity in one language."""
    if code in ENTITY_NAMES:
        return ENTITY_NAMES[code][ENTITY_LANG_INDEX[lang]]
    if code in BITS:
        return BITS[code][lang][0]
    if code in REGISTERS:
        if lang == "zh-Hans":
            return zh_registers.get(code, code)
        return REGISTERS[code][LANGS.index(lang)]
    raise SystemExit(f"Missing entity name for {code} ({lang})")


def _load_maps() -> tuple[dict, dict]:
    v1 = json.loads(registry.map_path(registry.MAP_V1).read_text(encoding="utf-8"))
    v2 = json.loads(registry.map_path(registry.MAP_V2).read_text(encoding="utf-8"))
    return v1, v2


def _write_entity_sections(
    sections: dict[str, dict[str, dict]], lang: str
) -> None:
    """Replace the entity section, preserving config/exceptions verbatim.

    English is written to both ``strings.json`` (the source catalog) and
    ``translations/en.json`` (what Home Assistant actually loads at runtime).
    """
    sources = [COMPONENT_DIR / "translations" / f"{lang}.json"]
    if lang == "en":
        sources.insert(0, COMPONENT_DIR / "strings.json")
    for path in sources:
        existing = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        )
        payload = {
            "exceptions": existing.get("exceptions", {}),
            "config": existing.get("config", {}),
            "options": existing.get("options", {}),
            "entity": sections[lang],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    v1, v2 = _load_maps()
    entries = {
        item["code"]: item
        for item in (*v1["registers"], *v2["registers"])
    }
    all_codes = [item["code"] for item in v2["registers"]] + [
        item["code"]
        for item in v1["registers"]
        if item["code"] not in {reg["code"] for reg in v2["registers"]}
    ]
    group_ids = [item["id"] for item in v2["groups"]] + [
        item["id"]
        for item in v1["groups"]
        if item["id"] not in {group["id"] for group in v2["groups"]}
    ]

    # Chinese: names/labels/enums come straight from the maps (v2 wins).
    zh_registers = {item["code"]: item["name"] for item in v1["registers"]}
    zh_registers.update({item["code"]: item["name"] for item in v2["registers"]})
    zh_groups = {item["id"]: item["label"] for item in v1["groups"]}
    zh_groups.update({item["id"]: item["label"] for item in v2["groups"]})

    missing = [code for code in all_codes if code not in REGISTERS]
    if missing:
        raise SystemExit(f"Missing register translations: {missing}")
    unknown = [code for code in REGISTERS if code not in entries]
    if unknown:
        raise SystemExit(f"Unknown register translations: {unknown}")
    missing_groups = [group for group in group_ids if group not in GROUPS]
    if missing_groups:
        raise SystemExit(f"Missing group translations: {missing_groups}")
    for code, item in entries.items():
        if item.get("values") and code not in VALUES:
            raise SystemExit(f"Missing enum translations: {code}")
    spec_codes = {
        spec.code
        for map_version in (registry.MAP_V1, registry.MAP_V2)
        for spec in entity_model.build_entity_specs(map_version)
    }
    for code in BITS:
        if code not in spec_codes:
            raise SystemExit(f"Bit translation without an entity: {code}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    zh_values = {
        code: {str(raw): label for raw, label in item["values"].items()}
        for code, item in entries.items()
        if item.get("values")
    }
    for code, labels in ZH_VALUES.items():
        zh_values.setdefault(code, {}).update(labels)
    for code, translations in BITS.items():
        name, off_label, on_label = translations["zh-Hans"]
        zh_registers[code] = name
        zh_values[code] = {"0": off_label, "1": on_label}
    zh_payload = {
        "language": "zh-Hans",
        "ui": UI["zh-Hans"],
        "groups": zh_groups,
        "subgroups": {"slot": "时段 {n}", "strategy": "策略 {n}"},
        "registers": zh_registers,
        "values": zh_values,
    }
    (OUT_DIR / "zh-Hans.json").write_text(
        json.dumps(zh_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for index, lang in enumerate(LANGS):
        registers_out = {code: REGISTERS[code][index] for code in all_codes}
        groups_out = {group: GROUPS[group][index] for group in group_ids}
        values_out = {
            code: {raw: labels[index] for raw, labels in options.items()}
            for code, options in VALUES.items()
        }
        for code, translations in BITS.items():
            name, off_label, on_label = translations[lang]
            registers_out[code] = name
            values_out[code] = {"0": off_label, "1": on_label}
        payload = {
            "language": lang,
            "ui": UI[lang],
            "groups": groups_out,
            "subgroups": SUBGROUPS[lang],
            "registers": registers_out,
            "values": values_out,
        }
        (OUT_DIR / f"{lang}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Home Assistant device-page strings, one section per platform.
    # ------------------------------------------------------------------
    specs_by_code = {}
    for map_version in (registry.MAP_V1, registry.MAP_V2):
        for spec in entity_model.build_entity_specs(map_version):
            previous = specs_by_code.setdefault(spec.code, spec)
            if previous.platform != spec.platform:
                raise SystemExit(
                    f"{spec.code}: platform {previous.platform} on one map, "
                    f"{spec.platform} on {map_version}"
                )

    sections_by_lang: dict[str, dict[str, dict[str, dict]]] = {}
    for lang in ALL_LANGS:
        sections: dict[str, dict[str, dict]] = {
            platform: {}
            for platform in (
                "sensor",
                "binary_sensor",
                "number",
                "select",
                "switch",
                "time",
            )
        }
        for code, spec in specs_by_code.items():
            entry: dict[str, object] = {
                "name": _entity_name(code, lang, zh_registers)
            }
            if spec.platform == "binary_sensor":
                bit_labels = BITS.get(code)
                if bit_labels is not None:
                    entry["state"] = {
                        "on": bit_labels[lang][2],
                        "off": bit_labels[lang][1],
                    }
                elif code in VALUES and set(VALUES[code]) == {"0", "1"}:
                    map_labels = spec.register.values or {}
                    entry["state"] = {
                        "on": _localized_value(
                            code, 1, lang, map_labels.get(1, "on")
                        ),
                        "off": _localized_value(
                            code, 0, lang, map_labels.get(0, "off")
                        ),
                    }
            register = spec.register
            if (
                spec.platform == "sensor"
                and register.device_class == "enum"
                and register.values
            ):
                entry["state"] = {
                    label: _localized_value(code, raw, lang, label)
                    for raw, label in register.values.items()
                }
            sections[spec.platform][code] = entry
        # Stable, reviewable ordering inside every platform section.
        sections = {
            platform: dict(sorted(entries.items()))
            for platform, entries in sections.items()
        }
        sections_by_lang[lang] = sections

    for lang in ALL_LANGS:
        _write_entity_sections(sections_by_lang, lang)

    print(
        f"Wrote {len(all_codes)} register names, {len(group_ids)} groups and "
        f"{len(specs_by_code)} entity names to {COMPONENT_DIR}"
    )


if __name__ == "__main__":
    main()
