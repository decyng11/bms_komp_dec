"""EV i CWU: prąd za nadwyżką, limit przyłącza, cel sesji, bramka temperaturowa CWU, antylegionella."""
import sys
from datetime import datetime
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import evdhw as E


def ev_part():
    check("prąd: 3450 W / 230 V / 1 faza = 15 A", E.amps_for_power(3450, 230, 1, 6, 16) == 15)
    check("prąd: ograniczony do maksimum", E.amps_for_power(9000, 230, 1, 6, 16) == 16)
    check("prąd: poniżej minimum → 0", E.amps_for_power(1200, 230, 1, 6, 16) == 0)
    check("prąd: 3 fazy dzielą moc przez 3", E.amps_for_power(4200, 230, 3, 6, 16) == 6 and E.amps_for_power(4000, 230, 3, 6, 16) == 0)
    for bad in (None, "x", -5, 0, float("nan"), True):
        check(f"prąd: śmieć {bad!r} → 0", E.amps_for_power(bad) == 0)
    check("prąd: odwrócone granice → 0", E.amps_for_power(5000, 230, 1, 16, 6) == 0)
    # limit przyłącza: import 5 kW, limit 6 kW, auto bierze 10 A (2,3 kW) i chce 16 A (3,68 kW) → +1,38 kW → 6,38 kW > 6 kW
    check("limit: bez limitu bez zmian", E.limit_amps(16, 5000, 0, 2300, 230, 1, 6) == 16)
    check("limit: mieści się → bez zmian", E.limit_amps(10, 3000, 6000, 2300, 230, 1, 6) == 10)
    a = E.limit_amps(16, 5000, 6000, 2300, 230, 1, 6)
    check("limit: przekroczenie obniża prąd", 6 <= a < 16, a)
    check("limit: bardzo duży import → wstrzymaj (0)", E.limit_amps(16, 9000, 6000, 2300, 230, 1, 6) == 0)
    check("limit: brak odczytu importu → bez zmian", E.limit_amps(12, None, 6000, 0, 230, 1, 6) == 12)
    check("limit: prąd 0 zostaje 0", E.limit_amps(0, 9000, 6000, 0) == 0)
    # cel
    check("cel kWh osiągnięty", E.ev_goal(20.0, 20, None, 0)[0] and "cel sesji" in E.ev_goal(20.0, 20, None, 0)[1])
    check("cel kWh nieosiągnięty", E.ev_goal(5, 20, None, 0) == (False, None))
    check("cel SOC auta osiągnięty", E.ev_goal(None, 0, 81, 80)[0])
    check("cel: brak celu → nigdy", E.ev_goal(50, 0, None, 0) == (False, None))
    check("cel: śmieci bez wyjątku", E.ev_goal("x", None, "y", float("nan")) == (False, None))
    check("godziny: 12 kWh przy 6 kW = 2 h", E.ev_hours_needed(12, 0, None, 0, 0, 6000) == 2.0)
    check("godziny: z SOC auta 40→80% z 60 kWh przy 7 kW", E.ev_hours_needed(0, 0, 40, 80, 60, 7000) == round(24 / 7, 2))
    check("godziny: brak danych → None", E.ev_hours_needed(0, 0, None, 0, 0, 7000) is None and E.ev_hours_needed(10, 0, None, 0, 0, 0) is None)


def dhw_part():
    D = lambda **k: {"dhw_temp_eid": "sensor.cwu", "dhw_max_c": 60, "dhw_boost_c": 55, "dhw_comfort_c": 45, "dhw_comfort_h": 6, **k}
    n = lambda h, m=0: datetime(2026, 11, 22, h, m)            # niedziela
    r = E.dhw_decide(61, n(12), D(), False)
    check("CWU: ≥ limit → blokada", r["block"] and not r["boost_ok"] and "limit" in r["reason"], r)
    r = E.dhw_decide(56, n(12), D(), False)
    check("CWU: ≥ zadana → blokada trybów oszczędnych", r["block"] and "zadaną" in r["reason"], r)
    r = E.dhw_decide(48, n(12), D(), False)
    check("CWU: między komfortem a zadaną → można grzać", not r["block"] and not r["force"] and r["boost_ok"], r)
    r = E.dhw_decide(40, n(4), D(), False)
    check("CWU: poniżej komfortu 2 h przed porą → wymuś", r["force"] and "komfort" in r["reason"], r)
    r = E.dhw_decide(40, n(14), D(), False)
    check("CWU: poniżej komfortu, ale pora daleko → bez wymuszenia", not r["force"], r)
    r = E.dhw_decide(40, n(6, 30), D(), False)
    check("CWU: po godzinie komfortu nie wymusza (okno minęło)", not r["force"], r)
    r = E.dhw_decide(None, n(12), D(), False)
    check("CWU: czujnik skonfigurowany, brak odczytu → blokada (bezpiecznie)", r["block"], r)
    r = E.dhw_decide(None, n(12), {"dhw_max_c": 0}, False)
    check("CWU: bez czujnika bramka nic nie robi", not r["block"] and not r["force"], r)
    r = E.dhw_decide(200, n(12), D(), False)
    check("CWU: absurdalny odczyt (200 °C) traktowany jak brak odczytu", r["block"] and "brak odczytu" in r["reason"], r)
    leg = D(dhw_leg=True, dhw_leg_c=60, dhw_max_c=65, dhw_boost_c=55)
    r = E.dhw_decide(52, n(12), leg, True)
    check("antylegionella: cel 60 °C ponad zadaną, można grzać", r.get("leg") and r["boost_ok"] and r["target"] == 60 and not r["block"], r)
    r = E.dhw_decide(60.3, n(12), leg, True)
    check("antylegionella: osiągnięta → leg_done", r.get("leg_done") is True, r)
    check("antylegionella: nie włączona → nic", "leg" not in E.dhw_decide(52, n(12), D(), True))
    check("legionella_due: niedziela (6), brak wpisu → tak", E.legionella_due(n(12), 6, None))
    check("legionella_due: już zrobiona w tym tygodniu → nie", not E.legionella_due(n(12), 6, E.week_key(n(12))))
    check("legionella_due: inny dzień → nie", not E.legionella_due(n(12), 2, None))
    check("legionella_due: śmieć → nie", not E.legionella_due(n(12), "x", None))
    check("sane_temp: granice", E.sane_temp(-30) is None and E.sane_temp(96) is None and E.sane_temp(45.5) == 45.5 and E.sane_temp(True) is None)


ev_part()
dhw_part()
print(f"EVDHW PASS={common.PASS} FAIL={common.FAIL}")
