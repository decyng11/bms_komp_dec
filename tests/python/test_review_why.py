"""„Dlaczego nie sprzedał” w ocenie planu i linia z oceną w raporcie tygodniowym."""
import asyncio, sys
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import review as RV, tariff as tar


def ent(ts, kind, msg):
    return {"ts": ts, "kind": kind, "level": "warn", "msg": msg}


def pure():
    day = "2026-11-19"
    log = [ent("2026-11-19T19:05:00+01:00", "schedule", "Pominięto sprzedaz_6000w: zakaz sprzedaży — dziś pobrano z sieci 6.0 kWh > limit 5.0 kWh"),
           ent("2026-11-19T17:00:00+01:00", "guard", "Sprzedaż 6000 W (ręcznie) ZABLOKOWANA: tryb burzowy"),
           ent("2026-11-18T18:00:00+01:00", "guard", "Zatrzymuję sprzedaż: SOC 15% < minimalny SOC 20%")]
    w = RV.sale_reason(log, day)
    check("powód: najnowszy wpis z tej doby wygrywa", w and w["text"].startswith("dziś pobrano z sieci") and w["at"] == "19:05" and w["n"] == 2, w)
    check("powód: wpis z innej doby jest pomijany", RV.sale_reason([log[2]], day) is None)
    w = RV.sale_reason([ent("2026-11-19T18:00:00+01:00", "guard", "Zatrzymuję sprzedaż: SOC 15% < minimalny SOC 20%; arbitraż")], day)
    check("powód: zatrzymanie sprzedaży", w and "SOC 15%" in w["text"] and w["source"] == "log", w)
    w = RV.sale_reason([ent("2026-11-19T18:00:00+01:00", "price", "cena RCE wróciła do 0.300 PLN/kWh; nie wznawiam sprzedaży: tryb burzowy")], day)
    check("powód: nie wznawiam sprzedaży", w and w["text"] == "tryb burzowy", w)
    check("powód: inne rodzaje wpisów i śmieci ignorowane", RV.sale_reason([ent("2026-11-19T18:00:00+01:00", "command", "ZABLOKOWANA: x"), None, {"ts": 5, "kind": "guard", "msg": "ZABLOKOWANA: y"}, "x"], day) is None)
    check("powód: brak listy → None", RV.sale_reason(None, day) is None and RV.sale_reason([], day) is None)
    long_msg = "Sprzedaż (auto) ZABLOKOWANA: " + "x" * 500
    check("powód: tekst przycięty", len(RV.sale_reason([ent("2026-11-19T18:00:00+01:00", "guard", long_msg)], day)["text"]) <= RV.WHY_MAX_LEN)
    w = RV.sale_reason([], day, soc_max=38, min_soc=50)
    check("powód z SOC, gdy dziennik milczy", w and w["source"] == "soc" and "38%" in w["text"] and "50%" in w["text"], w)
    check("brak powodu z SOC, gdy bateria dobiła do progu", RV.sale_reason([], day, soc_max=80, min_soc=50) is None)
    check("próg 0 → brak powodu z SOC", RV.sale_reason([], day, soc_max=10, min_soc=0) is None)

    # pozycja sprzedaży z powodem
    plan, act = {"kwh": 4.0}, {"kwh": 0.5}
    r = RV.build(day, sale_plan=plan, sale_act=act, sale_why={"text": "tryb burzowy", "at": "19:05", "n": 3})
    it = next(i for i in r["items"] if i["id"] == "sale")
    check("pozycja: powód w tekście i szczegółach", "Powód: tryb burzowy o 19:05 (łącznie 3×)" in it["text"] and "powód: tryb burzowy" in it["detail"] and it["why"] == "tryb burzowy", it)
    check("pozycja: powód widać w „co zawiodło”", r["culprit"] and "tryb burzowy" in r["culprit"]["text"], r["culprit"])
    r = RV.build(day, sale_plan=plan, sale_act=act)
    it = next(i for i in r["items"] if i["id"] == "sale")
    check("pozycja bez powodu: ogólne objaśnienie jak dotąd", "okno było zablokowane" in it["text"] and "why" not in it, it)
    r = RV.build(day, sale_plan=plan, sale_act={"kwh": 3.9}, sale_why={"text": "x"})
    it = next(i for i in r["items"] if i["id"] == "sale")
    check("sprzedaż wykonana → powód nie jest pokazywany", it["level"] == "ok" and it["text"] == "" and "why" not in it, it)
    r = RV.build(day, sale_plan=plan, sale_act=act, sale_why={"text": 5})
    check("zły powód (nie napis) nie psuje oceny", next(i for i in r["items"] if i["id"] == "sale")["text"].startswith("W oknach sprzedaży"))

    # ---------- linia tygodniowa
    def rv(d, **kw):
        return RV.build(d, **kw)
    ok = dict(pv_fc=10, pv_act=10)
    bad_pv = dict(pv_fc=20, pv_act=10)
    reviews = {}
    for d, kw in (("2026-11-14", ok), ("2026-11-15", ok), ("2026-11-16", bad_pv), ("2026-11-17", ok), ("2026-11-18", bad_pv), ("2026-11-19", ok), ("2026-11-13", bad_pv)):
        RV.store(reviews, rv(d, **kw))
    line = RV.week_line(reviews, "2026-11-14", "2026-11-20")
    check("tydzień: ile dni trafnych i co zawodziło", line is not None and line.startswith("Plan trafny w 4 z 6 dni") and "najczęściej zawodziła: prognoza PV" in line, line)
    check("tydzień: dni spoza okresu nie liczą się", "13" not in (line or "") and "z 6 dni" in (line or ""))
    only_ok = {}
    RV.store(only_ok, rv("2026-11-19", **ok))
    line = RV.week_line(only_ok, "2026-11-14", "2026-11-20")
    check("tydzień: 1 dzień → poprawna odmiana, bez winowajcy", line == "Plan trafny w 1 z 1 dnia", line)
    check("tydzień: brak ocen → None", RV.week_line({}, "2026-11-14", "2026-11-20") is None and RV.week_line(None, "a", "b") is None)
    check("tydzień: uszkodzone wpisy pominięte", RV.week_line({"2026-11-19": {"date": "x"}, "2026-11-18": 5}, "2026-11-14", "2026-11-20") is None)
    line = RV.week_line({"2026-11-19": rv("2026-11-19", pv_fc=20, pv_act=10, load_fc=10, load_act=10)}, "2026-11-14", "2026-11-20")
    check("tydzień: częściowo / chybiony wymienione", line and "z 1 dnia" in line and ("częściowo" in line or "chybiony" in line), line)


async def env(now=(2026, 11, 20, 21, 0)):
    hass, c, sched = await mk(now, 60)
    rt = rtm.BmsRuntime(hass, c, sched)
    c.runtime = rt
    return hass, c, sched, rt


async def runtime_part():
    tar.set_profile(tar.make_profile({"tariff_mode": "zone"}, prices_fn=lambda d: None, eff_fn=lambda: 0.9, source=""))
    hass, c, sched, rt = await env()
    # dziennik: wpis z wczoraj o zablokowanej sprzedaży
    rt.log.add("guard", "Sprzedaż 6000 W (auto) ZABLOKOWANA: tryb burzowy", "warn")
    ts = rt.log.entries[-1]["ts"]
    rt.log.entries[-1]["ts"] = "2026-11-19" + ts[10:]
    rt.insights.fc["2026-11-19"] = {"at": 6, "pv_fc": 10.0, "pv_fc_h": [0.0] * 24, "pv_act": 10.0, "soc_plan": [50.0] * 24, "soc_act": [50.0] * 24, "pv_lim": 0.0}
    rt.state["sale_plan"] = {"2026-11-19": {"kwh": 4.0, "gross": 5.0, "net": 1.5}}
    rt.state["sale_actual"] = {"2026-11-19": {"kwh": 0.0, "rev": 0.0}}
    rev = rt.build_day_review(date(2026, 11, 19))
    it = next((i for i in (rev or {}).get("items", []) if i["id"] == "sale"), None)
    check("runtime: powód braku sprzedaży z dziennika w ocenie", it and it.get("why") == "tryb burzowy", it)

    # bez wpisu w dzienniku, bateria nie dobiła do progu → powód z SOC
    hass, c, sched, rt = await env()
    rt.insights.fc["2026-11-19"] = {"at": 6, "pv_fc": 10.0, "pv_fc_h": [0.0] * 24, "pv_act": 10.0, "soc_plan": [40.0] * 24, "soc_act": [40.0] * 24, "pv_lim": 0.0}
    rt.state["sale_plan"] = {"2026-11-19": {"kwh": 4.0, "gross": 5.0, "net": 1.5}}
    rt.state["sale_actual"] = {"2026-11-19": {"kwh": 0.0, "rev": 0.0}}
    hass.states.set("number.bms_min_soc_for_sell", "50")
    rev = rt.build_day_review(date(2026, 11, 19))
    it = next((i for i in (rev or {}).get("items", []) if i["id"] == "sale"), None)
    check("runtime: powód z SOC, gdy dziennik milczy", it is not None and "nie dobiła do progu" in (it.get("why") or ""), it)

    # raport tygodniowy zawiera linię z oceną
    hass, c, sched, rt = await env()
    for d, kw in (("2026-11-18", dict(pv_fc=10, pv_act=10)), ("2026-11-19", dict(pv_fc=20, pv_act=10))):
        RV.store(rt.state.setdefault("day_reviews", {}), RV.build(d, **kw))
    txt = rt.summary_text("week", date(2026, 11, 20))
    check("raport tygodniowy ma linię z oceną planu", "Plan trafny w 1 z 2 dni" in txt and "prognoza PV" in txt, txt)
    hass, c, sched, rt = await env()
    txt = rt.summary_text("week", date(2026, 11, 20))
    check("raport tygodniowy bez ocen nie ma linii o planie", "Plan trafny" not in txt, txt)
    rt.state["day_reviews"] = "śmieć"
    try:
        txt = rt.summary_text("week", date(2026, 11, 20))
        ok = True
    except Exception:  # noqa: BLE001
        ok = False
    check("uszkodzone oceny nie psują raportu tygodniowego", ok)


async def main():
    pure()
    await runtime_part()


asyncio.run(main())
print(f"REVIEW_WHY PASS={common.PASS} FAIL={common.FAIL}")
