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

    print(f"AUTOAPPLY-SHIFT PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
