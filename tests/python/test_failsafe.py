"""Tryb awaryjny: brak SOC dłużej niż 15 min → STOP tego, co zlecił EMS + zgłoszenie; powrót danych kończy tryb."""
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
    hass, c, opt, rt = build(); S = hass.states
    await rt.run_command("wlacz_ladowanie_siec", source="ręcznie")
    check("warunek testu: ładowanie z sieci trwa", rt.grid_charging_on())
    rt.soc = lambda: None                                  # brak odczytu SOC
    await rt.enforce_guard(base)
    await rt.enforce_guard(base + timedelta(minutes=10))
    check("przed progiem: bez trybu awaryjnego", not msgs(rt, "Tryb awaryjny"))
    check("przed progiem: ładowanie trwa", rt.grid_charging_on())
    await rt.enforce_guard(base + timedelta(minutes=16))
    check("po progu: wpis trybu awaryjnego", len(msgs(rt, "Tryb awaryjny")) == 1, msgs(rt, "Tryb"))
    check("po progu: zleconym ładowaniem zatrzymane", not rt.grid_charging_on())
    await rt.enforce_guard(base + timedelta(minutes=30))
    check("tryb awaryjny zgłaszany raz", len(msgs(rt, "Tryb awaryjny")) == 1)
    rt.soc = lambda: 50.0                                  # dane wróciły
    await rt.enforce_guard(base + timedelta(minutes=35))
    check("powrót danych: wpis w dzienniku", len(msgs(rt, "tryb awaryjny zakończony")) == 1, msgs(rt, "awaryjny"))

    # krótka przerwa < 15 min → nic
    hass, c, opt, rt = build()
    rt.soc = lambda: None
    await rt.enforce_guard(base); await rt.enforce_guard(base + timedelta(minutes=8))
    rt.soc = lambda: 60.0
    await rt.enforce_guard(base + timedelta(minutes=9))
    check("krótka przerwa: bez wpisów", not msgs(rt, "awaryjny"))
    print(f"FAILSAFE PASS={common.PASS} FAIL={common.FAIL}")


asyncio.run(main())
