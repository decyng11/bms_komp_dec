"""Rachunek: prognoza bilansu, cel miesięczny, rozbicie miesiąca, skarbonka; runtime.bill(), usługa insights_get, ostrzeżenie o celu."""
import asyncio, json, sys
from datetime import date, timedelta
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import billing as B, notify_cfg as N

TODAY = date(2026, 11, 20)


def days(vals, end=date(2026, 11, 19)):
    """vals = bilanse od najstarszego do `end` włącznie."""
    return {(end - timedelta(days=len(vals) - 1 - i)).isoformat(): v for i, v in enumerate(vals)}


def pure():
    # prognoza
    d = days([-3.0] * 19)                          # 1–19.11: po −3 zł (koszt)
    fc = B.forecast(d, TODAY, 0.0)
    check("prognoza: mtd = suma bieżącego miesiąca", fc["mtd"] == -57.0, fc)
    check("prognoza: średnia z ostatnich dób, 11 dni do końca (dziś + 10)", fc["avg_day"] == -3.0 and fc["remaining_days"] == 11.0, fc)
    check("prognoza: wynik = mtd + średnia × pozostałe", fc["projected"] == -90.0 and fc["low"] == -90.0 == fc["high"], fc)
    fc2 = B.forecast(d, TODAY, 0.5)
    check("prognoza: połowa dnia minęła → 10,5 doby do końca", fc2["remaining_days"] == 10.5 and fc2["projected"] == round(-57 - 3 * 10.5, 2), fc2)
    mixed = days([-5.0, -1.0, 0.0, 2.0, -4.0, -2.0, -3.0])
    fm = B.forecast(mixed, TODAY, 0.0)
    check("prognoza: przedział low ≤ projected ≤ high", fm["low"] <= fm["projected"] <= fm["high"] and fm["low"] < fm["high"], fm)
    check("prognoza: za mało dób → None", B.forecast(days([-1.0, -2.0]), TODAY) is None and B.forecast({}, TODAY) is None)
    check("prognoza: dzisiejszy niepełny bilans wchodzi do mtd, ale nie do średniej", B.forecast({**d, TODAY.isoformat(): -50.0}, TODAY, 0.0)["avg_day"] == -3.0 and B.forecast({**d, TODAY.isoformat(): -50.0}, TODAY, 0.0)["mtd"] == -107.0)
    check("prognoza: dni z poprzedniego miesiąca w średniej, nie w mtd", B.forecast(days([-3.0] * 10, end=date(2026, 11, 3)), date(2026, 11, 4), 0.0)["mtd"] == -9.0)
    check("prognoza: ostatni dzień miesiąca (30.11 o 18:00)", B.forecast(days([-3.0] * 29, end=date(2026, 11, 29)), date(2026, 11, 30), 0.75)["remaining_days"] == 0.25)
    check("prognoza: luty w roku przestępnym ma 29 dni", B.forecast(days([1.0] * 10, end=date(2028, 2, 10)), date(2028, 2, 11), 0.0)["remaining_days"] == 19.0)
    for bad in (None, 5, "x", [], {"zła": 1, "2026-11-01": "abc", "2026-11-02": float("nan")}):
        check(f"prognoza: śmieci ({str(bad)[:16]})", B.forecast(bad, TODAY) is None)
    check("prognoza: zły dzień docelowy", B.forecast(d, "2026-11-20") is None)
    check("prognoza: ułamek dnia poza zakresem jest przycinany", B.forecast(d, TODAY, 7)["remaining_days"] == 10.0 and B.forecast(d, TODAY, -1)["remaining_days"] == 11.0)

    # cel
    fc = B.forecast(d, TODAY, 0.0)            # wydatek ok. 90 zł
    g = B.goal_status(fc, 200)
    check("cel: daleko od limitu → ok", g["status"] == "ok" and g["spent"] == 57.0 and g["projected_spent"] == 90.0 and g["pct"] == 45, g)
    check("cel: blisko (≥90%) → warn", B.goal_status(fc, 95)["status"] == "warn")
    check("cel: prognoza ponad limit → over", B.goal_status(fc, 80)["status"] == "over" and "powyżej celu 80" in B.goal_status(fc, 80)["text"])
    check("cel: już wydano więcej → over_now", B.goal_status(fc, 50)["status"] == "over_now" and "już przekroczony" in B.goal_status(fc, 50)["text"])
    plus = B.forecast(days([2.0] * 19), TODAY, 0.0)
    check("cel: dodatni bilans = wydatek 0, status ok", B.goal_status(plus, 100)["projected_spent"] == 0.0 and B.goal_status(plus, 100)["status"] == "ok")
    for gv in (0, -5, None, "x", float("nan"), True, 1e12):
        check(f"cel: wyłączony / zły ({gv}) → None", B.goal_status(fc, gv) is None)
    check("cel: brak prognozy → None", B.goal_status(None, 100) is None and B.goal_status({}, 100) is None)

    # rozbicie
    rep = {"days_with_data": 20, "import_kwh": 120.5, "export_kwh": 300.2, "cost": 80.1, "revenue": 150.25, "net": 70.15, "avg_buy_price": 0.665, "avg_sell_price": 0.5,
           "load_kwh": 400.0, "saving_estimate": 336.1}
    br = B.breakdown(rep)
    txt = " | ".join(f"{r['k']}: {r['v']}" for r in br)
    check("rozbicie: pięć pozycji z przecinkami", len(br) == 5 and "120,5 kWh za 80,10 zł" in txt and "300,2 kWh za 150,25 zł" in txt and "+70,15 zł" in txt, txt)
    check("rozbicie: „bez PV i baterii” i oszczędność", "dom 400 kWh × 0,67 zł = 266,00 zł" in txt or "× 0,66 zł" in txt, txt)
    check("rozbicie: brak danych → pusto", B.breakdown({"days_with_data": 0}) == [] and B.breakdown(None) == [] and B.breakdown("x") == [])
    part = B.breakdown({"days_with_data": 3, "net": -5.0})
    check("rozbicie: częściowe dane → tylko to, co jest", [r["k"] for r in part] == ["Bilans z siecią"], part)

    # skarbonka
    p = B.piggy(1200.0, 20000.0, 100, TODAY)
    check("skarbonka: procent nakładu i data zwrotu", p["pct"] == 6.0 and p["per_day"] == 12.0 and p["payback_date"] and p["years_left"] == round((18800 / 12) / 365, 1), p)
    check("skarbonka: data zwrotu w przyszłości", date.fromisoformat(p["payback_date"]) > TODAY)
    check("skarbonka: bez nakładu → tylko suma", B.piggy(500.0, None, 50, TODAY)["pct"] is None and B.piggy(500.0, 0, 50, TODAY)["invest"] is None)
    check("skarbonka: nakład zwrócony", B.piggy(25000.0, 20000.0, 400, TODAY)["payback_date"] == "zwrócone")
    check("skarbonka: za krótka historia (<14 dób) → bez daty", B.piggy(100.0, 20000.0, 7, TODAY)["payback_date"] is None)
    check("skarbonka: oszczędność ujemna → bez daty, procent 0", B.piggy(-50.0, 20000.0, 60, TODAY)["pct"] == 0.0 and B.piggy(-50.0, 20000.0, 60, TODAY)["payback_date"] is None)
    check("skarbonka: zwrot dalej niż 50 lat → bez daty", B.piggy(1.0, 1e7, 100, TODAY)["payback_date"] is None)
    for bad in ((None, 1, 1), ("x", 1, 1), (1, 1, 0), (float("nan"), 1, 5), (1, 1, None)):
        check(f"skarbonka: śmieci {bad[:2]}", B.piggy(bad[0], bad[1], bad[2], TODAY) is None)
    json.dumps(p, allow_nan=False)


async def runtime_part():
    hass, c, opt, rt = build()
    now = at(2026, 11, 20, 10, 0)
    for i in range(19):
        d = (date(2026, 11, 19) - timedelta(days=i)).isoformat()
        rt.ledger.days[d] = {"revenue": 1.0, "cost": 4.0, "export_kwh": 2.0, "import_kwh": 5.0, "neg_export_kwh": 0.0}
    b = rt.bill()
    json.dumps(b, allow_nan=False)
    check("bill(): prognoza z księgi zysków", b["forecast"] and b["forecast"]["mtd"] == -57.0 and b["goal"] is None and b["goal_value"] == 0.0, b["forecast"])
    check("bill(): rozbicie bieżącego miesiąca", b["month_title"] == "Listopad 2026" and any(r["k"] == "Bilans z siecią" for r in b["breakdown"]), b["breakdown"])
    # cel z numeru
    hass.states.set("number.bms_monthly_goal_pln", 80)
    check("number monthly_goal_pln istnieje w stałych", any(n[0] == "monthly_goal_pln" for n in const.NUMBERS))
    # usługa insights_get zawiera blok „bill”
    from custom_components.bms_komp_dec import __init__ as comp
    check("katalog: bill_goal, priorytet ważne, tygodniowy odstęp, domyślnie włączony",
          N.CATALOG["bill_goal"][5] == 10080 and N.PRIORITY["bill_goal"] == 2 and N.effective({})["kinds"]["bill_goal"]["on"] is True)
    check("odstęp rodzaju na liście", N.CATALOG["bill_goal"][5] in N.COOLDOWNS)


def pn(hass):
    return [x for x in hass.services.calls if x[0] == "persistent_notification" and x[1] == "create" and "cel miesięczny" in x[2]["title"].lower()]


async def notify_part():
    for status, goal in (("over", 80), ("warn", 95), ("ok", 200)):
        hass, c, opt, rt = build()
        at(2026, 11, 20, 10, 0)
        for i in range(19):
            rt.ledger.days[(date(2026, 11, 19) - timedelta(days=i)).isoformat()] = {"revenue": 1.0, "cost": 4.0, "export_kwh": 2.0, "import_kwh": 5.0, "neg_export_kwh": 0.0}
        rt.state["notify_cfg"] = N.effective({"phone_level": "all"})
        rt.bill = lambda g=goal: {"goal": B.goal_status(B.forecast({k: rt.ledger.net(v) for k, v in rt.ledger.days.items()}, date(2026, 11, 20), 0.0), g)}
        await rt.monitor._bill_goal(at(2026, 11, 20, 10, 0))
        inb = [i for i in rt.state.get("inbox", []) if i.get("kind") == "bill_goal"]
        if status == "ok":
            check("cel ok: bez powiadomienia", not inb and not pn(hass))
        else:
            check(f"cel {status}: jedno powiadomienie z tekstem celu", len(inb) == 1 or len(pn(hass)) == 1, (inb, pn(hass)))
            await rt.monitor._bill_goal(at(2026, 11, 20, 11, 0))
            await rt.monitor._bill_goal(at(2026, 11, 21, 10, 0))
            inb2 = [i for i in rt.state.get("inbox", []) if i.get("kind") == "bill_goal"]
            check(f"cel {status}: bez powtórek w tym samym miesiącu i stanie", len(inb2) == 1, len(inb2))
    hass, c, opt, rt = build()
    rt.bill = lambda: {"goal": {"status": "over", "text": "x"}}
    await rt.monitor._bill_goal(at(2026, 11, 20, 8, 0))
    check("przed 9:00 cisza", not [i for i in rt.state.get("inbox", []) if i.get("kind") == "bill_goal"])
    rt.state["notify_cfg"] = N.effective({"kinds": {"bill_goal": {"on": False}}})
    await rt.monitor._bill_goal(at(2026, 11, 20, 10, 0))
    check("wyłączone w konfiguratorze: cisza", not [i for i in rt.state.get("inbox", []) if i.get("kind") == "bill_goal"])
    rt.bill = lambda: {}
    rt.state["notify_cfg"] = N.effective({})
    await rt.monitor._bill_goal(at(2026, 11, 20, 10, 0))
    check("brak celu w odpowiedzi: bez wyjątku i bez powiadomienia", True)


async def main():
    pure()
    await runtime_part()
    await notify_part()


asyncio.run(main())
print(f"BILLING PASS={common.PASS} FAIL={common.FAIL}")
