"""Ocena trafności planu po dobie: pozycje PV / zużycie / SOC / sprzedaż, werdykt, winowajca, zapis w stanie, runtime, czujnik."""
import asyncio, json, math, sys
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import review as RV, state_guard, tariff as tar
from custom_components.bms_komp_dec.sensor import BmsRuntimeSensor

NAN = float("nan")


def soc24(f):
    return [float(f(h)) for h in range(24)]


def item(rev, iid):
    return next((i for i in rev["items"] if i["id"] == iid), None)


def pure():
    # ---------- brak danych → None
    check("brak jakichkolwiek par → None", RV.build("2026-11-19") is None)
    check("same prognozy bez wykonania → None", RV.build("2026-11-19", pv_fc=10, load_fc=12) is None)
    check("wykonanie poniżej 0,5 kWh nie daje oceny procentowej", RV.build("2026-11-19", pv_fc=3, pv_act=0.2) is None)
    check("nan / bool / napis nie są liczbami", RV.build("2026-11-19", pv_fc=NAN, pv_act=5) is None
          and RV.build("2026-11-19", pv_fc=True, pv_act=5) is None and RV.build("2026-11-19", pv_fc="x", pv_act=5) is None)

    # ---------- trafny dzień
    r = RV.build("2026-11-19", pv_fc=10.0, pv_act=9.6, load_fc=14.0, load_act=13.5, soc_plan=soc24(lambda h: 50), soc_act=soc24(lambda h: 53),
                 sale_plan={"kwh": 3.0, "gross": 3.5, "net": 1.0}, sale_act={"kwh": 2.9, "rev": 3.4}, net=4.2, guards=0, autos=0)
    check("trafny dzień: werdykt, wynik 100, brak winowajcy", r["verdict"] == "trafny" and r["score"] == 100 and r["culprit"] is None, r)
    check("wszystkie cztery pozycje", [i["id"] for i in r["items"]] == ["pv", "load", "soc", "sale"], r["items"])
    check("poziomy ok", all(i["level"] == "ok" for i in r["items"]))
    check("fakty: bilans dnia z przecinkiem", r["facts"] == ["Bilans dnia: +4,20 zł"], r["facts"])
    check("linia: werdykt i skrócone pozycje", r["line"].startswith("Ocena planu z 2026-11-19: trafny — ") and "PV ±4%" in r["line"] and "najbardziej" not in r["line"], r["line"])

    # ---------- PV zawyżona → chybiony / winowajca
    r = RV.build("2026-11-19", pv_fc=20.0, pv_act=10.0, load_fc=14.0, load_act=14.0)
    check("PV zawyżona 2× → pozycja bad, błąd +100%", item(r, "pv")["level"] == "bad" and item(r, "pv")["err"] == 100.0, item(r, "pv"))
    check("PV bad + zużycie ok → częściowo trafny (jeden bad)", r["verdict"] == "częściowo trafny", r["verdict"])
    check("winowajca = PV, tekst o mniejszej ilości słońca", r["culprit"]["id"] == "pv" and "mniej" in r["culprit"]["text"] and "10,0 kWh" in r["culprit"]["text"], r["culprit"])
    check("linia wskazuje, co zawiodło", "prognoza PV zawyżona o 100%" in r["line"] and "najbardziej zawiodło: produkcja pv" in r["line"], r["line"])

    # ---------- PV zaniżona
    r = RV.build("2026-11-19", pv_fc=6.0, pv_act=12.0)
    check("PV zaniżona → tekst o większej ilości słońca", item(r, "pv")["err"] == -50.0 and "więcej" in r["culprit"]["text"], r)
    check("jedna pozycja i bad → chybiony", r["verdict"] == "chybiony", r["verdict"])

    # ---------- progi
    for fc, lvl in ((11.4, "ok"), (11.6, "warn"), (12.9, "warn"), (13.1, "bad")):
        got = item(RV.build("d", pv_fc=fc, pv_act=10.0), "pv")["level"]
        check(f"próg PV: prognoza {fc} przy wykonaniu 10 → {lvl}", got == lvl, got)

    # ---------- uciętą produkcję nie liczymy jako winy prognozy
    r = RV.build("2026-11-19", pv_fc=20.0, pv_act=10.0, pv_limited=0.4)
    check("bateria pełna i ucięcie PV: bad łagodzone do warn", item(r, "pv")["level"] == "warn", item(r, "pv"))
    check("opis wyjaśnia ucięcie, nie obwinia prognozy", "nie jest błąd prognozy" in r["culprit"]["text"] and "40%" in r["culprit"]["text"], r["culprit"])
    r = RV.build("2026-11-19", pv_fc=20.0, pv_act=10.0, pv_limited=0.05)
    check("małe ucięcie (5%) nie zmienia oceny", item(r, "pv")["level"] == "bad", item(r, "pv"))
    r = RV.build("2026-11-19", pv_fc=10.0, pv_act=20.0, pv_limited=0.4)
    check("ucięcie nie tłumaczy prognozy zaniżonej", item(r, "pv")["level"] == "bad", item(r, "pv"))

    # ---------- zużycie
    r = RV.build("d", load_fc=10.0, load_act=16.0)
    check("zużycie większe niż w prognozie → tekst o szybszym schodzeniu baterii", "więcej" in item(r, "load")["text"] and "zabraknąć" in item(r, "load")["text"], item(r, "load"))
    r = RV.build("d", load_fc=20.0, load_act=14.0)
    check("zużycie mniejsze niż w prognozie → tekst o energii, która została", "mniej" in item(r, "load")["text"] and "zostało więcej" in item(r, "load")["text"], item(r, "load"))

    # ---------- SOC
    r = RV.build("d", soc_plan=soc24(lambda h: 60), soc_act=soc24(lambda h: 60 - (30 if h == 18 else 2)))
    s = item(r, "soc")
    check("SOC: średnia różnica i godzina największej różnicy", s["unit"] == "pp" and "18:00" in s["detail"] and s["level"] == "ok", s)
    r = RV.build("d", soc_plan=soc24(lambda h: 60), soc_act=soc24(lambda h: 40))
    s = item(r, "soc")
    check("SOC: różnica 20 pp → bad, tekst o mniejszej ilości energii", s["level"] == "bad" and "mniej energii" in s["text"], s)
    r = RV.build("d", soc_plan=soc24(lambda h: 40), soc_act=soc24(lambda h: 60))
    check("SOC wyższy od planu → tekst o większej ilości energii", "więcej energii" in item(r, "soc")["text"])
    r = RV.build("d", soc_plan=[50.0, 50.0, 50.0] + [None] * 21, soc_act=[40.0] * 24)
    check("SOC: mniej niż 4 pary → brak pozycji", r is None, r)
    r = RV.build("d", soc_plan=[50.0, NAN, "x", None, True] + [50.0] * 3 + [None] * 16, soc_act=[50.0] * 24)
    check("SOC: nan/napisy/bool pomijane, 4 poprawne pary wystarczają", r is not None and item(r, "soc")["level"] == "ok", r)

    # ---------- sprzedaż
    plan = {"kwh": 5.0, "gross": 6.0, "net": 2.0}
    for kwh, lvl in ((5.0, "ok"), (7.0, "ok"), (4.0, "ok"), (3.9, "warn"), (2.5, "warn"), (2.4, "bad"), (0.0, "bad")):
        got = item(RV.build("d", sale_plan=plan, sale_act={"kwh": kwh, "rev": 1.0}), "sale")["level"]
        check(f"sprzedaż {kwh} z planowanych 5 kWh → {lvl}", got == lvl, got)
    r = RV.build("d", sale_plan=plan, sale_act=None)
    check("plan sprzedaży bez żadnego eksportu → bad 0%", item(r, "sale")["level"] == "bad" and "0% planu" in item(r, "sale")["short"], item(r, "sale"))
    check("plan sprzedaży poniżej 0,5 kWh nie jest oceniany", RV.build("d", sale_plan={"kwh": 0.3}, sale_act={"kwh": 0}) is None)
    check("plan sprzedaży jako nie-słownik nie wywala oceny", RV.build("d", sale_plan="x", sale_act=5, pv_fc=5, pv_act=5) is not None)
    check("eksport jako nan → traktowany jak 0", item(RV.build("d", sale_plan=plan, sale_act={"kwh": NAN}), "sale")["level"] == "bad")

    # ---------- werdykt: kombinacje
    def v(**kw):
        return RV.build("d", **kw)["verdict"]
    check("dwa bad → chybiony", v(pv_fc=20, pv_act=10, load_fc=10, load_act=20, soc_plan=soc24(lambda h: 50), soc_act=soc24(lambda h: 50)) == "chybiony")
    check("jedno warn → trafny", v(pv_fc=12.5, pv_act=10, load_fc=10, load_act=10) == "trafny")
    check("dwa warn → częściowo trafny", v(pv_fc=12.5, pv_act=10, load_fc=12.5, load_act=10) == "częściowo trafny")
    check("bad + trzy ok → częściowo trafny", v(pv_fc=20, pv_act=10, load_fc=10, load_act=10, soc_plan=soc24(lambda h: 50), soc_act=soc24(lambda h: 50),
                                                  sale_plan=plan, sale_act={"kwh": 5.0}) == "częściowo trafny")
    r = RV.build("d", pv_fc=20, pv_act=10, load_fc=10, load_act=10, soc_plan=soc24(lambda h: 50), soc_act=soc24(lambda h: 50))
    check("wynik: 1 bad z 3 pozycji = 67", r["score"] == 67, r["score"])

    # ---------- winowajca: najgorszy poziom, potem największa waga
    r = RV.build("d", pv_fc=12.5, pv_act=10, load_fc=17, load_act=10)       # PV warn (25%), zużycie bad (70%)
    check("winowajca: bad przed warn", r["culprit"]["id"] == "load", r["culprit"])
    r = RV.build("d", pv_fc=13.5, pv_act=10, load_fc=17, load_act=10)       # obie bad: PV 35%, zużycie 70%
    check("winowajca: przy równym poziomie większy błąd", r["culprit"]["id"] == "load", r["culprit"])

    # ---------- fakty
    r = RV.build("d", pv_fc=10, pv_act=10, net=-1.5, guards=3, autos=2)
    check("fakty: ujemny bilans, zabezpieczenia, automat", r["facts"] == ["Bilans dnia: -1,50 zł", "Zabezpieczenia zadziałały 3×", "Automat zmieniał ustawienia 2×"], r["facts"])
    r = RV.build("d", pv_fc=10, pv_act=10, net=NAN)
    check("bilans nan → bez faktu", r["facts"] == [], r["facts"])

    # ---------- zapis, przycinanie, odczyt
    revs = {}
    for i in range(1, 36):
        RV.store(revs, RV.build(f"2026-10-{i:02d}" if i <= 31 else f"2026-11-{i - 31:02d}", pv_fc=10, pv_act=10))
    check("przycięcie do 30 dni (najnowsze zostają)", len(revs) == RV.KEEP_DAYS and "2026-11-04" in revs and "2026-10-01" not in revs, sorted(revs)[:3])
    rows = RV.recent(revs, 5)
    check("recent: najnowsze pierwsze, limit", [x["date"] for x in rows] == ["2026-11-04", "2026-11-03", "2026-11-02", "2026-11-01", "2026-10-31"], [x["date"] for x in rows])
    check("recent: n=0 i zły typ", RV.recent(revs, 0) == [] and RV.recent("x") == [] and RV.recent(None) == [] and RV.recent([1]) == [])
    bad = dict(revs)
    bad["2026-12-01"] = {"date": "2026-12-01", "verdict": "super", "items": []}
    bad["2026-12-02"] = "tekst"
    bad["2026-12-03"] = {"date": "2026-12-03", "verdict": "trafny", "items": [1]}
    bad["2026-12-04"] = {"date": "2026-12-04", "verdict": "trafny", "items": [], "culprit": "x"}
    bad[5] = {"date": "x", "verdict": "trafny", "items": []}
    check("recent pomija uszkodzone wpisy", all(RV.valid(x) for x in RV.recent(bad, 99)) and len(RV.recent(bad, 99)) == len(revs), len(RV.recent(bad, 99)))

    # ---------- statystyka
    rows = [RV.build("a", pv_fc=20, pv_act=10), RV.build("b", pv_fc=20, pv_act=10, load_fc=10, load_act=20), RV.build("c", pv_fc=10, pv_act=10)]
    t = RV.tally(rows)
    check("tally: liczby werdyktów", t["n"] == 3 and t["counts"] == {"trafny": 1, "częściowo trafny": 0, "chybiony": 2}, t)
    check("tally: najczęstszy winowajca", t["top_culprit"] == "pv" and t["top_culprit_n"] == 2, t)
    check("tally: pusta lista", RV.tally([]) == {"n": 0, "counts": {"trafny": 0, "częściowo trafny": 0, "chybiony": 0}, "top_culprit": None, "top_culprit_n": 0})


async def env(now=(2026, 11, 20, 0, 30)):
    hass, c, sched = await mk(now, 60)
    rt = rtm.BmsRuntime(hass, c, sched)
    c.runtime = rt
    return hass, c, sched, rt


def seed_day(rt, key="2026-11-19", closed=True, **over):
    rec = {"at": 6, "pv_fc": 14.0, "pv_fc_h": [0.0] * 24, "soc_plan": soc24(lambda h: 55)}
    if closed:
        rec.update({"pv_act": 9.0, "soc_act": soc24(lambda h: 50), "pv_lim": 0.0})
    rec.update(over)
    rt.insights.fc[key] = rec


async def runtime_part():
    tar.set_profile(tar.make_profile({"tariff_mode": "zone"}, prices_fn=lambda d: None, eff_fn=lambda: 0.9, source=""))

    # ---------- po północy, doba zamknięta: ocena powstaje raz
    hass, c, sched, rt = await env()
    seed_day(rt)
    rt.state["sale_plan"] = {"2026-11-19": {"kwh": 4.0, "gross": 5.0, "net": 1.5}}
    rt.state["sale_actual"] = {"2026-11-19": {"kwh": 1.0, "rev": 1.2}}
    rt.state["accuracy"] = [{"date": "2026-11-19", "load_fc": 15.0, "load": 18.0, "pv_fc": 14.0, "pv": 8.5}]
    await rt.review_tick(at(2026, 11, 20, 0, 30))
    rev = rt.state.get("day_reviews", {}).get("2026-11-19")
    check("review_tick zapisuje ocenę wczorajszego dnia", rev is not None and RV.valid(rev), rt.state.get("day_reviews"))
    check("znacznik review_done ustawiony", rt.state.get("review_done") == "2026-11-19")
    check("PV: prognoza z insights, wykonanie z insights (pv_act 9,0)", item(rev, "pv")["plan"] == 14.0 and item(rev, "pv")["actual"] == 9.0, item(rev, "pv"))
    check("zużycie z wiersza trafności (brak load_forecast w teście)", item(rev, "load") is not None and item(rev, "load")["actual"] == 18.0, item(rev, "load"))
    check("SOC: plan 55 vs fakt 50 → ok", item(rev, "soc")["level"] == "ok", item(rev, "soc"))
    check("sprzedaż: 1 z 4 kWh → bad", item(rev, "sale")["level"] == "bad", item(rev, "sale"))
    check("dwie pozycje bad → werdykt chybiony", rev["verdict"] == "chybiony", rev["verdict"])
    n_log = len([e for e in rt.log.last(50) if "Ocena planu z 2026-11-19" in str(e.get("msg", ""))])
    check("wpis w dzienniku decyzji", n_log == 1, n_log)
    await rt.review_tick(at(2026, 11, 20, 0, 31))
    n_log = len([e for e in rt.log.last(50) if "Ocena planu z 2026-11-19" in str(e.get("msg", ""))])
    check("drugi tick tego samego dnia nie dubluje wpisu", n_log == 1, n_log)

    # ---------- doba jeszcze niezamknięta: czeka do 2:00
    hass, c, sched, rt = await env()
    seed_day(rt, closed=False)
    await rt.review_tick(at(2026, 11, 20, 0, 30))
    check("niezamknięta doba przed 2:00 → czeka", "day_reviews" not in rt.state and rt.state.get("review_done") is None, rt.state.get("day_reviews"))
    await rt.review_tick(at(2026, 11, 20, 2, 0))
    check("po 2:00 ocenia z tym, co jest (PV brak wykonania → bez PV)", rt.state.get("review_done") == "2026-11-19")

    # ---------- brak danych: znacznik ustawiony, bez wpisu i bez ponawiania
    hass, c, sched, rt = await env()
    await rt.review_tick(at(2026, 11, 20, 3, 0))
    check("brak danych → brak oceny, ale znacznik (bez pętli co minutę)", not rt.state.get("day_reviews") and rt.state.get("review_done") == "2026-11-19", rt.state)

    # ---------- dziś nie oceniamy; wczoraj oceniamy tylko raz
    hass, c, sched, rt = await env((2026, 11, 20, 23, 0))
    seed_day(rt, key="2026-11-20")
    await rt.review_tick(at(2026, 11, 20, 23, 0))
    check("ocena dotyczy wczoraj, nie dziś", "2026-11-20" not in (rt.state.get("day_reviews") or {}), rt.state.get("day_reviews"))

    # ---------- linia w podsumowaniu dnia: dla „dziś” — wczorajsza ocena
    hass, c, sched, rt = await env((2026, 11, 20, 21, 0))
    rt.state["day_reviews"] = {"2026-11-19": RV.build("2026-11-19", pv_fc=20, pv_act=10, load_fc=10, load_act=10)}
    lines = rt._plan_vs_actual_lines(date(2026, 11, 20))
    check("podsumowanie dzisiejszego dnia zawiera ocenę wczorajszą", any(l.startswith("Ocena planu z 2026-11-19") for l in lines), lines)
    lines = rt._plan_vs_actual_lines(date(2026, 11, 19))
    check("podsumowanie dnia z przeszłości zawiera jego własną ocenę", any(l.startswith("Ocena planu z 2026-11-19") for l in lines), lines)
    rt.state["day_reviews"] = {"2026-11-19": {"date": "2026-11-19", "verdict": "xx"}}
    try:
        lines = rt._plan_vs_actual_lines(date(2026, 11, 20))
        ok = not any("Ocena planu" in l for l in lines)
    except Exception as err:  # noqa: BLE001
        ok = False
    check("uszkodzona ocena nie psuje podsumowania", ok)

    # ---------- czujnik i odczyt dla karty
    hass, c, sched, rt = await env()
    for d, kw in (("2026-11-17", dict(pv_fc=10, pv_act=10)), ("2026-11-18", dict(pv_fc=20, pv_act=10)), ("2026-11-19", dict(pv_fc=10, pv_act=10))):
        RV.store(rt.state.setdefault("day_reviews", {}), RV.build(d, **kw))
    got = rt.day_reviews(2)
    check("day_reviews: najnowsze pierwsze, limit", [r["date"] for r in got] == ["2026-11-19", "2026-11-18"], [r["date"] for r in got])
    check("czujnik forecast_accuracy ma atrybut reviews", "reviews" in BmsRuntimeSensor._unrecorded_attributes)
    sens = BmsRuntimeSensor(c, "forecast_accuracy", "x", None, "mdi:x"); sens.coordinator = c
    attrs = sens.extra_state_attributes
    check("czujnik: reviews w atrybutach, bez nan", isinstance(attrs, dict) and isinstance(attrs.get("reviews"), list) and len(attrs["reviews"]) == 3
          and json.dumps(attrs["reviews"], allow_nan=False), attrs)

    # ---------- state_guard
    st = {"day_reviews": {"2026-11-19": RV.build("2026-11-19", pv_fc=10, pv_act=10), "2026-11-18": "śmieć", "x": {"date": "x"}}}
    fixed = state_guard.sanitize(st)
    check("state_guard: zostają tylko poprawne oceny", list(st["day_reviews"]) == ["2026-11-19"] and "day_reviews" in fixed, (st, fixed))
    st = {"day_reviews": [1, 2], "review_done": 5}
    fixed = state_guard.sanitize(st)
    check("state_guard: zły typ day_reviews i review_done → reset", st["day_reviews"] == {} and st["review_done"] is None, (st, fixed))
    st = {"day_reviews": {"2026-11-19": RV.build("2026-11-19", pv_fc=10, pv_act=10)}}
    check("state_guard: poprawne oceny bez zmian", state_guard.sanitize(st) == [] and len(st["day_reviews"]) == 1)


async def main():
    pure()
    await runtime_part()


asyncio.run(main())
print(f"REVIEW PASS={common.PASS} FAIL={common.FAIL}")
