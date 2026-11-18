"""Raport diagnostyczny „do zgłoszenia” (usługa diagnostic_report): zawartość, zamazywanie danych wrażliwych, odporność na błędy."""
import asyncio, sys, json
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import diagnostics as DG, const as C


async def main():
    hass, c, opt, rt = build(); S = hass.states
    sched = scheduler.ScheduleOptimizer(hass, c, dict(const.SCHEDULER_DEFAULTS))
    rt.optimizer = sched; c.runtime = rt
    at(2026, 11, 18, 12, 0)
    S.set("switch.bms_auto_apply", "on"); S.set("number.bms_auto_apply_max_shift_h", "4"); S.set("switch.other_lamp", "on")
    rt.cfg["host"] = "192.168.77.12"; rt.cfg["serial"] = 2798765432; rt.cfg["notify_service"] = "notify.mobile_app_jan"
    rt.cfg["diag_password"] = "SEKRET-HASLO-123"; rt.cfg["battery_capacity_kwh"] = 15
    rt.state["auto_skip"] = {"start_grid_charge": {"kind": "skip", "why": "przesunięcie o 6.0 h przekracza limit 4 h", "prop": "19:00"}}
    rt.state["auto_hist"] = [{"at": "2026-11-18T16:00:00", "src": "daily", "why": {"start_grid_charge": "limit"}}]
    rt.log.add("plan", "Połączono z 192.168.77.12 jako jan@example.com, wysłano przez notify.mobile_app_jan, SN 2798765432, brama 10.1.2.3, inna usługa notify.telegram_x", "info")
    rt.log.add("auto", "zwykły wpis dziennika", "warn")
    rt._plan = {"generated_at": "2026-11-18T12:00:00", "mode": "ok", "error": None,
                "proposals": {"start_grid_charge": {"current": "01:00", "proposed": "19:00", "skip": False, "required": True, "confidence": "high", "reason": "noc", "tajne": "x"}}}

    out = await DG.async_build_report(rt)
    txt = out["text"]
    check("raport: struktura odpowiedzi (tekst, nazwa pliku, podsumowanie)", set(out) == {"text", "filename", "summary"} and out["filename"].startswith("ems-raport-") and out["filename"].endswith(".txt"), list(out))
    check("raport: wersja integracji i nagłówek", f"EMS komp-dec {C.VERSION}" in txt and "raport diagnostyczny" in txt)
    check("raport: sekcje plan / auto-stosowanie / ustawienia / konfiguracja / dziennik",
          all(h in txt for h in ("== Plan i propozycje", "== Auto-stosowanie", "== Ustawienia", "== Konfiguracja", "== Dziennik decyzji")), txt[:300])
    check("raport: powód odmowy auto-stosowania i historia są w raporcie", "przekracza limit 4 h" in txt and '"src": "daily"' in txt)
    check("raport: propozycja z flagą required, bez zbędnych pól", '"required": true' in txt and "tajne" not in txt)
    check("raport: ustawienia EMS (tylko encje bms_*)", "switch.bms_auto_apply" in txt and "number.bms_auto_apply_max_shift_h" in txt and "other_lamp" not in txt)
    check("raport: zwykłe ustawienia widoczne", '"battery_capacity_kwh": 15' in txt)
    check("raport: autotest dołączony (grupy z kontrolami)", "Autotest:" in txt and "Auto-stosowanie" in txt)
    check("raport: wpisy dziennika (najnowsze pierwsze)", "zwykły wpis dziennika" in txt and txt.index("zwykły wpis dziennika") < txt.index("Połączono z"))

    # ---------- zamazywanie
    check("zamazane: adres IP falownika", "192.168.77.12" not in txt)
    check("zamazane: numer seryjny", "2798765432" not in txt)
    check("zamazane: usługa powiadomień", "mobile_app_jan" not in txt)
    check("zamazane: e-mail", "jan@example.com" not in txt)
    check("zamazane: hasło diagnostyki NIGDY nie trafia do raportu", "SEKRET-HASLO-123" not in txt and "diag_password" in txt and "**REDACTED**" in txt)
    check("zamazane: obcy adres IP i obca usługa notify (spoza konfiguracji) też", "10.1.2.3" not in txt and "telegram_x" not in txt and "brama x.x.x.x" in txt and "notify.***" in txt)
    check("zamazanie nie psuje reszty wpisu dziennika", "Połączono z *** jako ***@***" in txt and "SN ***" in txt)

    # ---------- odporność
    rt.log.entries.clear()
    out2 = await DG.async_build_report(rt, log_lines=5)
    check("raport: pusty dziennik — bez błędu", "== Dziennik decyzji (ostatnie 0" in out2["text"])
    for i in range(30):
        rt.log.add("plan", f"wpis {i}", "info")
    out3 = await DG.async_build_report(rt, log_lines=7)
    check("raport: limit liczby wierszy dziennika", out3["summary"]["log_lines"] == 7 and "wpis 29" in out3["text"] and "wpis 10" not in out3["text"], out3["summary"])
    rt._plan = None
    out4 = await DG.async_build_report(rt)
    check("raport: brak planu — bez błędu", "== Plan i propozycje" in out4["text"] and out4["summary"]["errors"] >= 0)

    async def boom(_rt):
        raise RuntimeError("awaria autotestu")
    import custom_components.bms_komp_dec.selftest as ST
    old = ST.run; ST.run = boom
    try:
        out5 = await DG.async_build_report(rt)
    finally:
        ST.run = old
    check("raport: awaria autotestu nie przerywa raportu", "== Dziennik decyzji" in out5["text"] and "== Konfiguracja" in out5["text"])
    check("raport: wynik da się wysłać jako JSON", bool(json.dumps(out, ensure_ascii=False)))

    # scrub_text samodzielnie
    s = DG.scrub_text("host 10.0.0.5 mail a.b@c.pl notify.tel SN ABC12345 oraz 3.14 i 1.2.3", ["ABC12345", "", None])
    check("scrub_text: IP, e-mail, notify, wartości z konfiguracji; liczby i wersje bez zmian", s == "host x.x.x.x mail ***@*** notify.*** SN *** oraz 3.14 i 1.2.3", s)
    print(f"REPORT PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
