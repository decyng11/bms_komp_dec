"""Straż poranka: wymagane okno ładowania nocnego, które nie jest ustawione na ~2 h przed startem → powiadomienie (raz na okno)."""
import asyncio, sys
from datetime import timedelta
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import automation, notify_cfg as N
from homeassistant.util import dt as dt_util


def pp(cur, new, **kw):
    d = {"skip": False, "proposed": new, "current": cur, "confidence": "high", "reason": "x", "required": True}; d.update(kw); return d


def plan(a="19:00", b="03:00", **kw):
    return {"proposals": {"start_grid_charge": pp("01:00", a, **kw), "stop_grid_charge": pp("03:00", b, **kw)}}


def setup(auto=False):
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_start_grid_charge", "01:00:00"); S.set("time.bms_stop_grid_charge", "03:00:00")
    S.set("switch.bms_auto_apply", "on" if auto else "off"); S.set("switch.bms_ladowanie_z_sieci_1", "on")
    sent = []
    async def fake_send(kind, title, message, **kw):
        sent.append((kind, message)); return True
    rt.monitor.notifier.send = fake_send
    return hass, rt, S, sent


def T(h, m=0):
    return dt_util.now().replace(hour=h, minute=m, second=0, microsecond=0)


async def main():
    check("katalog powiadomień zawiera „Straż poranka” (włączona, na telefon, raz na 12 h)",
          "morning_guard" in N.CATALOG and N.CATALOG["morning_guard"][3] is True and N.CATALOG["morning_guard"][4] is True and N.CATALOG["morning_guard"][5] == 720 and 720 in N.COOLDOWNS)

    hass, rt, S, sent = setup()
    await automation.async_morning_guard(rt, hass, plan(), T(16, 30))
    check("2,5 h przed startem: jeszcze cicho", not sent, sent)
    await automation.async_morning_guard(rt, hass, plan(), T(17, 30))
    check("1,5 h przed startem: powiadomienie z godzinami planu i falownika", len(sent) == 1 and sent[0][0] == "morning_guard"
          and "19:00–03:00" in sent[0][1] and "01:00–03:00" in sent[0][1] and "start za 90 min" in sent[0][1], sent)
    check("bez auto-stosowania: podpowiedź, że można je włączyć", "włącz automatyczne stosowanie" in sent[0][1], sent[0][1])
    await automation.async_morning_guard(rt, hass, plan(), T(17, 40))
    check("raz na okno: brak powtórzenia", len(sent) == 1, sent)

    # okno już trwa według planu (po północy), godziny nadal nie ustawione
    hass, rt, S, sent = setup()
    await automation.async_morning_guard(rt, hass, plan(), T(22, 0))
    check("okno już trwa według planu (22:00 w 19:00–03:00): powiadomienie „okno już trwa”", len(sent) == 1 and "okno już trwa" in sent[0][1], sent)
    hass, rt, S, sent = setup()
    await automation.async_morning_guard(rt, hass, plan(), T(1, 0))
    check("po północy w trwającym oknie 19:00–03:00 (01:00): powiadomienie", len(sent) == 1, sent)
    hass, rt, S, sent = setup()
    await automation.async_morning_guard(rt, hass, plan(), T(4, 0))
    check("po końcu okna: cicho", not sent, sent)

    # godziny już zgodne z planem
    hass, rt, S, sent = setup()
    S.set("time.bms_start_grid_charge", "19:00:00"); S.set("time.bms_stop_grid_charge", "03:00:00")
    await automation.async_morning_guard(rt, hass, plan(), T(17, 30))
    check("godziny zgodne z planem: cicho", not sent, sent)

    # odrzucone w panelu = decyzja użytkownika
    hass, rt, S, sent = setup()
    from custom_components.bms_komp_dec import inbox
    rt.state["rejected_props"] = {"start_grid_charge": "19:00"}
    await automation.async_morning_guard(rt, hass, plan(), T(17, 30))
    check("odrzucona propozycja: cicho (to decyzja użytkownika)", not sent, sent)

    # nie wymagane (zarobkowe), skip, niska pewność
    for lab, kw in (("niewymagane", {"required": False}), ("pomiń", {"skip": True}), ("niska pewność", {"confidence": "low"})):
        hass, rt, S, sent = setup()
        await automation.async_morning_guard(rt, hass, plan(**kw), T(17, 30))
        check(f"{lab}: cicho", not sent, sent)

    # auto-stosowanie włączone, ale nie zadziałało — w powiadomieniu powód
    hass, rt, S, sent = setup(auto=True)
    rt.state["auto_skip"] = {"start_grid_charge": {"kind": "skip", "why": "trwa ładowanie z sieci", "prop": "19:00"}}
    await automation.async_morning_guard(rt, hass, plan(), T(17, 30))
    check("auto włączone: komunikat wskazuje, że nie zmieniło godzin, i powód", len(sent) == 1 and "nie zmieniło godzin" in sent[0][1] and "trwa ładowanie z sieci" in sent[0][1], sent)

    # zestaw 2 działa tak samo
    hass, rt, S, sent = setup()
    S.set("time.bms_start_grid_charge_2", "12:00:00"); S.set("time.bms_stop_grid_charge_2", "14:00:00")
    p2 = {"proposals": {"start_grid_charge_2": pp("12:00", "13:00"), "stop_grid_charge_2": pp("14:00", "15:00")}}
    await automation.async_morning_guard(rt, hass, p2, T(12, 30))
    check("zestaw 2: wymagane okno dzienne 13:00–15:00 też pilnowane", len(sent) == 1 and "13:00–15:00" in sent[0][1], sent)

    # brak planu / pusty plan
    hass, rt, S, sent = setup()
    await automation.async_morning_guard(rt, hass, None, T(17, 30)); await automation.async_morning_guard(rt, hass, {"proposals": {}}, T(17, 30))
    check("brak planu: bez błędu i bez powiadomienia", not sent)
    print(f"MORNING-GUARD PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
