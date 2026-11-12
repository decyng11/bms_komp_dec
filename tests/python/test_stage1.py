"""Etap 1: przenośność — profil taryfy, wykrywanie encji falownika, opcje i zakresy."""
import asyncio, sys
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import inverter_ctl as ictl
from custom_components.bms_komp_dec.holidays_pl import is_holiday
from homeassistant.exceptions import HomeAssistantError


def legacy_peak(dt):
    if dt.weekday() >= 5 or is_holiday(dt.date()):
        return False
    h = dt.hour
    return 6 <= h < 13 or 15 <= h < 22


async def main():
    # ------------------------------------------------ parse_peaks
    P = tar.parse_peaks
    check("parse: domyślne", P("6-13,15-22") == (((6, 13), (15, 22)), None))
    check("parse: puste = domyślne", P("")[0] == tar.DEFAULT_PEAKS and P(None)[0] == tar.DEFAULT_PEAKS)
    check("parse: spacje i średnik", P(" 7 - 13 ; 16-21 ")[0] == ((7, 13), (16, 21)))
    check("parse: godziny z :00", P("06:00-13:00,15:00-22:00")[0] == ((6, 13), (15, 22)))
    check("parse: pojedyncze", P("7-21")[0] == ((7, 21),))
    check("parse: brak", P("brak")[0] == () and P("G11")[0] == ())
    check("parse: sortowanie", P("15-22,6-13")[0] == ((6, 13), (15, 22)))
    check("parse: styczne scalane", P("6-13,13-22")[0] == ((6, 22),))
    check("parse: nachodzące -> błąd", P("6-14,13-22")[0] is None and "nachodzą" in P("6-14,13-22")[1])
    check("parse: start>=koniec -> błąd", P("13-6")[0] is None and P("6-6")[0] is None)
    check("parse: 25 -> błąd", P("6-25")[0] is None)
    check("parse: minuty -> błąd", P("6:30-13")[0] is None)
    check("parse: tekst -> błąd", P("rano")[0] is None)
    check("parse: 3 okna -> błąd", P("1-2,3-4,5-6")[0] is None)
    check("parse: 24 jako koniec", P("0-6,22-24")[0] == ((0, 6), (22, 24)))

    # ------------------------------------------------ domyślny profil == stara logika (cały rok, co godzinę)
    tar.set_profile(None)
    bad = 0
    d = datetime(2026, 1, 1, tzinfo=TZ)
    for i in range(24 * 366):
        t = d + timedelta(hours=i)
        if tar.is_g12w_peak(t) != legacy_peak(t):
            bad += 1
    check("taryfa: profil domyślny identyczny ze starą logiką (8784 godz.)", bad == 0, bad)

    # ------------------------------------------------ okna profilu
    prof = tar.TariffProfile()
    check("profil: noc 22–6, południe 13–15", prof.night_window() == (22, 6) and prof.midday_window() == (13, 15))
    check("profil: jeden szczyt 7-21 -> noc (21,7), brak południa",
          tar.TariffProfile(peaks=((7, 21),)).night_window() == (21, 7) and tar.TariffProfile(peaks=((7, 21),)).midday_window() is None)
    check("profil: brak szczytów -> brak okien", tar.TariffProfile(peaks=()).night_window() is None)
    check("profil: szczyt 0–24 -> brak nocy", tar.TariffProfile(peaks=((0, 24),)).night_window() is None)
    check("profil: koniec 24 -> noc od północy", tar.TariffProfile(peaks=((6, 24),)).night_window() == (24, 6))

    # ------------------------------------------------ weekendy/święta konfigurowalne
    sat = datetime(2026, 10, 24, 10, tzinfo=TZ)
    wed = datetime(2026, 10, 28, 10, tzinfo=TZ)
    hol = datetime(2026, 11, 11, 10, tzinfo=TZ)    # Święto Niepodległości (środa)
    g12 = tar.TariffProfile(weekend_offpeak=False, holiday_offpeak=False)
    check("G12 (bez tańszych weekendów): sobota 10 = szczyt", g12.is_peak(sat) and g12.is_peak(wed) and g12.is_peak(hol))
    mixed = tar.TariffProfile(weekend_offpeak=True, holiday_offpeak=False)
    check("weekend tani, święto drogie", (not mixed.is_peak(sat)) and mixed.is_peak(hol))
    tar.set_profile(g12)
    check("is_g12w_peak używa ustawionego profilu", tar.is_g12w_peak(sat))
    w = tar.next_offpeak_window(sat.replace(hour=5))
    check("next_offpeak: G12 sobota 05:00 -> trwa teraz do 06:00", w and w[2] and w[1].hour == 6, w)
    tar.set_profile(tar.TariffProfile())     # G12w: weekend całodobowo tani
    sat_n = datetime(2026, 11, 7, 3, 41, tzinfo=TZ)
    w = tar.next_offpeak_window(sat_n)
    check("next_offpeak: sobota 03:41 (G12w) -> okno trwa do poniedziałku 06:00, nie do 03:00 (limit 48 h)",
          w and w[2] and (w[1].day, w[1].hour) == (9, 6), w)
    hol_n = datetime(2026, 11, 10, 22, 30, tzinfo=TZ)   # wtorek wieczór przed świętem (środa 11.11)
    w = tar.next_offpeak_window(hol_n)
    check("next_offpeak: wtorek 22:30 przed świętem -> do czwartku 06:00", w and w[2] and (w[1].day, w[1].hour) == (12, 6), w)
    tar.set_profile(tar.TariffProfile(peaks=()))
    check("next_offpeak: taryfa jednostrefowa -> None", tar.next_offpeak_window(wed) is None)
    tar.set_profile(None)

    # ------------------------------------------------ profile_from_config
    pr = tar.profile_from_config({"tariff_peaks": "7-13,16-21", "tariff_weekend_offpeak": False})
    check("z konfiguracji", pr.peaks == ((7, 13), (16, 21)) and not pr.weekend_offpeak and pr.holiday_offpeak)
    pr = tar.profile_from_config({"tariff_peaks": "bzdura"})
    check("z konfiguracji: błędny tekst -> domyślne", pr.peaks == tar.DEFAULT_PEAKS)
    check("z konfiguracji: pusta -> domyślne", tar.profile_from_config({}).peaks == tar.DEFAULT_PEAKS)

    # ------------------------------------------------ planer z innym profilem
    # (a) G12 Enea-podobna: szczyt 6-13,15-22 także w weekend (weekend_offpeak=False)
    tar.set_profile(tar.TariffProfile(weekend_offpeak=False, holiday_offpeak=False))
    hass, c, sched = await mk((2026, 11, 7, 10), 30, shutdown=25)   # sobota
    m1 = (await sched.suggest())["proposals"]["start_grid_charge_2"]
    check("planer G12: sobota też ma okno 13–15", (not m1["skip"]) and m1["proposed"] in ("13:00", "14:00"), m1["reason"])
    # (b) inne okna: 7-13,16-21 → noc 21–7, południe 13–16
    tar.set_profile(tar.TariffProfile(peaks=((7, 13), (16, 21))))
    hass, c, sched = await mk((2026, 11, 3, 10), 15, shutdown=10)
    out = (await sched.suggest())["proposals"]
    m1, m2 = out["start_grid_charge_2"], out["stop_grid_charge_2"]
    check("planer 7-13,16-21: południe 13–16 (stop o 16:00)", (not m1["skip"]) and m2["proposed"] == "16:00" and m1["proposed"] in ("13:00", "14:00", "15:00"), (m1, m2))
    check("planer 7-13,16-21: opis zawiera właściwe godziny", "16–21" in m1["reason"] and "21:00" in m1["reason"], m1["reason"])
    hass, c, sched = await mk((2026, 11, 2, 20), 35, shutdown=25)
    n1, n2 = (await sched.suggest())["proposals"]["start_grid_charge"], None
    check("planer 7-13,16-21: noc, ładowanie kończy się o 07:00", (not n1["skip"]) and "07:00" in n1["reason"], n1["reason"])
    check("planer: nocne ładowanie oznaczone jako wymagane (bez zysku w zł)", n1.get("required") is True and "gain_pln" not in n1, n1)
    sell = (await sched.suggest())["proposals"]
    check("planer 7-13,16-21: sprzedaż w oknach 7-13 / 16-21", all(k in sell for k in ("bateria_sprzedaz_start", "bateria_sprzedaz_start_2")))
    for k in ("bateria_sprzedaz_start", "bateria_sprzedaz_start_2"):
        v = sell[k]
        if not v["skip"]:
            hh = int(v["proposed"][:2])
            lo, hi = ((7, 13) if k.endswith("start") else (16, 21))
            check(f"sprzedaż {k}: start {v['proposed']} w oknie {lo}-{hi}", lo <= hh < hi, v)
    # (c) jeden szczyt 7-21 → brak zestawu 2 sprzedaży i brak okna południowego
    tar.set_profile(tar.TariffProfile(peaks=((7, 21),)))
    hass, c, sched = await mk((2026, 11, 3, 10), 30, shutdown=25)
    out = (await sched.suggest())["proposals"]
    check("jeden szczyt: zestaw 2 sprzedaży pominięty z powodem", out["bateria_sprzedaz_start_2"]["skip"] and "nie ma tego szczytu" in out["bateria_sprzedaz_start_2"]["reason"], out["bateria_sprzedaz_start_2"])
    check("jeden szczyt: okno południowe pominięte", out["start_grid_charge_2"]["skip"] and "nie ma taniego okna" in out["start_grid_charge_2"]["reason"], out["start_grid_charge_2"]["reason"])
    # (d) taryfa jednostrefowa
    tar.set_profile(tar.TariffProfile(peaks=()))
    hass, c, sched = await mk((2026, 11, 2, 21), 30, shutdown=25)
    out = (await sched.suggest())["proposals"]
    check("jednostrefowa: brak ładowania nocnego", out["start_grid_charge"]["skip"] and "nie ma taniego okna nocnego" in out["start_grid_charge"]["reason"], out["start_grid_charge"]["reason"])
    check("jednostrefowa: sprzedaż pominięta w obu zestawach", out["bateria_sprzedaz_start"]["skip"] and out["bateria_sprzedaz_start_2"]["skip"])
    tar.set_profile(None)
    # (e) domyślny profil: nic się nie zmieniło względem 0.5.0
    hass, c, sched = await mk((2026, 11, 2, 21), 35, shutdown=25)
    n = (await sched.suggest())["proposals"]["start_grid_charge"]
    check("domyślny: noc SOC 35 próg 25 -> ładowanie", (not n["skip"]) and "06:00" in n["reason"], n["reason"])

    # ------------------------------------------------ wykrywanie encji falownika
    hass, c, opt, rt = build()
    check("resolve: konfiguracja istnieje", rt.eid("work_mode") == "select.inverter_work_mode" and rt.eid("tou_select") == "select.inverter_time_of_use")
    # inny prefiks: stare encje nie istnieją
    hass2 = stubs.FakeHass(); S2 = hass2.states
    S2.set("select.deye_work_mode", "Zero Export To Load", {"options": ["Selling First", "Zero Export To Load", "Zero Export To CT"]})
    S2.set("number.deye_battery_max_charging_current", 120, {"max": 120, "min": 0})
    S2.set("number.deye_export_surplus_power", 5000, {"max": 5000})
    S2.set("select.deye_time_of_use", "Week", {"options": ["Disabled", "Week"]})
    cfg = dict(const.DEFAULT_CONFIG)
    check("resolve: prefiks wykryty po sąsiedzie (work_mode)", ictl.resolve(hass2, cfg, "work_mode") == "select.deye_work_mode")
    check("resolve: prefiks wykryty (export_surplus)", ictl.resolve(hass2, cfg, "export_surplus") == "number.deye_export_surplus_power")
    check("resolve: prefiks wykryty (tou)", ictl.resolve(hass2, cfg, "tou_select") == "select.deye_time_of_use")
    check("resolve: prefiks wykryty (charge_current)", ictl.resolve(hass2, cfg, "charge_current") == "number.deye_battery_max_charging_current")
    cfg2 = dict(cfg, work_mode="select.deye_work_mode")
    check("resolve: jawna konfiguracja wygrywa", ictl.resolve(hass2, cfg2, "work_mode") == "select.deye_work_mode")
    S2.set("select.inny_work_mode", "x")
    check("resolve: config wskazuje istniejącą -> bez zgadywania", ictl.resolve(hass2, dict(cfg, work_mode="select.inny_work_mode"), "work_mode") == "select.inny_work_mode")
    check("resolve: nic nie istnieje -> nazwa domyślna", ictl.resolve(stubs.FakeHass(), cfg, "tou_select") == "select.inverter_time_of_use")

    # ------------------------------------------------ opcje select
    check("opcje: Selling First dla „export”", ictl.pick_option(hass2, "select.deye_work_mode", "export") == "Selling First")
    check("opcje: Zero Export To Load", ictl.pick_option(hass2, "select.deye_work_mode", "zero") == "Zero Export To Load")
    S2.set("select.x_mode", "a", {"options": ["Batt First", "Load First"]})
    check("opcje: brak pasującej -> None (nie zgadujemy)", ictl.pick_option(hass2, "select.x_mode", "export") is None)
    S2.set("select.noopts", "a")
    check("opcje: brak listy -> domyślna", ictl.pick_option(hass2, "select.noopts", "export") == "Export First")
    S2.set("select.lc", "a", {"options": ["export first", "zero export to load"]})
    check("opcje: wielkość liter ignorowana, zwraca nazwę z listy", ictl.pick_option(hass2, "select.lc", "export") == "export first")
    check("matches_option", ictl.matches_option(hass2, "x", "EXPORT FIRST", "export") and ictl.matches_option(hass2, "x", "Selling First", "export")
          and not ictl.matches_option(hass2, "x", "Zero Export To Load", "export") and not ictl.matches_option(hass2, "x", None, "export"))

    # ------------------------------------------------ komendy: inny falownik
    hass, c, opt, rt = build(hass2)
    S = hass.states
    for k in [k for k in S._s if k.startswith(("select.inverter_", "number.inverter_"))]:
        S._s.pop(k)                       # ten falownik ma prefiks „deye”, nie „inverter”
    for k, *_ in const.NUMBERS: S.set(f"number.bms_{k}", const.NUMBER_DEFAULTS[k])
    for k, _n, _i, d in const.SWITCHES: S.set(f"switch.bms_{k}", "on" if d else "off")
    S.set("sensor.rce_pse_cena", 0.6)
    hass.services.calls.clear()
    await rt.run_command("sprzedaz_6000w", source="ręcznie", enforce_guard=False)
    cs = [(d, s, dict(x)) for d, s, x in hass.services.calls]
    check("deye: sprzedaż -> select Selling First na select.deye_work_mode",
          cs[0][2] == {"entity_id": "select.deye_work_mode", "option": "Selling First"}, cs)
    check("deye: moc sprzedaży przycięta do limitu encji (5000 < 6000)",
          cs[1][2] == {"entity_id": "number.deye_export_surplus_power", "value": 5000}, cs)
    await settle(hass)
    hass.services.calls.clear()
    await rt.run_command("odblokuj_ladowanie", source="ręcznie")
    check("deye: odblokuj -> 120 A (limit encji), nie 170", hass.services.calls[0][2]["value"] == 120, hass.services.calls)
    hass.services.calls.clear()
    await rt.run_command("wlacz_ladowanie_siec", source="ręcznie")
    check("deye: ładowanie z sieci -> TOU Disabled na select.deye_time_of_use",
          hass.services.calls[0][2] == {"entity_id": "select.deye_time_of_use", "option": "Disabled"}, hass.services.calls)
    check("deye: grid_charging_on() rozpoznaje stan", rt.grid_charging_on())
    hass.services.calls.clear()
    await rt.run_command("wylacz_ladowanie_siec", source="ręcznie")
    check("deye: wyłącz ładowanie -> TOU Week", hass.services.calls[0][2]["option"] == "Week" and not rt.grid_charging_on())
    await settle(hass)

    # brak wymaganej opcji -> błąd bez żadnego wywołania
    S.set("select.deye_work_mode", "Batt First", {"options": ["Batt First", "Load First"]})
    hass.services.calls.clear()
    try:
        await rt.run_command("sprzedaz_6000w", source="ręcznie", enforce_guard=False)
        check("brak opcji: powinien zgłosić błąd", False)
    except HomeAssistantError as e:
        check("brak opcji: błąd i zero wywołań usług", not hass.services.calls and "nie ma oczekiwanej opcji" in str(e), (e, hass.services.calls))
    # brak encji -> błąd, zero wywołań (komenda nie zostaje „w połowie”)
    hass3 = stubs.FakeHass(); S3 = hass3.states
    S3.set("select.inverter_work_mode", "Zero Export To Load")
    S3.set("number.bms_sell_export_power_w", 6000)
    hass3, c3, opt3, rt3 = build(hass3)
    hass3.states._s.pop("number.inverter_export_surplus_power", None)
    hass3.services.calls.clear()
    try:
        await rt3.run_command("sprzedaz_6000w", source="ręcznie", enforce_guard=False)
        check("brak encji: powinien zgłosić błąd", False)
    except HomeAssistantError as e:
        check("brak encji: czytelny błąd, zero wywołań", not hass3.services.calls and "nie znaleziono encji" in str(e), (e, hass3.services.calls))

    # ------------------------------------------------ prąd ładowania
    hass, c, opt, rt = build()
    S = hass.states
    hass.services.calls.clear()
    await rt.run_command("odblokuj_ladowanie", source="ręcznie")
    check("prąd: domyślnie 170 (stare zachowanie)", hass.services.calls[0][2]["value"] == 170)
    S.set("number.inverter_battery_max_charging_current", 140)
    rt._remember_charge_current()
    check("prąd: zapamiętuje ostatnią wartość > 0", rt.state["normal_charge_current"] == 140)
    await rt.run_command("zablokuj_ladowanie", source="ręcznie")
    check("blokada ustawia 0 i nie nadpisuje zapamiętanej wartości", hass.states.get("number.inverter_battery_max_charging_current").state == "0" and (rt._remember_charge_current() or True) and rt.state["normal_charge_current"] == 140)
    hass.services.calls.clear()
    await rt.run_command("odblokuj_ladowanie", source="ręcznie")
    check("prąd: odblokowanie przywraca zapamiętane 140 A", hass.services.calls[0][2]["value"] == 140, hass.services.calls)
    S.set("number.bms_normal_charge_current", 100)
    hass.services.calls.clear()
    await rt.run_command("odblokuj_ladowanie", source="ręcznie")
    check("prąd: ustawienie użytkownika (100 A) ma pierwszeństwo", hass.services.calls[0][2]["value"] == 100)
    S.set("number.bms_normal_charge_current", 400)
    hass.services.calls.clear()
    await rt.run_command("odblokuj_ladowanie", source="ręcznie")
    check("prąd: wartość przycięta do max encji (185)", hass.services.calls[0][2]["value"] == 185, hass.services.calls)
    # moce z numberów
    S.set("number.bms_sell_export_power_w", 4000); S.set("number.bms_surplus_power_w", 8000)
    hass.services.calls.clear()
    await rt.run_command("sprzedaz_6000w", source="ręcznie", enforce_guard=False)
    await rt.run_command("nadwyzka_9700w", source="ręcznie")
    vals = [c[2].get("value") for c in hass.services.calls if c[0] == "number"]
    check("moce: sprzedaż 4000, nadwyżka 8000 z ustawień", vals == [4000, 8000], vals)
    await settle(hass)

    # ------------------------------------------------ is_selling dla różnych nazw
    hass, c, opt, rt = build()
    hass.states.set("select.inverter_work_mode", "Export First")
    check("is_selling: Export First", rt.is_selling())
    hass.states.set("select.inverter_work_mode", "Selling First")
    check("is_selling: Selling First", rt.is_selling())
    hass.states.set("select.inverter_work_mode", "Zero Export To Load")
    check("is_selling: Zero Export -> False", not rt.is_selling())

    import common
    print(f"STAGE1 PASS={common.PASS} FAIL={common.FAIL}")
    tar.set_profile(None)

asyncio.run(main())
