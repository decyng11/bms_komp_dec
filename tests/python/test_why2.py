"""„Dlaczego?”: tryb awaryjny i rozjazd mają pierwszeństwo, ładowanie z sieci podaje właściwy powód."""
import asyncio, sys
from datetime import timedelta
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import planview
from homeassistant.util import dt as dt_util


async def main():
    base = dt_util.now().replace(hour=9, minute=0, second=0, microsecond=0)
    hass, c, opt, rt = build()
    await rt.run_command("wlacz_ladowanie_siec", source="ręcznie")
    w = planview.why_now(rt, base)
    check("ręczne ładowanie: powód ręczny", "ręcznie" in w["text"] and w["kind"] == "grid", w)
    rt.state.pop("gc_origin", None)
    for m in (0, 11):
        await rt.enforce_guard(base + timedelta(minutes=m))
    w = planview.why_now(rt, base + timedelta(minutes=11))
    check("rozjazd: ostrzeżenie zamiast „tani prąd”", "poza planem" in w["text"], w)
    rt.soc = lambda: None
    for m in (20, 40):
        await rt.enforce_guard(base + timedelta(minutes=m))
    w = planview.why_now(rt, base + timedelta(minutes=40))
    check("tryb awaryjny ma pierwszeństwo", "awaryjny" in w["text"].lower(), w)
    print(f"WHY PASS={common.PASS} FAIL={common.FAIL}")


asyncio.run(main())
