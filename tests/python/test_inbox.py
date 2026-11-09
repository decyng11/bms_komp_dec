"""Skrzynka powiadomień panelu (dzwonek) i pamięć odrzuconych propozycji."""
import sys
from common import *   # noqa
import common
from custom_components.bms_komp_dec import inbox as IB

st = {}
e1 = IB.add(st, "low_soc", "Niski SOC", "SOC 12%", "warn", ts=1_000_000)
e2 = IB.add(st, "summary_daily", "Podsumowanie dnia", "Zysk 3 zł", "info", ts=1_000_100)
check("wpis ma id, grupę i flagę read", e1["id"] == 1 and e1["group"] == "Bateria" and e1["read"] is False, e1)
check("rodzaj spoza katalogu → grupa Inne", IB.add(st, "xyz", "t", "m", ts=1_000_200)["group"] == "Inne")
check("propozycja nie trafia do skrzynki", IB.add(st, "proposal", "t", "m") is None and len(st["inbox"]) == 3)
check("nieznany poziom → info", IB.add(st, "alarm", "t", "m", "dziwny", ts=1_000_300)["level"] == "info")
check("nieprzeczytane = 4", IB.unread(st) == 4)
IB.act(st, "read", ident=1)
check("read oznacza jeden wpis", IB.unread(st) == 3 and st["inbox"][0]["read"])
check("read nieistniejącego nic nie zmienia", IB.act(st, "read", ident=999)["changed"] == 0)
check("read_all", IB.act(st, "read_all")["changed"] == 3 and IB.unread(st) == 0)
check("delete usuwa wpis", IB.act(st, "delete", ident=2)["changed"] == 1 and all(e["id"] != 2 for e in st["inbox"]))
# limit liczby i wieku
s2 = {}
for i in range(80):
    IB.add(s2, "alarm", f"t{i}", "m", ts=2_000_000 + i)
check("limit 60 wpisów, zostają najnowsze", len(s2["inbox"]) == IB.INBOX_MAX and s2["inbox"][-1]["title"] == "t79", len(s2["inbox"]))
IB.add(s2, "alarm", "nowy", "m", ts=2_000_000 + 20 * 86400)
check("wpisy starsze niż 14 dni znikają", [e["title"] for e in s2["inbox"]] == ["nowy"], len(s2["inbox"]))
check("id rośnie monotonicznie mimo przycinania", s2["inbox"][0]["id"] == 81)
IB.act(s2, "clear")
check("clear", s2["inbox"] == [])
# odrzucanie
s3 = {}
check("brak odrzucenia domyślnie", not IB.is_rejected(s3, "bateria_sprzedaz_start", "17:00"))
IB.act(s3, "reject", key="bateria_sprzedaz_start", proposed="17:00")
check("odrzucona wartość jest ukryta", IB.is_rejected(s3, "bateria_sprzedaz_start", "17:00"))
check("inna propozycja tego samego klucza wraca", not IB.is_rejected(s3, "bateria_sprzedaz_start", "18:00"))
check("inny klucz nie jest dotknięty", not IB.is_rejected(s3, "bateria_sprzedaz_stop", "17:00"))
check("unreject", IB.act(s3, "unreject", key="bateria_sprzedaz_start")["changed"] == 1 and not IB.is_rejected(s3, "bateria_sprzedaz_start", "17:00"))
for bad in (dict(action="nic"), dict(action="reject", key="x")):
    try:
        IB.act(s3, bad.pop("action"), **bad); ok = False
    except ValueError:
        ok = True
    check(f"błędne wywołanie odrzucone {bad}", ok)

# Notifier.send zapisuje do skrzynki, także gdy telefon/persistent wyłączone
import asyncio
from custom_components.bms_komp_dec import monitor as M
class _Log:
    def add(self, *a, **k): pass
class _RT:
    def __init__(self):
        self.state = {}; self.cfg = {}; self.log = _Log(); self.hass = stubs.FakeHass()
    def _save_state(self): pass
rt = _RT()
n = M.Notifier(rt)
sent = asyncio.run(n.send("alarm", "🚨 Alarm", "F23", key="a1", level="error"))
check("send → wpis w skrzynce", len(rt.state.get("inbox", [])) == 1 and rt.state["inbox"][0]["level"] == "error", rt.state.get("inbox"))
asyncio.run(n.send("proposal", "🤖 propozycja", "x", key="p"))
check("send(proposal) nie dubluje w skrzynce", len(rt.state["inbox"]) == 1)

# prune_rejected: odrzucenie wygasa, gdy plan przestaje proponować tę godzinę
s4 = {}
IB.act(s4, "reject", key="a", proposed="23:00"); IB.act(s4, "reject", key="b", proposed="05:00"); IB.act(s4, "reject", key="c", proposed="07:00")
IB.act(s4, "reject", key="d", proposed="08:00")
n = IB.prune_rejected(s4, {"a": {"proposed": "23:00", "skip": False}, "b": {"proposed": "05:30", "skip": False},
                           "c": {"proposed": "07:00", "skip": True}})
check("prune: zostaje tylko wciąż proponowana odrzucona godzina", list(s4["rejected_props"]) == ["a"] and n == 3, s4["rejected_props"])
check("prune: po wygaśnięciu ta sama godzina znów jest do decyzji", not IB.is_rejected(s4, "b", "05:00"))

# nazwa okna ładowania przy ~0 kWh nie mówi „Doładuj ~0.0 kWh”
from custom_components.bms_komp_dec.scheduler import ScheduleOptimizer as SO
check("okno bez energii: opis nie obiecuje doładowania", "Doładuj" not in SO._charge_phrase(0.0) and "0.0 kWh" in SO._charge_phrase(0.0))
check("okno z energią: „Doładuj ~2.5 kWh z sieci”", SO._charge_phrase(2.5) == "Doładuj ~2.5 kWh z sieci")

print(f"INBOX PASS={common.PASS} FAIL={common.FAIL}")
sys.exit(1 if common.FAIL else 0)
