"""Własne profile i profil z datami: zapis bieżących ustawień (lista dozwolonych), nazwy, limity, zastosowanie, plan od–do (start, koniec,
wznowienie poprzedniego profilu, restart HA, ręczne cofnięcie), usługi i uprawnienia, odporność zapisu."""
import asyncio, json, sys, types
from datetime import date
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import profiles as P, state_guard, const, notify_cfg as N
import custom_components.bms_komp_dec as pkg
from stubs import HomeAssistantError, Unauthorized

TODAY = date(2026, 11, 20)


def pure():
    # --- lista dozwolonych ustawień
    bad = [k for k in P.CUSTOM_KEYS if P.kind(k) is None]
    check("wszystkie klucze dozwolone dla własnych profili istnieją jako encje", not bad, bad)
    check("bez duplikatów", len(P.CUSTOM_KEYS) == len(set(P.CUSTOM_KEYS)))
    forbidden = ("inverter_floor_soc", "sell_export_power_w", "surplus_power_w", "normal_charge_current", "battery_charge_sign", "grid_charge_power_kw",
                 "grid_import_limit_kw", "force_charge_battery", "auto_apply", "auto_apply_dry_run", "recurring_schedule", "bateria_sprzedaz_1", "bateria_sprzedaz_2",
                 "ladowanie_z_sieci_1", "ladowanie_z_sieci_2", "dzien_pn", "dzien_nd", "holidays_as_sunday", "readback_verify", "brand_test_mode",
                 "grid_arbitrage_block_kwh", "grid_import_sell_block_w", "grid_import_sell_block_kwh", "grid_import_daily_limit", "battery_price_pln", "cycle_efficiency",
                 "simple_mode", "tabs_top", "hide_devices_tab")
    check("sprzęt, harmonogram i ZABEZPIECZENIA (blokada arbitrażu / importu) poza profilami własnymi", not [k for k in forbidden if k in P.CUSTOM_KEYS], [k for k in forbidden if k in P.CUSTOM_KEYS])

    # --- nazwy
    check("nazwa: spacje zwinięte i przycięcie", P.clean_name("  Mój   weekend  ") == "Mój weekend" and len(P.clean_name("x" * 60)) == 24)
    check("nazwa: HTML i znaki sterujące wycięte", P.clean_name("<b>Zima</b>\n&\"x'") == "b Zima /b x" or "<" not in P.clean_name("<b>Zima</b>"), P.clean_name("<b>Zima</b>\n&\"x'"))
    check("nazwa: pusta / same znaki specjalne / nie napis → None", all(P.clean_name(v) is None for v in ("", "   ", "<>&", None, 5, ["a"], "\x00\x01")))

    # --- id
    check("id: własne u_N", P.is_custom_id("u_1") and P.is_custom_id("u_999999") and not P.is_custom_id("u_") and not P.is_custom_id("u_1234567") and not P.is_custom_id("winter") and not P.is_custom_id(5) and not P.is_custom_id("u_1;x"))
    check("valid_id: gotowe i własne", P.valid_id("winter") and P.valid_id("u_3") and not P.valid_id("zła") and not P.valid_id(None))
    check("get: tylko gotowe", P.get("winter") and P.get("u_1") is None)

    # --- make_custom / clean_custom
    vals = {"sell_enabled": True, "reserve_floor_soc": 22.0, "pv_plan_pessimism_pct": 35.0, "inverter_floor_soc": 12.0, "auto_apply": True, "vacation_mode": False}
    read = vals.get
    lst, rec, rep = P.make_custom("Weekend", "🏠", read, [], "2026-11-20T10:00:00+01:00")
    check("zapis: tylko ustawienia z listy dozwolonych i dostępne", rec["set"] == {"sell_enabled": True, "vacation_mode": False, "pv_plan_pessimism_pct": 35.0, "reserve_floor_soc": 22.0}, rec["set"])
    check("zapis: id u_1, ikona, nie zastąpiono", rec["id"] == "u_1" and rec["icon"] == "🏠" and rep is False and rec["custom"] is True and len(lst) == 1)
    check("zapis: opis zawiera datę i liczbę ustawień", "2026-11-20" in rec["desc"] and "4 ustawienia" in rec["desc"], rec["desc"])
    lst2, rec2, rep2 = P.make_custom("Inny", "💥", read, lst, "2026-11-21T10:00:00+01:00")
    check("drugi profil dostaje u_2, zła ikona → domyślna", rec2["id"] == "u_2" and rec2["icon"] == P.DEFAULT_ICON and len(lst2) == 2)
    lst3, rec3, rep3 = P.make_custom("  weekend ", "☀️", {"sell_enabled": False}.get, lst2, "2026-11-22T10:00:00+01:00")
    check("ta sama nazwa (bez względu na wielkość liter) nadpisuje profil, id zostaje", rep3 and rec3["id"] == "u_1" and len(lst3) == 2 and rec3["set"] == {"sell_enabled": False} and rec3["icon"] == "☀️", rec3)
    lst4, rec4, _ = P.make_custom("Trzeci", None, read, [r for r in lst3 if r["id"] != "u_1"], "x")
    check("wolne id po usunięciu jest ponownie używane najmniejsze", rec4["id"] == "u_1")
    for name, args in (("pusta nazwa", ("  ", None, read, [], "x")), ("brak dostępnych ustawień", ("A", None, {}.get, [], "x")), ("wszystkie wartości spoza zakresu", ("A", None, {"reserve_floor_soc": 999, "sell_enabled": "tak"}.get, [], "x"))):
        try:
            P.make_custom(*args); e = None
        except ValueError as err:
            e = str(err)
        check(f"zapis: {name} → ValueError po polsku", e and len(e) > 10, e)
    full = []
    for i in range(P.MAX_CUSTOM):
        full, _r, _ = P.make_custom(f"P{i}", None, read, full, "x")
    try:
        P.make_custom("Dziewiąty", None, read, full, "x"); e = None
    except ValueError as err:
        e = str(err)
    check(f"limit {P.MAX_CUSTOM} profili", e and "Limit" in e and len(full) == P.MAX_CUSTOM, e)
    _l, _r, rep = P.make_custom("p3", None, read, full, "x")
    check("przy pełnej liście można nadpisać istniejący", rep is True and len(_l) == P.MAX_CUSTOM)

    good = {"id": "u_4", "name": "Test", "icon": "🏠", "saved": "2026-11-20T10:00:00", "set": {"sell_enabled": True, "reserve_floor_soc": 20}}
    check("clean_custom: poprawny przechodzi", len(P.clean_custom([good])) == 1 and P.clean_custom([good])[0]["set"] == {"sell_enabled": True, "reserve_floor_soc": 20.0})
    for name, it in (("nie słownik", "x"), ("zły id", dict(good, id="winter")), ("brak nazwy", dict(good, name="")), ("nazwa nie napis", dict(good, name=5)), ("set nie słownik", dict(good, set=[1])),
                     ("set pusty po czyszczeniu", dict(good, set={"reserve_floor_soc": 999, "inverter_floor_soc": 10, "auto_apply": True})), ("set nan", dict(good, set={"reserve_floor_soc": float("nan")}))):
        check(f"clean_custom: {name} → odrzucone", P.clean_custom([it]) == [], it)
    c = P.clean_custom([dict(good, set={"reserve_floor_soc": 20, "inverter_floor_soc": 10, "auto_apply": True, 5: 1, "sell_enabled": "tak"}, icon="💥")])
    check("clean_custom: obce klucze, złe typy i ikona czyszczone pojedynczo", c[0]["set"] == {"reserve_floor_soc": 20.0} and c[0]["icon"] == P.DEFAULT_ICON, c)
    check("clean_custom: duplikaty id i limit", len(P.clean_custom([good, good])) == 1 and len(P.clean_custom([dict(good, id=f"u_{i}") for i in range(1, 30)])) == P.MAX_CUSTOM)
    check("clean_custom: nie lista → []", P.clean_custom(None) == [] and P.clean_custom("x") == [] and P.clean_custom({}) == [])
    check("find: gotowy, własny, brak", P.find("winter", []) and P.find("u_4", []) is None and P.find("u_4", P.clean_custom([good]))["name"] == "Test" and P.find("u_9", P.clean_custom([good])) is None)
    check("clean_state przyjmuje własne id", P.clean_state({"id": "u_4", "since": "x", "prev": {"reserve_floor_soc": 15}, "applied": {"reserve_floor_soc": 20}, "ended": None})["id"] == "u_4"
          and P.clean_state({"id": "zła", "since": "x", "prev": {}, "applied": {"reserve_floor_soc": 20}}) is None)

    # --- plan z datami
    ok_plan = P.check_plan("vacation", "2026-12-20", "2026-12-28", TODAY, [])
    check("plan: poprawny", ok_plan == {"id": "vacation", "from": "2026-12-20", "to": "2026-12-28", "status": "waiting", "resume": None}, ok_plan)
    check("plan: dziś jako start i jednodniowy plan", P.check_plan("summer", "2026-11-20", "2026-11-20", TODAY, [])["from"] == "2026-11-20")
    for name, args in (("nieznany profil", ("xx", "2026-12-01", "2026-12-02")), ("własny nieistniejący", ("u_1", "2026-12-01", "2026-12-02")), ("brak dat", ("vacation", None, "2026-12-02")),
                       ("zły format", ("vacation", "01.12.2026", "2026-12-02")), ("start z przeszłości", ("vacation", "2026-11-19", "2026-12-02")),
                       ("koniec przed startem", ("vacation", "2026-12-05", "2026-12-02")), ("za długi (181 dni)", ("vacation", "2026-11-20", "2027-05-19")),
                       ("data nie istnieje", ("vacation", "2026-02-30", "2026-03-02"))):
        try:
            P.check_plan(*args, TODAY, []); e = None
        except ValueError as err:
            e = str(err)
        check(f"plan: {name} → ValueError", e, args)
    check("plan: 180 dni dozwolone", P.check_plan("vacation", "2026-11-20", "2027-05-18", TODAY, []) is not None)
    check("plan: własny profil z listy", P.check_plan("u_4", "2026-12-01", "2026-12-02", TODAY, P.clean_custom([good]))["id"] == "u_4")
    pl = {"id": "vacation", "from": "2026-12-20", "to": "2026-12-28", "status": "active", "resume": "winter"}
    check("clean_plan: poprawny przechodzi", P.clean_plan(pl) == pl)
    for name, bad_ in (("nie słownik", "x"), ("zły profil", dict(pl, id="zz")), ("zła data", dict(pl, to="x")), ("koniec przed startem", dict(pl, to="2026-12-01")), ("zły status", dict(pl, status="done"))):
        check(f"clean_plan: {name} → None", P.clean_plan(bad_) is None)
    check("clean_plan: zły resume → None w polu", P.clean_plan(dict(pl, resume="zz"))["resume"] is None)
    check("plan_phase: przed / w trakcie / po", [P.plan_phase(pl, date(2026, 12, d)) for d in (19, 20, 24, 28, 29)] == ["before", "during", "during", "during", "after"])


def nv(S, eid):
    return float(S.get(eid).state)


def logs(rt, text):
    return [e for e in rt.log.last(100) if e.get("kind") == "mode" and text in str(e.get("msg", ""))]


def pn(hass, frag):
    return [c for c in hass.services.calls if c[0] == "persistent_notification" and c[1] == "create" and frag in c[2]["title"]]


async def runtime_part():
    at(2026, 11, 20, 10, 0)
    hass, c, opt, rt = build(); S = hass.states
    rt.state["notify_cfg"] = N.effective({"phone_level": "all"})
    v = rt.profile_view()
    check("widok: 3 gotowe, bez własnych i planu, limit i lista kluczy", len(v["profiles"]) == 3 and all(not p["custom"] for p in v["profiles"]) and v["plan"] is None and v["custom_limit"] == 8 and len(v["custom_keys"]) == len(P.CUSTOM_KEYS))
    # zapis bieżących ustawień
    S.set("number.bms_reserve_floor_soc", 25); S.set("number.bms_pv_plan_pessimism_pct", 30); S.set("switch.bms_sell_enabled", "off")
    res = rt.profile_save("Weekend", "🏠")
    check("save: id u_1, nie nadpisano", res["ok"] and res["id"] == "u_1" and res["replaced"] is False, res)
    rec = rt.state["custom_profiles"][0]
    check("save: wartości z encji, tylko z listy dozwolonych", rec["set"]["reserve_floor_soc"] == 25.0 and rec["set"]["pv_plan_pessimism_pct"] == 30.0 and rec["set"]["sell_enabled"] is False and "inverter_floor_soc" not in rec["set"] and "auto_apply" not in rec["set"], rec["set"])
    check("save: wpis w dzienniku", len(logs(rt, "Zapisano własny profil „Weekend”")) == 1)
    v = rt.profile_view()
    wk = next(p for p in v["profiles"] if p["id"] == "u_1")
    check("widok: własny profil na liście z flagą custom, ikoną i niczym do zmiany", wk["custom"] and wk["icon"] == "🏠" and wk["nothing_to_change"] is True, wk)
    json.dumps(v, allow_nan=False)
    # zmiana ustawień, zastosowanie własnego
    S.set("number.bms_reserve_floor_soc", 15); S.set("number.bms_pv_plan_pessimism_pct", 0); S.set("switch.bms_sell_enabled", "on")
    wk = next(p for p in rt.profile_view()["profiles"] if p["id"] == "u_1")
    check("widok: po zmianie ustawień własny profil pokazuje różnice", not wk["nothing_to_change"] and any(x["key"] == "reserve_floor_soc" and x["now_text"] == "15 %" and x["target_text"] == "25 %" for x in wk["changes"]))
    res = await rt.apply_profile("u_1")
    check("apply własnego: wartości wróciły do zapisanych", res["ok"] and res["changed"] == 3 and nv(S, "number.bms_reserve_floor_soc") == 25 and nv(S, "number.bms_pv_plan_pessimism_pct") == 30 and S.get("switch.bms_sell_enabled").state == "off", res)
    check("apply własnego: stan profilu z id u_1 i wpis „Weekend”", rt.state["profile"]["id"] == "u_1" and len(logs(rt, "Włączono profil „Weekend”")) == 1)
    v = rt.profile_view()
    check("widok: aktywny własny profil z nazwą i listą do przywrócenia", v["active"]["id"] == "u_1" and v["active"]["name"] == "Weekend" and v["active"]["can_revert"] and len(v["active"]["restore"]) == 3, v["active"])
    res = await rt.revert_profile()
    check("revert własnego: poprzednie ustawienia z powrotem", nv(S, "number.bms_reserve_floor_soc") == 15 and S.get("switch.bms_sell_enabled").state == "on" and len(logs(rt, "Cofnięto profil „Weekend”")) == 1, res)
    # nadpisanie, usunięcie
    res = rt.profile_save(" weekend", None)
    check("save o tej samej nazwie nadpisuje", res["replaced"] and len(rt.state["custom_profiles"]) == 1 and rt.state["custom_profiles"][0]["set"]["reserve_floor_soc"] == 15.0)
    for bad_name in ("", "   ", None, "<>"):
        try:
            rt.profile_save(bad_name); e = False
        except ValueError:
            e = True
        check(f"save: zła nazwa {bad_name!r} → ValueError", e)
    for pid in ("winter", "u_9", None, 5):
        try:
            rt.profile_delete(pid); e = False
        except ValueError:
            e = True
        check(f"delete: {pid!r} → ValueError (gotowych nie usuwa, nieistniejącego nie ma)", e)
    res = rt.profile_delete("u_1")
    check("delete: usunięto", res["ok"] and rt.state["custom_profiles"] == [] and len(logs(rt, "Usunięto własny profil „weekend”")) == 1)
    try:
        await rt.apply_profile("u_1"); e = False
    except ValueError:
        e = True
    check("apply usuniętego → ValueError", e)

    # aktywny własny profil, potem jego usunięcie: widok i powrót nadal działają
    hass, c, opt, rt = build(); S = hass.states
    S.set("number.bms_reserve_floor_soc", 25); rt.profile_save("Tymczasowy"); S.set("number.bms_reserve_floor_soc", 15)
    await rt.apply_profile("u_1"); rt.profile_delete("u_1")
    v = rt.profile_view()
    check("usunięcie aktywnego profilu: widok pokazuje „(usunięty)”, powrót możliwy", v["active"]["name"] == "Własny profil (usunięty)" and v["active"]["can_revert"], v["active"])
    await rt.revert_profile()
    check("…i powrót przywraca ustawienia", nv(S, "number.bms_reserve_floor_soc") == 15)

    # ---------- plan z datami: start, koniec
    at(2026, 11, 20, 10, 0)
    hass, c, opt, rt = build(); S = hass.states
    rt.state["notify_cfg"] = N.effective({"phone_level": "all"})
    res = rt.profile_schedule("vacation", "2026-11-22", "2026-11-24")
    check("schedule: plan zapisany jako waiting, wpis w dzienniku", rt.state["profile_plan"]["status"] == "waiting" and len(logs(rt, "Zaplanowano profil „Urlop” od 2026-11-22 do 2026-11-24")) == 1, res)
    v = rt.profile_view()
    check("widok: plan z nazwą i fazą „przed”", v["plan"]["name"] == "Urlop" and v["plan"]["phase"] == "before" and v["plan"]["from"] == "2026-11-22")
    await rt.profile_plan_tick(at(2026, 11, 21, 23, 59))
    check("przed startem: nic się nie dzieje", S.get("switch.bms_vacation_mode").state == "off" and rt.state["profile_plan"]["status"] == "waiting")
    await rt.profile_plan_tick(at(2026, 11, 22, 0, 1))
    check("pierwszego dnia po północy: profil włączony, plan active", S.get("switch.bms_vacation_mode").state == "on" and rt.state["profile"]["id"] == "vacation" and rt.state["profile_plan"]["status"] == "active", rt.state["profile_plan"])
    check("start: wpis i powiadomienie", len(logs(rt, "Zaplanowany profil „Urlop” włączony (do końca dnia 2026-11-24)")) == 1 and len(pn(hass, "włączono profil")) == 1)
    n_before = len(hass.services.calls)
    await rt.profile_plan_tick(at(2026, 11, 23, 12, 0)); await rt.profile_plan_tick(at(2026, 11, 24, 23, 59))
    check("w trakcie i ostatniego dnia: bez zmian i bez powtórnego włączania", S.get("switch.bms_vacation_mode").state == "on" and len(pn(hass, "włączono profil")) == 1 and rt.state["profile_plan"]["status"] == "active")
    try:
        rt.profile_schedule("summer", "2026-12-01", "2026-12-02"); e = False
    except ValueError as err:
        e = "jeszcze trwa" in str(err)
    check("nowy plan podczas trwającego → ValueError", e)
    await rt.profile_plan_tick(at(2026, 11, 25, 0, 1))
    check("po ostatnim dniu: profil cofnięty, plan wyczyszczony", S.get("switch.bms_vacation_mode").state == "off" and rt.state["profile"] is None and rt.state["profile_plan"] is None, rt.state.get("profile_plan"))
    check("koniec: wpis i powiadomienie", len(logs(rt, "Profil „Urlop” zakończony (minął ostatni dzień): przywrócono poprzednie ustawienia")) == 1 and len(pn(hass, "koniec profilu")) == 1)

    # ---------- plan wznawia poprzedni profil (Zima → Urlop → Zima)
    at(2026, 11, 20, 10, 0)
    hass, c, opt, rt = build(); S = hass.states
    await rt.apply_profile("winter")
    rt.profile_schedule("vacation", "2026-11-20", "2026-11-20")
    await rt.profile_plan_tick(at(2026, 11, 20, 10, 1))
    check("plan od dziś startuje od razu; poprzedni profil zapamiętany", rt.state["profile"]["id"] == "vacation" and rt.state["profile_plan"]["resume"] == "winter", rt.state["profile_plan"])
    await rt.profile_plan_tick(at(2026, 11, 21, 0, 5))
    check("po końcu wraca Zima (rezerwa 30, ostrożność 40)", rt.state["profile"]["id"] == "winter" and nv(S, "number.bms_reserve_floor_soc") == 30 and nv(S, "number.bms_pv_plan_pessimism_pct") == 40 and S.get("switch.bms_vacation_mode").state == "off", rt.state.get("profile"))
    check("wpis o wznowieniu poprzedniego profilu", len(logs(rt, "wrócił profil „Zima”")) == 1)

    # ---------- ręczne cofnięcie w trakcie planu: koniec nie rusza cudzych ustawień
    at(2026, 11, 20, 10, 0)
    hass, c, opt, rt = build(); S = hass.states
    rt.profile_schedule("vacation", "2026-11-20", "2026-11-22")
    await rt.profile_plan_tick(at(2026, 11, 20, 10, 1))
    await rt.revert_profile()
    await rt.profile_plan_tick(at(2026, 11, 21, 12, 0))
    check("ręczny powrót w trakcie planu: tick nie włącza go ponownie", rt.state["profile"] is None and S.get("switch.bms_vacation_mode").state == "off")
    S.set("switch.bms_vacation_mode", "on")                       # użytkownik włączył tryb urlopowy sam
    await rt.apply_profile("summer")                               # i wybrał inny profil
    await rt.profile_plan_tick(at(2026, 11, 23, 0, 5))
    check("koniec planu przy innym aktywnym profilu: cudzy profil nietknięty", rt.state["profile"]["id"] == "summer" and rt.state["profile_plan"] is None)
    check("wpis: nic do przywracania", len(logs(rt, "nic do przywracania")) == 1)

    # ---------- restart HA: spóźniony start, termin minął, usunięty profil
    at(2026, 11, 20, 10, 0)
    hass, c, opt, rt = build(); S = hass.states
    rt.profile_schedule("vacation", "2026-11-21", "2026-11-25")
    await rt.profile_plan_tick(at(2026, 11, 23, 9, 0))
    check("HA włączony dopiero w trakcie zakresu: profil startuje z opóźnieniem", rt.state["profile"]["id"] == "vacation" and rt.state["profile_plan"]["status"] == "active")
    at(2026, 11, 20, 10, 0)
    hass, c, opt, rt = build(); S = hass.states
    rt.state["notify_cfg"] = N.effective({"phone_level": "all"})
    rt.profile_schedule("vacation", "2026-11-21", "2026-11-25")
    await rt.profile_plan_tick(at(2026, 11, 28, 9, 0))
    check("HA włączony po terminie: profil się nie włącza, plan odrzucony z ostrzeżeniem", S.get("switch.bms_vacation_mode").state == "off" and rt.state["profile_plan"] is None and any(e.get("level") == "warn" and "termin już minął" in str(e.get("msg")) for e in rt.log.last(20)))
    check("…i powiadomienie o tym", len(pn(hass, "nie wystartował")) == 1)
    at(2026, 11, 20, 10, 0)
    hass, c, opt, rt = build(); S = hass.states
    S.set("number.bms_reserve_floor_soc", 25); rt.profile_save("Wyjazd")
    rt.profile_schedule("u_1", "2026-11-22", "2026-11-23")
    res = rt.profile_delete("u_1")
    check("usunięcie profilu, który czeka w planie, kasuje plan", res["dropped_plan"] and rt.state["profile_plan"] is None and len(logs(rt, "i jego plan z datami")) == 1)
    S.set("number.bms_reserve_floor_soc", 25); rt.profile_save("Wyjazd"); rt.profile_schedule("u_1", "2026-11-22", "2026-11-23")
    rt.state["custom_profiles"] = []                                # zapis zniknął (np. uszkodzony plik)
    await rt.profile_plan_tick(at(2026, 11, 22, 1, 0))
    check("profil zniknął przed startem: plan odrzucony, nic nie włączone", rt.state["profile_plan"] is None and rt.state.get("profile") is None and any("profil został usunięty" in str(e.get("msg")) for e in rt.log.last(20)))

    # ---------- anulowanie planu
    at(2026, 11, 20, 10, 0)
    hass, c, opt, rt = build(); S = hass.states
    rt.profile_schedule("vacation", "2026-11-25", "2026-11-26")
    res = await rt.profile_schedule_clear()
    check("anulowanie oczekującego planu", res["ok"] and rt.state["profile_plan"] is None and len(logs(rt, "Anulowano zaplanowany profil „Urlop”")) == 1)
    try:
        await rt.profile_schedule_clear(); e = False
    except ValueError:
        e = True
    check("anulowanie bez planu → ValueError", e)
    rt.profile_schedule("vacation", "2026-11-20", "2026-11-26")
    await rt.profile_plan_tick(at(2026, 11, 20, 10, 5))
    res = await rt.profile_schedule_clear()
    check("anulowanie trwającego planu kończy go od razu i cofa profil", rt.state["profile_plan"] is None and rt.state["profile"] is None and S.get("switch.bms_vacation_mode").state == "off" and len(logs(rt, "anulowany")) == 1)

    # ---------- uszkodzony zapis
    hass, c, opt, rt = build()
    rt.state["profile_plan"] = {"id": "zz", "from": "x"}
    await rt.profile_plan_tick(at(2026, 11, 22, 1, 0))
    check("uszkodzony plan: czyszczony bez wyjątku", rt.state["profile_plan"] is None)
    rt.state["custom_profiles"] = "śmieć"
    check("uszkodzone własne profile: widok działa", len(rt.profile_view()["profiles"]) == 3)
    st = {"custom_profiles": "x", "profile_plan": "y"}
    fixed = state_guard.sanitize(st)
    check("state_guard: śmieci → [] i None", st["custom_profiles"] == [] and st["profile_plan"] is None and "custom_profiles" in fixed and "profile_plan" in fixed, (st, fixed))
    st = {"custom_profiles": [{"id": "u_1", "name": "A", "set": {"reserve_floor_soc": 20, "auto_apply": True}}, {"id": "zły"}], "profile_plan": None}
    fixed = state_guard.sanitize(st)
    check("state_guard: zła zawartość czyszczona, poprawna zostaje", len(st["custom_profiles"]) == 1 and st["custom_profiles"][0]["set"] == {"reserve_floor_soc": 20.0} and "custom_profiles" in fixed, st)
    check("state_guard: poprawny stan bez zmian", state_guard.sanitize(st) == [])
    check("katalog: profile_plan ważny, domyślnie na telefon", N.PRIORITY["profile_plan"] == 2 and N.CATALOG["profile_plan"][4] is True)

    # ---------- usługi i uprawnienia
    at(2026, 11, 20, 10, 0)
    hass, c, opt, rt = build()
    users = {"adm": types.SimpleNamespace(is_admin=True), "usr": types.SimpleNamespace(is_admin=False)}
    async def get_user(uid): return users.get(uid)
    hass.auth = types.SimpleNamespace(async_get_user=get_user)
    pkg._get_runtime = lambda h_: rt
    pkg._register_services(hass)
    H = {n: hh for (d, n), (hh, _r) in hass.services.handlers.items() if d == "bms_komp_dec"}
    check("usługi zarejestrowane", all(n in H for n in ("profile_save", "profile_delete", "profile_schedule", "profile_schedule_clear")))
    def call(data, uid=None): return types.SimpleNamespace(data=data, context=types.SimpleNamespace(user_id=uid))
    for name, data in (("profile_save", {"name": "X"}), ("profile_delete", {"id": "u_1"}), ("profile_schedule", {"id": "vacation", "from": "2026-12-01", "to": "2026-12-02"}), ("profile_schedule_clear", {})):
        try:
            await H[name](call(data, "usr")); ok_ = False
        except Unauthorized:
            ok_ = True
        check(f"{name}: odrzuca zwykłego użytkownika", ok_)
    check("odrzucone wywołania nic nie zmieniły", not rt.state.get("custom_profiles") and not rt.state.get("profile_plan"))
    r = await H["profile_save"](call({"name": "Z usługi", "icon": "🌙"}, "adm"))
    check("profile_save: admin, odpowiedź z widokiem", r["ok"] and any(p["id"] == "u_1" and p["icon"] == "🌙" for p in r["profiles"]), r.get("id"))
    try:
        await H["profile_save"](call({"name": ""}, "adm")); ok_ = False
    except HomeAssistantError:
        ok_ = True
    check("profile_save: zła nazwa → HomeAssistantError", ok_)
    r = await H["profile_schedule"](call({"id": "u_1", "from": "2026-11-20", "to": "2026-11-21"}, "adm"))
    check("profile_schedule od dziś: włącza od razu, widok zawiera plan active", r["ok"] and r["plan"]["status"] == "active" and r["plan"]["phase"] == "during" and r["active"]["id"] == "u_1" and r["profiles"], r.get("plan"))
    try:
        await H["profile_schedule"](call({"id": "u_1", "from": "zła", "to": "2026-11-21"}, "adm")); ok_ = False
    except HomeAssistantError:
        ok_ = True
    check("profile_schedule: zła data → HomeAssistantError", ok_)
    r = await H["profile_schedule_clear"](call({}, None))
    check("profile_schedule_clear: automatyzacja (bez użytkownika)", r["ok"] and r["plan"] is None)
    r = await H["profile_delete"](call({"id": "u_1"}, "adm"))
    check("profile_delete: admin", r["ok"] and not any(p["custom"] for p in r["profiles"]))
    try:
        await H["profile_delete"](call({"id": "winter"}, "adm")); ok_ = False
    except HomeAssistantError:
        ok_ = True
    check("profile_delete gotowego → HomeAssistantError", ok_)
    r = await H["profiles_get"](call({}, "usr"))
    check("profiles_get dla zwykłego użytkownika zawiera plan i limit", "plan" in r and r["custom_limit"] == 8)


async def main():
    pure()
    await runtime_part()


asyncio.run(main())
print(f"PROFILES-CUSTOM PASS={common.PASS} FAIL={common.FAIL}")
