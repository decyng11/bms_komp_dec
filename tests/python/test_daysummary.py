"""Podsumowanie dnia: plan kontra wykonanie (prognoza PV, sprzedaż), zabezpieczenia, energia z sieci w baterii."""
import sys
import common
sys.path.insert(0, ".")
from common import *   # noqa
from homeassistant.util import dt as dt_util

hass, c, opt, rt = build()
d = dt_util.now().date(); key = d.isoformat()
c.data = {"energy_pv_today": 4.1}
rt.insights.fc[key] = {"pv_fc": 3.6}
rt.state["sale_plan"] = {key: {"kwh": 3.0, "gross": 2.4, "net": 0.9}}
rt.state["sale_actual"] = {key: {"kwh": 2.6, "rev": 2.05}}
rt.state["grid_batt"] = {"kwh": 1.2}
rt.log.add("guard", "Zatrzymuję sprzedaż: test", "warn")
rt.log.add("auto", "Auto-zastosowano 2 zmian(y)", "ok")
lines = rt._plan_vs_actual_lines(d)
txt = "\n".join(lines)
check("PV: prognoza i wykonanie z odchyleniem", "PV: prognoza 3,6 kWh, wykonanie 4,1 kWh (+14%)" in txt, txt)
check("sprzedaż: plan i wykonanie", "plan ~3,0 kWh / 2,40 zł" in txt and "2,6 kWh / 2,05 zł" in txt, txt)
check("zabezpieczenia i zmiany automatu", "Zabezpieczenia zadziałały: 1×, zmiany automatu: 1×" in txt, txt)
check("energia z sieci w baterii", "~1,2 kWh energii z sieci" in txt, txt)
full = rt.summary_text("day", d)
check("wiersze są w podsumowaniu dnia", "PV: prognoza 3,6 kWh" in full, full)
hass, c, opt, rt = build()
check("brak danych: bez dodatkowych wierszy i bez błędu", rt._plan_vs_actual_lines(d) == [], rt._plan_vs_actual_lines(d))
print(f"DAYSUMMARY PASS={common.PASS} FAIL={common.FAIL}")
