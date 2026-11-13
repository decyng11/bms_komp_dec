"""Prognoza PV: suma dnia z prognozy środkowej (nie ze stanu encji), wykrycie wariantu encji, porównanie źródeł, zerowanie nauki."""
import asyncio, sys
from datetime import timedelta
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import pv_forecast as pvf
from custom_components.bms_komp_dec.button import BmsResetPvLearningButton
from homeassistant.util import dt as dt_util


def attrs(d, hours=range(24)):
    mid = lambda h: 0.6 if 9 <= h < 15 else 0.0          # 3,6 kWh
    return {"detailedHourly": [{"period_start": f"{d.isoformat()}T{h:02d}:00:00+01:00", "pv_estimate": mid(h),
                                "pv_estimate10": mid(h) * 0.4, "pv_estimate90": mid(h) * 1.5} for h in hours]}


async def main():
    hass, c, opt, rt = build(); S = hass.states
    d = dt_util.now().date(); eid = "sensor.solcast_pv_forecast_forecast_today"
    fc = pvf.PvForecast(hass)
    S.set(eid, 1.44, attrs(d))                                    # encja ustawiona na estimate10 (3,6 × 0,4)
    check("suma dnia = prognoza środkowa z danych godzinowych, nie stan encji", abs(fc.daily_kwh(eid, d) - 3.6) < 0.01, fc.daily_kwh(eid, d))
    check("wykryty wariant encji: estimate10", pvf.solcast_variant(hass, eid, d) == "estimate10", pvf.solcast_variant(hass, eid, d))
    S.set(eid, 5.4, attrs(d))
    check("wykryty wariant encji: estimate90", pvf.solcast_variant(hass, eid, d) == "estimate90")
    S.set(eid, 3.6, attrs(d))
    check("encja środkowa: bez ostrzeżenia", pvf.solcast_variant(hass, eid, d) is None)
    S.set(eid, 2.9, attrs(d, range(12, 24)))                      # niepełna doba danych godzinowych → stan encji
    check("niepełne dane godzinowe: bierzemy stan encji", abs(fc.daily_kwh(eid, d) - 2.9) < 0.01, fc.daily_kwh(eid, d))
    S.set(eid, 2.9, {})
    check("brak danych godzinowych: stan encji", abs(fc.daily_kwh(eid, d) - 2.9) < 0.01)
    S.set(eid, 1.44, attrs(d))
    pay = fc.card_payload(eid, "sensor.solcast_pv_forecast_forecast_tomorrow")
    check("karta: dziś 3,6 kWh i zakres 1,44–5,4", pay["pv_daily"][0]["kwh"] == 3.6 and pay["pv_daily"][0]["lo"] == 1.44 and pay["pv_daily"][0]["hi"] == 5.4, pay["pv_daily"][0])
    check("karta: ostrzeżenie o wariancie i porównanie źródeł", pay["pv_entity_variant"] == "estimate10" and pay["pv_sources"][0] == {"name": "Solcast", "today": 3.6, "tomorrow": None}, (pay["pv_entity_variant"], pay["pv_sources"]))

    # zerowanie nauki korekty
    ins = rt.insights
    for i in range(1, 9):
        ins.fc[(d - timedelta(days=i)).isoformat()] = {"pv_fc": 2.0, "pv_act": 5.0, "pv_fc_by_h": {"0": 2.0}, "pv_adj_by_h": {"0": 2.4}, "pv_fc_h": [0.1] * 24}
    f0 = ins.pv_horizon_factor(0, d)
    check("warunek testu: korekta nauczona na zaniżonej prognozie (×1,4)", f0[0] == 1.4 and f0[1] == 8, f0)
    btn = BmsResetPvLearningButton(c)
    await btn.async_press()
    f1 = ins.pv_horizon_factor(0, d)
    check("po wyzerowaniu: korekta ×1, 0 dni", f1[0] == 1.0 and f1[1] == 0, f1)
    rec = ins.fc[(d - timedelta(days=1)).isoformat()]
    check("wykonanie i kształt godzinowy zostają", rec.get("pv_act") == 5.0 and "pv_fc_h" in rec and "pv_fc" not in rec, rec)
    ents = list(rt.log.entries.values()) if isinstance(rt.log.entries, dict) else list(rt.log.entries)
    check("wpis w dzienniku", any("Wyzerowano naukę korekty" in e["msg"] for e in ents))
    check("encja przycisku: button.bms_wyzeruj_korekte_pv", getattr(btn, "_key", "") == "wyzeruj_korekte_pv")
    print(f"PVP50 PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
