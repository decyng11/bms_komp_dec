"""Auto-stosowanie: limit przesunięcia liczony krótszą drogą przez północ i nie blokujący okna WYMAGANEGO przez plan.

Zgłoszenie: „nie działa auto-stosowanie na dwóch instalacjach” — propozycja okna ładowania nocnego „START 01:00 → 19:00,
STOP 03:00” (wymagane) wisiała w „Do decyzji”. Przyczyna: przesunięcie liczone na prostej (|19:00 − 01:00| = 18 h)
i porównywane z limitem, którego suwak kończy się na 12 h, więc okno przechodzące przez północ nie miało szans."""
import asyncio, sys
from datetime import timedelta
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import automation
from homeassistant.util import dt as dt_util


def pp(cur, new, **kw):
    d = {"skip": False, "proposed": new, "current": cur, "confidence": "high", "reason": "x"}; d.update(kw); return d


def setup(cs, ce, shift=None):
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_start_grid_charge", cs + ":00"); S.set("time.bms_stop_grid_charge", ce + ":00")
    S.set("switch.bms_auto_apply", "on"); S.set("switch.bms_ladowanie_z_sieci_1", "on")
    if shift is not None:
        S.set("number.bms_auto_apply_max_shift_h", str(shift))
    return hass, c, opt, rt, S


def cur(S):
    return S.get("time.bms_start_grid_charge").state[:5], S.get("time.bms_stop_grid_charge").state[:5]


async def apply(cs, ce, ns, ne, shift=None, **kw):
    hass, c, opt, rt, S = setup(cs, ce, shift)
    res = await automation.async_auto_apply(rt, hass, {"proposals": {"start_grid_charge": pp(cs, ns, **kw), "stop_grid_charge": pp(ce, ne, **kw)}})
    return cur(S), res


async def main():
    # odległość krótszą drogą przez północ
    sh = automation._shift_hours
    check("23:00 → 01:00 to 2 h", abs(sh(23 * 60, 60) - 2.0) < 1e-9, sh(23 * 60, 60))
    check("01:00 → 23:00 to 2 h (w drugą stronę)", abs(sh(60, 23 * 60) - 2.0) < 1e-9)
    check("01:00 → 19:00 to 6 h (nie 18)", abs(sh(60, 19 * 60) - 6.0) < 1e-9, sh(60, 19 * 60))
    check("12:00 → 00:30 to 11,5 h", abs(sh(12 * 60, 30) - 11.5) < 1e-9)
    check("bez północy bez zmian: 22:00 → 23:30 to 1,5 h", abs(sh(22 * 60, 23 * 60 + 30) - 1.5) < 1e-9)
    check("granica: 06:00 → 18:00 to 12 h", abs(sh(6 * 60, 18 * 60) - 12.0) < 1e-9)

    # niewymagane okno: limit nadal działa, ale przez północ liczy się krótszą drogą
    t, r = await apply("23:00", "06:00", "01:00", "06:00")
    check("start 23:00 → 01:00 (2 h przez północ) przechodzi przy domyślnym limicie 4 h", t == ("01:00", "06:00") and r["applied"], (t, r))
    t, r = await apply("00:30", "06:00", "23:30", "06:00")
    check("start 00:30 → 23:30 (1 h wstecz przez północ) przechodzi", t[0] == "23:30" and r["applied"], (t, r))
    t, r = await apply("01:00", "03:00", "19:00", "03:00")
    check("niewymagane 01:00 → 19:00 (6 h) przy limicie 4 h: nadal odrzucone, z poprawną liczbą (6,0 h)",
          t == ("01:00", "03:00") and any("przesunięcie 6.0 h > limit 4 h" in s for s in r["skipped"]), (t, r))
    t, r = await apply("01:00", "03:00", "19:00", "03:00", shift=6)
    check("niewymagane 01:00 → 19:00 przy limicie 6 h: przechodzi (wcześniej 18 h > max 12 h, nie do przejścia)", t[0] == "19:00" and r["applied"], (t, r))
    t, r = await apply("12:00", "14:00", "17:00", "19:00")
    check("niewymagane okno dzienne, przesunięcie o 5 h > 4 h: odrzucone", t == ("12:00", "14:00") and not r["applied"], (t, r))

    # okno WYMAGANE przez plan (zrzut z zakładki „Do decyzji”): limit przesunięcia go nie blokuje
    t, r = await apply("01:00", "03:00", "19:00", "03:00", required=True)
    check("WYMAGANE 01:00 → 19:00, STOP 03:00 (zrzut użytkownika) stosuje się samo przy domyślnym limicie",
          t == ("19:00", "03:00") and r["applied"] == {"start_grid_charge": "19:00"}, (t, r))
    t, r = await apply("12:00", "14:00", "07:00", "14:00", required=True)
    check("WYMAGANE: dowolne przesunięcie startu (5 h) stosuje się", t[0] == "07:00" and r["applied"], (t, r))
    # pozostałe zabezpieczenia dla wymaganych nadal działają
    t, r = await apply("01:00", "03:00", "19:00", "03:00", required=True, confidence="low")
    check("WYMAGANE, ale niska pewność: nic", t == ("01:00", "03:00") and not r["applied"], (t, r))
    hass, c, opt, rt, S = setup("01:00", "03:00")
    S.set("time.bms_bateria_sprzedaz_start", "08:00:00"); S.set("time.bms_bateria_sprzedaz_stop", "10:00:00")
    res = await automation.async_auto_apply(rt, hass, {"proposals": {"bateria_sprzedaz_start": pp("08:00", "11:00", required=True), "bateria_sprzedaz_stop": pp("10:00", "10:00", required=True)}})
    check("WYMAGANE, ale start po stopie w oknie sprzedaży (nie przechodzi przez północ): niespójna para, nic",
          S.get("time.bms_bateria_sprzedaz_start").state[:5] == "08:00" and any("niespójna" in s for s in res["skipped"]), res)
    hass, c, opt, rt, S = setup("01:00", "03:00")
    S.set("switch.bms_auto_apply_dry_run", "off")
    rt.is_selling = lambda: True
    res = await automation.async_auto_apply(rt, hass, {"proposals": {"start_grid_charge": pp("01:00", "19:00", required=True), "stop_grid_charge": pp("03:00", "03:00", required=True)}})
    check("WYMAGANE, ale trwa sprzedaż: wstrzymane", cur(S) == ("01:00", "03:00") and not res["applied"], res)

    # ścieżka na żywo (co 30 s z _plan_tick): stabilne ≥ 30 min → zastosowane, mimo przesunięcia 6 h
    hass, c, opt, rt, S = setup("01:00", "03:00")
    t0 = dt_util.now().replace(hour=16, minute=30, second=0, microsecond=0)
    plan = {"proposals": {"start_grid_charge": pp("01:00", "19:00", required=True), "stop_grid_charge": pp("03:00", "03:00", required=True)}}
    await automation.async_live_apply(rt, hass, plan, t0)
    check("na żywo: pierwszy odczyt jeszcze nie stosuje", cur(S) == ("01:00", "03:00"), cur(S))
    await automation.async_live_apply(rt, hass, plan, t0 + timedelta(minutes=31))
    check("na żywo: po 31 min wymagane okno 19:00–03:00 zastosowane", cur(S) == ("19:00", "03:00"), cur(S))

    # ---- powód niezastosowania zapamiętany dla panelu („Do decyzji”)
    from custom_components.bms_komp_dec import inbox
    hass, c, opt, rt, S = setup("12:00", "14:00")
    pr = {"start_grid_charge": pp("12:00", "17:00"), "stop_grid_charge": pp("14:00", "19:00")}
    res = await automation.async_auto_apply(rt, hass, {"proposals": pr})
    rec = (rt.state.get("auto_skip") or {}).get("start_grid_charge") or {}
    check("odmowa przez limit: powód zapisany przy kluczu", rec.get("kind") == "skip" and "limit 4 h" in rec.get("why", "") and rec.get("prop") == "17:00", rec)
    check("odmowa przez limit: powód podpowiada, co zrobić", "potwierdź ręcznie" in rec.get("why", "") and "maks. przesunięcie" in rec.get("why", ""), rec)
    # w czasie przerwy między próbami ogólne „czekam” nie przykrywa konkretnego powodu
    automation._remember_auto_skip(rt, {"start_grid_charge": ("czekam", "17:00")}, kind="wait")
    check("„czekam” nie nadpisuje konkretnej odmowy tej samej propozycji", rt.state["auto_skip"]["start_grid_charge"]["kind"] == "skip", rt.state["auto_skip"])
    automation._remember_auto_skip(rt, {"start_grid_charge": ("czekam", "18:00")}, kind="wait")
    check("dla innej propozycji „czekam” zastępuje stary powód", rt.state["auto_skip"]["start_grid_charge"]["kind"] == "wait" and rt.state["auto_skip"]["start_grid_charge"]["prop"] == "18:00")
    # plan zmienił propozycję → stary powód znika
    inbox.prune_auto_skip(rt.state, {"start_grid_charge": pp("12:00", "17:30"), "stop_grid_charge": pp("14:00", "19:00")})
    check("inna proponowana godzina: stary powód usunięty", "start_grid_charge" not in rt.state["auto_skip"], rt.state["auto_skip"])
    # zastosowanie czyści powód
    hass, c, opt, rt, S = setup("12:00", "14:00")
    rt.state["auto_skip"] = {"start_grid_charge": {"kind": "skip", "why": "stary", "prop": "13:00"}}
    await automation.async_auto_apply(rt, hass, {"proposals": {"start_grid_charge": pp("12:00", "13:00"), "stop_grid_charge": pp("14:00", "14:00")}})
    check("zastosowanie propozycji czyści jej powód", "start_grid_charge" not in rt.state["auto_skip"] and cur(S)[0] == "13:00", (rt.state["auto_skip"], cur(S)))
    # trwa sprzedaż → powód „wstrzymane” przy oczekujących kluczach
    hass, c, opt, rt, S = setup("12:00", "14:00")
    rt.is_selling = lambda: True
    await automation.async_auto_apply(rt, hass, {"proposals": {"start_grid_charge": pp("12:00", "13:00"), "stop_grid_charge": pp("14:00", "14:00")}})
    rec = (rt.state.get("auto_skip") or {}).get("start_grid_charge") or {}
    check("trwa sprzedaż: powód „wstrzymane: trwa sprzedaż”", "wstrzymane: trwa sprzedaż" in rec.get("why", "") and "stop_grid_charge" not in rt.state["auto_skip"], rt.state.get("auto_skip"))
    # niska pewność i tryb podglądu
    t, r = await apply("12:00", "14:00", "13:00", "14:00", confidence="low")
    hass, c, opt, rt, S = setup("12:00", "14:00"); S.set("switch.bms_auto_apply_dry_run", "on")
    await automation.async_auto_apply(rt, hass, {"proposals": {"start_grid_charge": pp("12:00", "13:00"), "stop_grid_charge": pp("14:00", "14:00")}}, dry_run=True)
    check("tryb podglądu: powód wskazuje przełącznik", "tylko podgląd" in ((rt.state.get("auto_skip") or {}).get("start_grid_charge") or {}).get("why", ""), rt.state.get("auto_skip"))
    # ścieżka na żywo: oczekiwanie na stabilność jest widoczne jako powód
    hass, c, opt, rt, S = setup("12:00", "14:00")
    t1 = dt_util.now().replace(hour=9, minute=0, second=0, microsecond=0)
    pl = {"proposals": {"start_grid_charge": pp("12:00", "13:00"), "stop_grid_charge": pp("14:00", "14:00")}}
    await automation.async_live_apply(rt, hass, pl, t1)
    rec = (rt.state.get("auto_skip") or {}).get("start_grid_charge") or {}
    check("na żywo: przed upływem 30 min widać powód „czekam…”", rec.get("kind") == "wait" and "30 min" in rec.get("why", ""), rec)
    await automation.async_live_apply(rt, hass, pl, t1 + timedelta(minutes=31))
    check("na żywo: po zastosowaniu powód znika", "start_grid_charge" not in (rt.state.get("auto_skip") or {}) and cur(S)[0] == "13:00", (rt.state.get("auto_skip"), cur(S)))

    # ---- historia prób i autotest „Auto-stosowanie”
    from custom_components.bms_komp_dec import selftest as ST
    hass, c, opt, rt, S = setup("12:00", "14:00")
    await automation.async_auto_apply(rt, hass, {"proposals": {"start_grid_charge": pp("12:00", "17:00"), "stop_grid_charge": pp("14:00", "19:00")}}, source="daily")
    await automation.async_auto_apply(rt, hass, {"proposals": {"start_grid_charge": pp("12:00", "13:00"), "stop_grid_charge": pp("14:00", "14:00", required=True)}}, source="live")
    h = rt.state.get("auto_hist") or []
    check("historia: dwie próby zapisane z źródłem", [x["src"] for x in h] == ["daily", "live"], h)
    check("historia: odmowa ma powód, zastosowanie ma godziny", "limit 4 h" in (h[0].get("why") or {}).get("start_grid_charge", "") and h[1].get("applied") == {"start_grid_charge": "13:00"}, h)
    await automation.async_auto_apply(rt, hass, {"proposals": {"start_grid_charge": pp("13:00", "13:00"), "stop_grid_charge": pp("14:00", "14:00")}}, source="daily")
    check("historia: próba bez niczego do zrobienia nie dopisuje wpisu", len(rt.state["auto_hist"]) == 2, rt.state["auto_hist"])
    for i in range(30):
        automation._auto_hist_add(rt, "live", busy=["trwa sprzedaż"])
    check("historia: najwyżej 20 wpisów", len(rt.state["auto_hist"]) == 20, len(rt.state["auto_hist"]))
    res = await ST.run(rt)
    grp = next(g for g in res["groups"] if g["name"] == "Auto-stosowanie")
    ids = {ch["id"]: ch for ch in grp["checks"]}
    check("autotest: grupa ma kontrole włączenia, limitu, encji, wstrzymania, oczekujących i ostatniej próby",
          all(k in ids for k in ("auto_on", "auto_limit", "auto_entities", "auto_busy", "auto_pending", "auto_last")), list(ids))
    check("autotest: auto-stosowanie włączone, limit 4 h", ids["auto_on"]["detail"] == "włączone" and "4 h" in ids["auto_limit"]["detail"], (ids["auto_on"], ids["auto_limit"]))
    S.set("switch.bms_auto_apply_dry_run", "on")
    ids = {ch["id"]: ch for ch in next(g for g in (await ST.run(rt))["groups"] if g["name"] == "Auto-stosowanie")["checks"]}
    check("autotest: auto włączone + podgląd → ostrzeżenie", ids["auto_dry"]["status"] == "warn", ids.get("auto_dry"))
    S.set("switch.bms_auto_apply_dry_run", "off")
    S.set("time.bms_start_grid_charge", "unavailable")
    ids = {ch["id"]: ch for ch in next(g for g in (await ST.run(rt))["groups"] if g["name"] == "Auto-stosowanie")["checks"]}
    check("autotest: niedostępna encja godziny → błąd z nazwą klucza", ids["auto_entities"]["status"] == "error" and "start_grid_charge" in ids["auto_entities"]["detail"], ids["auto_entities"])
    S.set("time.bms_start_grid_charge", "12:00:00")
    rt.is_selling = lambda: True
    ids = {ch["id"]: ch for ch in next(g for g in (await ST.run(rt))["groups"] if g["name"] == "Auto-stosowanie")["checks"]}
    check("autotest: trwa sprzedaż → wstrzymanie wymienione", "trwa sprzedaż" in ids["auto_busy"]["detail"], ids["auto_busy"])
    del rt.is_selling
    rt._plan = {"proposals": {"start_grid_charge": {"proposed": "17:00", "current": "12:00", "skip": False}}}
    rt.state["auto_skip"] = {"start_grid_charge": {"kind": "skip", "why": "przesunięcie za duże", "prop": "17:00"}}
    ids = {ch["id"]: ch for ch in next(g for g in (await ST.run(rt))["groups"] if g["name"] == "Auto-stosowanie")["checks"]}
    check("autotest: oczekująca propozycja z powodem → ostrzeżenie", ids["auto_pending"]["status"] == "warn" and "przesunięcie za duże" in ids["auto_pending"]["detail"], ids["auto_pending"])

    # straż poranka w autoteście
    rt._plan = {"proposals": {"start_grid_charge": pp("12:00", "19:00", required=True), "stop_grid_charge": pp("14:00", "03:00", required=True)}}
    S.set("time.bms_start_grid_charge", "12:00:00"); S.set("time.bms_stop_grid_charge", "14:00:00")
    t_g = dt_util.now().replace(hour=18, minute=0, second=0, microsecond=0)
    gi = automation.morning_guard_issues(rt, hass, rt._plan, t_g)
    check("straż poranka: problem wykryty 1 h przed oknem", len(gi) == 1 and gi[0]["start"] == "19:00" and gi[0]["minutes_to_start"] == 60, gi)
    print(f"AUTOAPPLY-SHIFT PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
