"""Passa zawyżonej prognozy PV: 3 dni z rzędu <70% → jedno ostrzeżenie dziennie."""
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
    today = base.date()
    hass, c, opt, rt = build()
    for i, (f, a) in enumerate([(10, 5), (12, 6), (9, 4)], start=1):
        rt.insights.fc[(today - timedelta(days=i)).isoformat()] = {"pv_fc": f, "pv_act": a}
    check("passa wykryta", (rt.pv_streak(today) or {}).get("days") == 3, rt.pv_streak(today))
    await rt.enforce_guard(base)
    check("ostrzeżenie w dzienniku", len(msgs(rt, "zawyżona")) == 1, msgs(rt, "zawyżona"))
    await rt.enforce_guard(base + timedelta(hours=3))
    check("tylko raz dziennie", len(msgs(rt, "zawyżona")) == 1)

    hass, c, opt, rt = build()
    for i, (f, a) in enumerate([(10, 5), (12, 11), (9, 4)], start=1):
        rt.insights.fc[(today - timedelta(days=i)).isoformat()] = {"pv_fc": f, "pv_act": a}
    check("jeden dobry dzień przerywa passę", rt.pv_streak(today) is None)
    hass, c, opt, rt = build()
    check("brak danych: brak passy", rt.pv_streak(today) is None)
    print(f"PVSTREAK PASS={common.PASS} FAIL={common.FAIL}")


asyncio.run(main())
