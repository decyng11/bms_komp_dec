"""Samokontrola po starcie: jednorazowe podsumowanie zgodności stanu falownika ze znacznikami EMS."""
import asyncio, sys
from datetime import timedelta
import common
sys.path.insert(0, ".")
from common import *   # noqa
from homeassistant.util import dt as dt_util


def msgs(rt, text):
    ents = list(rt.log.entries.values()) if isinstance(rt.log.entries, dict) else list(rt.log.entries)
    return [e["msg"] for e in ents if text in e.get("msg", "")]


async def main():
    base = dt_util.now().replace(hour=9, minute=0, second=0, microsecond=0)
    # wszystko zgodne
    hass, c, opt, rt = build()
    await rt.enforce_guard(base); await rt.enforce_guard(base + timedelta(minutes=2))
    check("przed upływem czasu: bez wpisu", not msgs(rt, "Samokontrola"))
    await rt.enforce_guard(base + timedelta(minutes=4))
    check("po czasie: stan zgodny", len(msgs(rt, "stan falownika zgodny")) == 1, msgs(rt, "Samokontrola"))
    await rt.enforce_guard(base + timedelta(minutes=10))
    check("samokontrola tylko raz", len(msgs(rt, "Samokontrola")) == 1)

    # nieaktualne znaczniki
    hass, c, opt, rt = build()
    rt.state["gc_origin"] = {"src": "ręcznie", "ts": base.timestamp()}
    rt.state["sale_sched"] = {"start_key": "bateria_sprzedaz_start", "ts": base.timestamp()}
    await rt.enforce_guard(base); await rt.enforce_guard(base + timedelta(minutes=4))
    m = msgs(rt, "Samokontrola")
    check("nieaktualne znaczniki zgłoszone", len(m) == 1 and "nieaktualny" in m[0], m)
    check("nieaktualne znaczniki wyczyszczone", not rt.state.get("gc_origin") and not rt.state.get("sale_sched"))

    # ładowanie bez właściciela
    hass, c, opt, rt = build()
    await rt.run_command("wlacz_ladowanie_siec", source="ręcznie"); rt.state.pop("gc_origin", None)
    await rt.enforce_guard(base); await rt.enforce_guard(base + timedelta(minutes=4))
    m = msgs(rt, "Samokontrola")
    check("ładowanie bez właściciela zgłoszone", len(m) == 1 and "bez zlecenia" in m[0], m)
    print(f"STARTUP PASS={common.PASS} FAIL={common.FAIL}")


asyncio.run(main())
