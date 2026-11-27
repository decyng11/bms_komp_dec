"""Poziom powiadomień „na telefon” (wszystkie / ważne / krytyczne) i autoodczyt skrzynki panelu (dzwonka):
informacje czytają się same, powtórki zastępują starsze, ostrzeżenia i błędy zostają nieprzeczytane — nic nie ginie."""
import asyncio, sys
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import notify_cfg as N, inbox as I
from homeassistant.util import dt as dt_util


def push(h): return [c for c in h.services.calls if c[0] == "notify"]
def pn(h, nid=None): return [c for c in h.services.calls if c[0] == "persistent_notification" and c[1] == "create" and (nid is None or c[2].get("notification_id") == nid)]
def dis(h): return [c for c in h.services.calls if c[0] == "persistent_notification" and c[1] == "dismiss"]
def clear(h): h.services.calls.clear()
def env(level=None, auto_read=None, kinds=None):
    hass, c, opt, rt = build()
    c.config["notify_service"] = "notify.mobile_app_tel"
    hass.states.set("switch.bms_notifications_enabled", "on")
    raw = {"kinds": kinds or {}}
    if level is not None: raw["phone_level"] = level
    if auto_read is not None: raw["auto_read"] = auto_read
    rt.state["notify_cfg"] = N.effective(raw)
    return hass, c, opt, rt
def inb(rt): return list(rt.state.get("inbox") or [])
def unread_kinds(rt): return sorted(e["kind"] for e in inb(rt) if not e.get("read"))


async def main():
    # ---------------------------------------------------------------- ustawienia i klasyfikacja
    e = N.effective(None)
    check("domyślnie: poziom „ważne”, autoodczyt włączony", e["phone_level"] == "important" and e["auto_read"] is True, (e["phone_level"], e["auto_read"]))
    e = N.effective({"phone_level": "critical", "auto_read": False})
    check("poprawne wartości przyjęte", e["phone_level"] == "critical" and e["auto_read"] is False)
    e = N.effective({"phone_level": "wszystko!", "auto_read": "tak"})
    check("śmieci → domyślne", e["phone_level"] == "important" and e["auto_read"] is True, e)
    check("każdy rodzaj z katalogu ma przypisaną ważność (nic bez klasyfikacji)", set(N.CATALOG) <= set(N.PRIORITY), sorted(set(N.CATALOG) - set(N.PRIORITY)))
    check("klasyfikacja nie zawiera nieistniejących rodzajów", set(N.PRIORITY) <= set(N.CATALOG), sorted(set(N.PRIORITY) - set(N.CATALOG)))
    check("ważność tylko 1–3", set(N.PRIORITY.values()) <= {1, 2, 3})
    crit = {"low_soc", "alarm", "comm_loss", "grid_outage", "island_overload", "battery_temp_high", "battery_temp_low", "command_unconfirmed",
            "drift", "guard_action", "grid_limit", "grid_charge_stalled", "plan_floor", "set_off", "morning_guard", "grid_charge_target"}
    check("krytyczne: bateria, falownik, zabezpieczenia, plan zagrożony, straż poranka", all(N.priority(k) == 1 for k in crit), [k for k in crit if N.priority(k) != 1])
    check("podsumowania i brak danych to „ważne”, nie „info”", all(N.priority(k) == 2 for k in ("summary_daily", "summary_weekly", "summary_monthly", "rce_missing", "pv_forecast_missing", "auto_apply")))
    check("nieznany rodzaj = „ważny” (nie gubimy)", N.priority("cos_nowego") == 2)
    a, i_, c_ = N.effective({"phone_level": "all"}), N.effective({"phone_level": "important"}), N.effective({"phone_level": "critical"})
    check("poziom „wszystkie”: przechodzi także info", N.phone_allows(a, "device_cycle") and N.phone_allows(a, "low_soc"))
    check("poziom „ważne”: bez info, z ważnymi i krytycznymi", not N.phone_allows(i_, "device_cycle") and N.phone_allows(i_, "summary_daily") and N.phone_allows(i_, "low_soc"))
    check("poziom „krytyczne”: tylko krytyczne", not N.phone_allows(c_, "summary_daily") and not N.phone_allows(c_, "device_cycle") and N.phone_allows(c_, "alarm"))
    check("katalog dla karty niesie ważność", all(x.get("prio") in (1, 2, 3) for x in N.catalog_payload()))

    # ---------------------------------------------------------------- wysyłka wg poziomu
    hass, c, opt, rt = env("important"); n = rt.monitor.notifier
    r = await n.send("device_cycle", "🧺 Koniec cyklu", "Pralka skończyła", level="info")
    check("ważne: informacja NIE idzie na telefon ani do powiadomień HA", r is True and not push(hass) and not pn(hass), hass.services.calls)
    check("ważne: informacja jest w skrzynce panelu (nieprzeczytana) — nic nie ginie", unread_kinds(rt) == ["device_cycle"], inb(rt))
    r = await n.send("summary_daily", "📊 Podsumowanie dnia", "Bilans +3,20 zł", level="info")
    check("ważne: podsumowanie dnia idzie na telefon", len(push(hass)) == 1 and len(pn(hass)) == 1, hass.services.calls)
    r = await n.send("low_soc", "🔋 niski SOC", "Bateria 12%", level="warn")
    check("ważne: krytyczne (niski SOC) idzie na telefon", len(push(hass)) == 2)
    check("ważne: wszystkie trzy w skrzynce", unread_kinds(rt) == ["device_cycle", "low_soc", "summary_daily"], unread_kinds(rt))

    hass, c, opt, rt = env("critical"); n = rt.monitor.notifier
    await n.send("summary_daily", "📊 Podsumowanie dnia", "Bilans", level="info")
    await n.send("rce_negative", "📉 ujemne ceny", "jutro", level="info")
    check("krytyczne: ważne nie idzie na telefon, jest w skrzynce", not push(hass) and unread_kinds(rt) == ["rce_negative", "summary_daily"], (hass.services.calls, unread_kinds(rt)))
    await n.send("alarm", "⚠ alarm", "F13", key="alarm:1", level="error")
    check("krytyczne: alarm idzie na telefon", len(push(hass)) == 1)

    hass, c, opt, rt = env("all"); n = rt.monitor.notifier
    await n.send("device_cycle", "🧺 Koniec cyklu", "Pralka skończyła", level="info")
    check("wszystkie: informacja idzie na telefon (jak dotąd)", len(push(hass)) == 1 and len(pn(hass)) == 1)

    hass, c, opt, rt = env("critical"); n = rt.monitor.notifier
    await n.send("test", "✅ testowe", "działa", key="t1", level="info", force=True)
    check("wiadomość testowa (force) omija poziom", len(push(hass)) == 1)

    hass, c, opt, rt = env("important", kinds={"low_soc": {"phone": False}}); n = rt.monitor.notifier
    await n.send("low_soc", "🔋 niski SOC", "Bateria 12%", level="warn")
    check("„tylko HA” przy rodzaju nadal działa: krytyczne bez telefonu, ale z powiadomieniem HA", not push(hass) and len(pn(hass)) == 1, hass.services.calls)

    hass, c, opt, rt = env("important"); n = rt.monitor.notifier
    hass.states.set("switch.bms_notifications_enabled", "off")
    r = await n.send("low_soc", "🔋 niski SOC", "Bateria 12%", level="warn")
    check("główny wyłącznik wyłączony: bez telefonu (skrzynka dalej zapisuje)", r is False and not push(hass) and unread_kinds(rt) == ["low_soc"])

    hass, c, opt, rt = env("important", kinds={"device_cycle": {"on": False}}); n = rt.monitor.notifier
    r = await n.send("device_cycle", "🧺 Koniec cyklu", "x", level="info")
    check("rodzaj wyłączony w konfiguratorze: nic (jak dotąd)", r is False and not inb(rt))

    # ---------------------------------------------------------------- krótka wersja na telefon
    from custom_components.bms_komp_dec import monitor as MM
    hass, c, opt, rt = env("all"); n = rt.monitor.notifier
    full = "Bilans +3,18 zł\nPV 8,2 kWh\nDom 11,4 kWh"
    await n.send("summary_daily", "📅 podsumowanie", full, level="info", short="Bilans +3,18 zł · PV 8,2 kWh · Dom 11,4 kWh")
    check("short: telefon dostaje jedną linię + wskazówkę", push(hass) and push(hass)[0][2]["message"] == "Bilans +3,18 zł · PV 8,2 kWh · Dom 11,4 kWh\nSzczegóły: panel → dzwonek", push(hass))
    check("short: powiadomienie HA też krótkie", pn(hass) and pn(hass)[0][2]["message"].startswith("Bilans +3,18 zł · PV"), pn(hass))
    check("short: skrzynka panelu ma pełną treść", inb(rt)[0]["message"] == full, inb(rt))
    clear(hass)
    hass, c, opt, rt = env("all"); n = rt.monitor.notifier
    await n.send("device_cycle", "🧺 Koniec cyklu", "Pralka skończyła", level="info")
    check("bez short: telefon dostaje pełną treść", push(hass)[0][2]["message"] == "Pralka skończyła", push(hass))
    check("short_of: krótkie zostaje, długie → pierwsze zdanie, wielolinijkowe → pierwsza linia",
          MM.short_of("Krótko.") is None and MM.short_of("a\nb") == "a"
          and MM.short_of("Nocny pobór wyższy niż zwykle o 0,4 kW. " + "Powód. " * 30) == "Nocny pobór wyższy niż zwykle o 0,4 kW.")
    hass, c, opt, rt = env("all")
    check("_summary_short bez danych → None (idzie pełna treść)", rt.monitor._summary_short("day", __import__("datetime").date(2026, 11, 7)) is None)

    # ---------------------------------------------------------------- powtórki zastępują starsze
    hass, c, opt, rt = env("all", kinds={"low_soc": {"cooldown": 0}}); n = rt.monitor.notifier
    await n.send("low_soc", "🔋 niski SOC", "Bateria 12% (próg 10%)", key="a", level="warn")
    await n.send("low_soc", "🔋 niski SOC", "Bateria 9% (próg 10%)", key="b", level="warn")
    es = inb(rt)
    check("powtórka (inne liczby): zlewa się w jeden nieprzeczytany wpis z licznikiem", len(es) == 1 and es[0]["n"] == 2 and not es[0]["read"] and "9%" in es[0]["message"], es)
    await n.send("low_soc", "🔋 niski SOC", "Bateria 8% (próg 10%)", key="c", level="warn")
    check("po trzeciej: nadal jeden wpis, licznik 3", [(e["read"], e["n"]) for e in inb(rt)] == [(False, 3)])
    hass, c, opt, rt = env("all", auto_read=False, kinds={"low_soc": {"cooldown": 0}}); n = rt.monitor.notifier
    await n.send("low_soc", "🔋 niski SOC", "Bateria 12%", key="a", level="warn")
    await n.send("low_soc", "🔋 niski SOC", "Bateria 9%", key="b", level="warn")
    check("autoodczyt wyłączony: jeden nieprzeczytany wpis z licznikiem", [(e["read"], e["n"]) for e in inb(rt)] == [(False, 2)])
    hass, c, opt, rt = env("all", kinds={"alarm": {"cooldown": 0}, "drift": {"cooldown": 0}}); n = rt.monitor.notifier
    await n.send("alarm", "⚠ alarm", "F13 przepięcie", key="a", level="error")
    await n.send("alarm", "⚠ alarm", "F13 przepięcie", key="b", level="error")
    check("błędy też się zlewają, ale zostają nieprzeczytane", [(e["read"], e["n"]) for e in inb(rt)] == [(False, 2)])
    await n.send("drift", "Zmiana po zapisie", "parametr work_mode zmienił wartość", key="a", level="warn")
    await n.send("drift", "Zmiana po zapisie", "parametr charge_current zmienił wartość", key="b", level="warn")
    check("inna treść (inny parametr) nie jest powtórką", [e["read"] for e in inb(rt) if e["kind"] == "drift"] == [False, False])

    # ---------------------------------------------------------------- autoodczyt informacji po czasie
    st = {}
    t = 1_800_000_000
    I.add(st, "device_cycle", "info stara", "x", "info", ts=t - 7 * 3600)
    I.add(st, "summary_daily", "ok stare", "y", "ok", ts=t - 10 * 3600)
    I.add(st, "device_hint", "info świeża", "z", "info", ts=t - 3600)
    I.add(st, "low_soc", "ostrzeżenie stare", "w", "warn", ts=t - 30 * 3600)
    I.add(st, "alarm", "błąd stary", "e", "error", ts=t - 40 * 3600)
    gone = I.auto_read(st, now=t)
    rd = {e["kind"]: e["read"] for e in st["inbox"]}
    check("po 6 h: stare info/ok przeczytane, świeże info nie", rd["device_cycle"] and rd["summary_daily"] and not rd["device_hint"], rd)
    check("ostrzeżenie czyta się samo po 24 h, błąd dopiero po 72 h", rd["low_soc"] and not rd["alarm"], rd)
    check("zwraca rodzaje bez nieprzeczytanych wpisów (do zdjęcia z HA)", gone == ["device_cycle", "low_soc", "summary_daily"], gone)
    I.add(st, "device_cycle", "info nowa", "n", "info", ts=t - 60)
    st["inbox"][0]["read"] = False
    gone = I.auto_read(st, now=t)
    check("rodzaj z nowszym nieprzeczytanym wpisem nie jest zwracany", "device_cycle" not in gone, gone)
    check("znacznik powodu odczytu", [e.get("auto") for e in st["inbox"] if e["kind"] == "summary_daily"] == ["po 6 h"])
    check("liczba nieprzeczytanych = tylko to, co wymaga uwagi", I.unread(st) == 3, I.unread(st))

    # tick monitora: zdejmuje powiadomienia HA, zapisuje stan, szanuje wyłącznik
    hass, c, opt, rt = env("all"); n = rt.monitor.notifier
    now = dt_util.now(); ts = now.timestamp()
    I.add(rt.state, "device_cycle", "Koniec cyklu", "Pralka", "info", ts=ts - 8 * 3600)
    I.add(rt.state, "low_soc", "niski SOC", "12%", "warn", ts=ts - 8 * 3600)
    await rt.monitor._inbox_auto_read(now)
    check("tick: info przeczytane, ostrzeżenie nie", unread_kinds(rt) == ["low_soc"], unread_kinds(rt))
    check("tick: powiadomienie HA dla odczytanego info zdjęte, dla ostrzeżenia nie", [c[2]["notification_id"] for c in dis(hass)] == ["bms_device_cycle"], dis(hass))
    clear(hass)
    await rt.monitor._inbox_auto_read(now)
    check("tick: drugi przebieg nic nie robi", not dis(hass))
    hass, c, opt, rt = env("all", auto_read=False)
    I.add(rt.state, "device_cycle", "Koniec cyklu", "Pralka", "info", ts=ts - 8 * 3600)
    await rt.monitor._inbox_auto_read(now)
    check("autoodczyt wyłączony: tick nic nie czyta", unread_kinds(rt) == ["device_cycle"] and not dis(hass))

    # ---------------------------------------------------------------- koniec sytuacji (dismiss)
    hass, c, opt, rt = env("all", kinds={"low_soc": {"cooldown": 0}, "alarm": {"cooldown": 0}}); n = rt.monitor.notifier
    await n.send("low_soc", "🔋 niski SOC", "Bateria 9%", key="a", level="warn")
    await n.send("alarm", "⚠ alarm", "F13", key="a", level="error")
    await n.send("rce_missing", "Brak cen", "brak", key="c", level="warn")
    await n.dismiss("low_soc"); await n.dismiss("alarm")
    rd = {e["kind"]: e["read"] for e in inb(rt)}
    check("koniec sytuacji: ostrzeżenie przeczytane, błąd nadal nieprzeczytany, inny rodzaj nietknięty", rd == {"low_soc": True, "alarm": False, "rce_missing": False}, rd)
    check("koniec sytuacji: znacznik powodu", [e.get("auto") for e in inb(rt) if e["kind"] == "low_soc"] == ["sytuacja minęła"])
    hass, c, opt, rt = env("all", auto_read=False, kinds={"low_soc": {"cooldown": 0}}); n = rt.monitor.notifier
    await n.send("low_soc", "🔋 niski SOC", "Bateria 9%", key="a", level="warn")
    await n.dismiss("low_soc")
    check("autoodczyt wyłączony: koniec sytuacji nie czyta wpisów", unread_kinds(rt) == ["low_soc"])

    # ---------------------------------------------------------------- akcja „obejrzane” z karty
    st = {}
    I.add(st, "device_cycle", "a", "x", "info"); I.add(st, "summary_daily", "b", "y", "ok")
    I.add(st, "low_soc", "c", "z", "warn"); I.add(st, "alarm", "d", "w", "error")
    r = I.act(st, "read_info")
    check("read_info: czyta tylko info/ok", r["changed"] == 2 and [e["read"] for e in st["inbox"]] == [True, True, False, False], st["inbox"])
    check("read_info: znacznik „obejrzane”", st["inbox"][0].get("auto") == "obejrzane")
    check("read_info: ponownie nic nie zmienia", I.act(st, "read_info")["changed"] == 0)
    check("read_info jest na liście akcji", "read_info" in I.ACTIONS)
    print(f"NOTIFY-LEVELS PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
