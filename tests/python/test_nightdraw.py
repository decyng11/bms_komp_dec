"""Nocny pobór wyższy niż zwykle: czysta logika (mediana nocy, progi), powiadomienie rano, pominięcie przy pracy urządzenia z EMS."""
import asyncio, sys
from datetime import date, timedelta
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import nightdraw as ND, notify_cfg as N, insights as INS

TODAY = date(2026, 11, 20)


def night(kw_by_hour=None, base_kw=0.2):
    """Doba 24 godzin z podanym zużyciem w godzinach 1–4 (kWh na godzinę = kW)."""
    return [(kw_by_hour or {}).get(h, base_kw) if h in ND.NIGHT_HOURS else 0.4 for h in range(24)]


def hist(n=8, kw=0.2):
    return {(TODAY - timedelta(days=i)).isoformat(): night(base_kw=kw) for i in range(1, n + 1)}


def pure():
    avg, n = ND.night_avg_w(night(base_kw=0.2))
    check("średnia nocna 200 W z 4 godzin", abs(avg - 200.0) < 1e-6 and n == 4, (avg, n))
    check("za mało godzin → None", ND.night_avg_w([None, 0.2, 0.2] + [None] * 21)[0] is None)
    check("śmieci → None", ND.night_avg_w(None)[0] is None and ND.night_avg_w([1, 2])[0] is None and ND.night_avg_w("x")[0] is None)
    check("wartości nan / ujemne / bool pomijane", ND.night_avg_w([0.0, float("nan"), -1, True, 0.3] + [None] * 19)[0] is None)
    b = ND.baseline(hist(), TODAY)
    check("baseline: mediana 200 W z 8 nocy", b and abs(b["w"] - 200.0) < 1e-6 and b["nights"] == 8, b)
    check("baseline: za mało nocy → None", ND.baseline(hist(3), TODAY) is None)
    h2 = hist(8)
    h2[(TODAY - timedelta(days=1)).isoformat()] = night(base_kw=3.0)
    check("baseline: jedna skrajna noc nie zmienia mediany", abs(ND.baseline(h2, TODAY)["w"] - 200.0) < 1e-6)
    check("baseline: dziś nie wchodzi do historii", ND.baseline({TODAY.isoformat(): night(), **hist(3)}, TODAY) is None)
    old = {(TODAY - timedelta(days=i)).isoformat(): night() for i in range(40, 50)}
    check("baseline: zbyt stare noce pomijane", ND.baseline(old, TODAY) is None)
    check("baseline: śmieci", ND.baseline(None, TODAY) is None and ND.baseline({"zła": [1] * 24, 5: []}, TODAY) is None)

    ev = ND.evaluate(night(base_kw=0.6), hist(), TODAY)
    check("noc 600 W vs 200 W → zgłoszenie 3×", ev and ev["avg_w"] == 600.0 and ev["base_w"] == 200.0 and ev["ratio"] == 3.0 and ev["extra_w"] == 400.0 and ev["nights"] == 8, ev)
    check("noc 250 W vs 200 W → bez zgłoszenia", ND.evaluate(night(base_kw=0.25), hist(), TODAY) is None)
    check("noc 80 W vs 40 W (podwojenie, ale małe wartości) → bez zgłoszenia", ND.evaluate(night(base_kw=0.08), hist(kw=0.04), TODAY) is None)
    check("noc 300 W vs 100 W: ×3, ale +200 W ≥ 150 → zgłoszenie", ND.evaluate(night(base_kw=0.3), hist(kw=0.1), TODAY) is not None)
    check("noc 240 W vs 50 W: poniżej progu bezwzględnego 250 W → bez zgłoszenia", ND.evaluate(night(base_kw=0.24), hist(kw=0.05), TODAY) is None)
    check("noc 500 W vs 400 W (×1,25) → bez zgłoszenia przy progu 1,6", ND.evaluate(night(base_kw=0.5), hist(kw=0.4), TODAY) is None)
    check("własny próg 1,2×: ×1,36 i +160 W → zgłoszenie", ND.evaluate(night(base_kw=0.6), hist(kw=0.44), TODAY, ratio=1.2) is not None)
    check("własny próg 1,2×: ×1,25, ale tylko +120 W → bez zgłoszenia", ND.evaluate(night(base_kw=0.6), hist(kw=0.48), TODAY, ratio=1.2) is None)
    check("próg poniżej 1,2 jest podnoszony do 1,2", ND.evaluate(night(base_kw=0.55), hist(kw=0.5), TODAY, ratio=0.1) is None)
    check("brak historii → None", ND.evaluate(night(base_kw=2.0), {}, TODAY) is None and ND.evaluate(None, hist(), TODAY) is None)
    ev2 = ND.evaluate(night({1: 0.2, 2: 0.2, 3: 0.2, 4: 2.0}, 0.2), hist(), TODAY)
    check("jedna godzina wysokiego poboru: średnia 650 W → zgłoszenie", ev2 and abs(ev2["avg_w"] - 650.0) < 1e-6, ev2)

    msg = ND.message(ev, [("Bojler", 1200.0), ("Pralka", 480.0)])
    check("komunikat: moc, norma, liczba nocy, wielokrotność, urządzenia", "600 W" in msg and "200 W" in msg and "8 nocy" in msg and "3,0× więcej" in msg and "Bojler 1,2 kW" in msg, msg)
    check("komunikat bez urządzeń: podpowiedź co sprawdzić", "Sprawdź, co zostało włączone" in ND.message(ev, []), ND.message(ev, None))


def seed(rt, today_kw, hist_kw=0.2, n=8):
    for i in range(1, n + 1):
        d = (TODAY - timedelta(days=i)).isoformat()
        for h in range(24):
            b = INS._blank_bucket(); b[INS.LOAD] = hist_kw if h in ND.NIGHT_HOURS else 0.4
            rt.insights.hours[f"{d}T{h:02d}"] = b
    for h in range(24):
        b = INS._blank_bucket(); b[INS.LOAD] = today_kw if h in ND.NIGHT_HOURS else 0.4
        rt.insights.hours[f"{TODAY.isoformat()}T{h:02d}"] = b


def notes(rt):
    return [e for e in rt.log.last(50) if e.get("kind") == "notify" and "Nocny" in str(e.get("msg", "")) or "nocny pobór" in str(e.get("msg", "")).lower()]


async def runtime_part():
    # ---------- noc z podwyższonym poborem: powiadomienie rano, raz
    hass, c, opt, rt = build()
    seed(rt, 0.6)
    hass.states.set("switch.bms_notifications_enabled", "on")
    rt.state["notify_cfg"] = N.effective({"phone_level": "all"})
    c.config["notify_service"] = "notify.mobile_app_tel"
    hass.states.set("sensor.bojler_moc", 1200, {"unit_of_measurement": "W"})
    rt.devices.set_devices([{"id": "boj", "name": "Bojler", "category": "boiler", "power_eid": "sensor.bojler_moc"}])
    await rt.monitor._night_draw(at(2026, 11, 20, 4, 30))
    check("przed 5:00 nic nie wysyła", not [c for c in hass.services.calls if c[0] == "persistent_notification"])
    await rt.monitor._night_draw(at(2026, 11, 20, 6, 0))
    pn = [c for c in hass.services.calls if c[0] == "persistent_notification" and c[1] == "create"]
    check("rano: powiadomienie o nocnym poborze", len(pn) == 1 and "nocny pobór" in pn[0][2]["title"].lower(), pn)
    check("treść z urządzeniem najwięcej biorącym", "Bojler 1,2 kW" in pn[0][2]["message"] and "600 W" in pn[0][2]["message"], pn[0][2]["message"])
    await rt.monitor._night_draw(at(2026, 11, 20, 6, 5))
    pn = [c for c in hass.services.calls if c[0] == "persistent_notification" and c[1] == "create"]
    check("drugi tick tego samego dnia: bez powtórki", len(pn) == 1, len(pn))
    check("wpis w skrzynce panelu", any(i.get("kind") == "night_draw" for i in rt.state.get("inbox", [])), rt.state.get("inbox"))

    # ---------- zwykła noc: cisza (i oznaczenie, że ocena zrobiona)
    hass, c, opt, rt = build()
    seed(rt, 0.2)
    await rt.monitor._night_draw(at(2026, 11, 20, 6, 0))
    check("zwykła noc: brak powiadomienia", not [c for c in hass.services.calls if c[0] == "persistent_notification"])
    check("zwykła noc: ocena oznaczona jako zrobiona", (rt.state.get("notify_once") or {}).get("night_draw") == TODAY.isoformat(), rt.state.get("notify_once"))

    # ---------- wyłączone w konfiguratorze
    hass, c, opt, rt = build()
    seed(rt, 0.6)
    rt.state["notify_cfg"] = N.effective({"kinds": {"night_draw": {"on": False}}})
    await rt.monitor._night_draw(at(2026, 11, 20, 6, 0))
    check("wyłączone w konfiguratorze: brak powiadomienia i brak obliczeń", not [c for c in hass.services.calls if c[0] == "persistent_notification"] and "night_draw" not in (rt.state.get("notify_once") or {}))

    # ---------- własny próg
    hass, c, opt, rt = build()
    seed(rt, 0.6, hist_kw=0.4)
    rt.state["notify_cfg"] = N.effective({"phone_level": "all"})
    await rt.monitor._night_draw(at(2026, 11, 20, 6, 0))
    check("×1,5 przy progu domyślnym 1,6 → bez powiadomienia", not [c for c in hass.services.calls if c[0] == "persistent_notification"])
    hass, c, opt, rt = build()
    seed(rt, 0.6, hist_kw=0.4)
    rt.state["notify_cfg"] = N.effective({"phone_level": "all", "kinds": {"night_draw": {"thr": 1.3}}})
    await rt.monitor._night_draw(at(2026, 11, 20, 6, 0))
    check("próg 1,3 → powiadomienie", len([c for c in hass.services.calls if c[0] == "persistent_notification"]) == 1)

    # ---------- noc z urządzeniem włączonym przez EMS (np. auto w najtańszych godzinach) — bez fałszywego alarmu
    hass, c, opt, rt = build()
    seed(rt, 0.6)
    rt.state["notify_cfg"] = N.effective({"phone_level": "all"})
    hass.states.set("switch.auto", "off")
    rt.devices.set_devices([{"id": "ev", "name": "Auto", "category": "ev", "power_eid": "sensor.auto_p", "switch_eid": "switch.auto",
                             "ctl_mode": "cheap", "ctl_power_w": 3000}])
    rt.state["dev_ctl"] = {"ev": {"on_s": 7200.0, "cmd": "off"}}
    await rt.monitor._night_draw(at(2026, 11, 20, 6, 0))
    check("auto włączone przez EMS tłumaczy pobór → brak powiadomienia", not [c for c in hass.services.calls if c[0] == "persistent_notification"])
    check("wpis informacyjny w dzienniku", any("tłumaczą go urządzenia włączone przez EMS" in str(e.get("msg", "")) for e in rt.log.last(20)), [e.get("msg") for e in rt.log.last(5)])
    rt.state["dev_ctl"] = {"ev": {"on_s": 0.0, "cmd": "off"}}
    rt.state["notify_once"] = {}
    await rt.monitor._night_draw(at(2026, 11, 20, 6, 10))
    check("auto nie pracowało, a pobór wysoki → powiadomienie", len([c for c in hass.services.calls if c[0] == "persistent_notification"]) == 1)

    # ---------- brak historii: nic, bez wyjątków
    hass, c, opt, rt = build()
    await rt.monitor._night_draw(at(2026, 11, 20, 6, 0))
    check("brak historii: brak powiadomienia i błędów", not [c for c in hass.services.calls if c[0] == "persistent_notification"])

    # ---------- katalog
    check("katalog: rodzaj night_draw, ważny, z progiem", "night_draw" in N.CATALOG and N.PRIORITY["night_draw"] == 2 and N.CATALOG["night_draw"][7][2] == 1.6)
    check("odstęp rodzaju jest na liście do wyboru", N.CATALOG["night_draw"][5] in N.COOLDOWNS)


async def main():
    pure()
    await runtime_part()


asyncio.run(main())
print(f"NIGHTDRAW PASS={common.PASS} FAIL={common.FAIL}")
