"""0.8.8: dziennik decyzji planu — wpis „Plan: …” tylko przy zmianie decyzji, z powodem."""
import asyncio, sys
sys.path.insert(0, ".")
from common import *   # noqa
import common

def P(start=None, stop=None, skip=False, reason=""):
    return {"proposed": start, "skip": skip, "reason": reason, "current": "—", "label": "x"}

def plan_entries(rt): return [e for e in reversed(rt.log.last(200)) if e.get("kind") == "plan"]   # od najstarszego

async def main():
    hass, c, opt, rt = build()
    plan = {"proposals": {
        "start_grid_charge": P("22:00", reason="Doładuj ~4.0 kWh z sieci (22:00–06:00, najtańsza taryfa nocna)."), "stop_grid_charge": P("06:00"),
        "start_grid_charge_2": P(skip=True, reason="Pomiń — okno nocne wystarcza"), "stop_grid_charge_2": P(skip=True),
        "bateria_sprzedaz_start_2": P(skip=True, reason="Pomiń — okno 1 h: po sprzedaży 18–19 bateria spadłaby do ~12% przed świtem"), "bateria_sprzedaz_stop_2": P(skip=True),
    }}
    rt._log_plan_decisions(plan)
    e = plan_entries(rt)
    check("pierwszy plan: wpisy dla trzech decyzji", len(e) == 3, [x["msg"] for x in e])
    msgs = " | ".join(x["msg"] for x in e)
    check("ładowanie z sieci: godziny i powód", "Plan: ładowanie z sieci (noc) 22:00–06:00" in msgs and "Doładuj ~4.0 kWh" in msgs, msgs)
    check("sprzedaż pominięta: powód z planera", "sprzedaż z baterii (zestaw 2) — pomijam: okno 1 h" in msgs and "przed świtem" in msgs, msgs)
    check("zestaw 2 ładowania: pominięty z powodem", "ładowanie z sieci (zestaw 2) — pomijam: okno nocne wystarcza" in msgs, msgs)
    check("grupy bez wpisu w planie nie dają wpisów (blokada PV, sprzedaż 1)", "blokada" not in msgs and "zestaw 1" not in msgs)
    # ten sam plan → bez nowych wpisów (nawet gdy zmieni się tekst powodu)
    plan["proposals"]["start_grid_charge"]["reason"] = "Doładuj ~4.1 kWh z sieci (22:00–06:00)"
    rt._log_plan_decisions(plan)
    check("ten sam plan: bez nowych wpisów", len(plan_entries(rt)) == 3)
    # zmiana godziny → nowy wpis
    plan["proposals"]["start_grid_charge"]["proposed"] = "23:00"
    rt._log_plan_decisions(plan)
    e = plan_entries(rt)
    check("zmiana godziny startu: jeden nowy wpis", len(e) == 4 and "23:00–06:00" in e[-1]["msg"], e[-1]["msg"])
    check("zmiana oznaczona jako zmiana (extra.changed)", (e[-1].get("extra") or {}).get("changed") is True and (e[0].get("extra") or {}).get("changed") in (None, False), [x.get("extra") for x in e])
    # z ładowania na pominięcie → wpis „pomijam”
    plan["proposals"]["start_grid_charge"].update({"proposed": None, "skip": True, "reason": "Pomiń — bateria wystarczy do rana (SOC 70% o 06:00)"})
    rt._log_plan_decisions(plan)
    e = plan_entries(rt)
    check("z ładowania na pominięcie: wpis z powodem", len(e) == 5 and "pomijam: bateria wystarczy do rana" in e[-1]["msg"], e[-1]["msg"])
    # powrót ładowania
    plan["proposals"]["start_grid_charge"].update({"proposed": "22:00", "skip": False, "reason": ""})
    rt._log_plan_decisions(plan)
    check("powrót ładowania: wpis bez powodu też działa", len(plan_entries(rt)) == 6 and plan_entries(rt)[-1]["msg"].endswith("22:00–06:00"), plan_entries(rt)[-1]["msg"])
    # odporność
    for bad in (None, {}, {"proposals": None}, {"proposals": {"start_grid_charge": "zły"}}):
        try:
            rt._log_plan_decisions(bad); okk = True
        except Exception:   # noqa: BLE001
            okk = False
        check(f"odporność: {str(bad)[:40]}", okk)
    # długi powód jest przycięty
    plan["proposals"]["bateria_sprzedaz_start_2"]["reason"] = "Pomiń — " + "x" * 900
    plan["proposals"]["bateria_sprzedaz_start_2"]["proposed"] = None
    rt.state["plan_sig"].pop("sprzedaż z baterii (zestaw 2)", None)
    rt._log_plan_decisions(plan)
    check("długi powód przycięty do 260 znaków", len(plan_entries(rt)[-1]["msg"]) < 340, len(plan_entries(rt)[-1]["msg"]))
    # integracja: refresh planu wpisuje do dziennika
    import inspect
    from custom_components.bms_komp_dec import runtime
    check("refresh planu wywołuje _log_plan_decisions", "_log_plan_decisions(self._plan)" in inspect.getsource(runtime.BmsRuntime))
    print(f"PLANDEC PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)

asyncio.run(main())
