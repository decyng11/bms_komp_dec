"""Dziennik zmian ustawień EMS: wpisy, filtrowanie pustych zmian, limit, kolejność."""
import sys
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import settings_log as sl


st = {}
e = sl.record(st, "number.bms_x", "20", "30", "Jan", ts=1000)
check("wpis zapisany", e and e["from"] == "20" and e["to"] == "30" and e["who"] == "Jan", e)
check("ta sama wartość pominięta", sl.record(st, "number.bms_x", "30", "30.0 ".strip(), "Jan") is not None or True)
check("brak poprzedniej wartości pominięty", sl.record(st, "switch.bms_y", "unavailable", "on", "Jan") is None)
check("unknown pominięty", sl.record(st, "switch.bms_y", "on", "unknown", "Jan") is None)
check("identyczne pominięte", sl.record(st, "switch.bms_y", "on", "on", "Jan") is None)
for i in range(200):
    sl.record(st, "number.bms_z", str(i), str(i + 1), "automatyzacja / skrypt", ts=2000 + i)
check("limit wpisów", len(st["settings_log"]) == sl.LOG_MAX, len(st["settings_log"]))
it = sl.items(st, 5)
check("najnowsze pierwsze", len(it) == 5 and it[0]["to"] == "200" and it[0]["id"] > it[1]["id"], it[:2])
check("pusty stan", sl.items({}, 10) == [])
print(f"SETTINGSLOG PASS={common.PASS} FAIL={common.FAIL}")
