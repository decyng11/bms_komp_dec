import asyncio, sys
sys.path.insert(0, ".")
from common import *   # noqa
import common
from custom_components.bms_komp_dec.battery_sign import SignLearner, DEFAULT_SIGN

def feed(L, start_ts, minutes, soc0, soc_per_min, power):
    n = 0
    for i in range(minutes):
        ts = start_ts + i * 60
        soc = soc0 + soc_per_min * i
        if L.add(ts, int(round(soc)), power): n += 1
    return n

async def main():
    # Deye: ładowanie = moc ujemna, SOC rośnie
    L = SignLearner()
    check("sign: brak danych -> domyślny Deye (-1)", L.result(None)["sign"] == -1 and L.result(None)["source"].startswith("domyślny"))
    t = 1_700_000_000.0
    # poszarpane dane (skoki SOC między blokami, luki w próbkach) NIE mogą dawać fałszywych głosów
    Lg = SignLearner()
    for k in range(6):
        feed(Lg, t + k * 3600, 40, 30 + k * 5, 0.25, -2500.0)
    check("sign: luki/skoki SOC między blokami nie dają błędnych głosów", Lg.votes["pos"] == 0, Lg.votes)
    # ciągły przebieg: 3 h ładowania (−2.5 kW), potem 3 h rozładowania (+1.5 kW)
    for i in range(0, 3 * 3600, 30):
        L.add(t + i, 20 + int(i / 3600 * 10), -2500.0)
    for i in range(0, 3 * 3600, 30):
        L.add(t + 3 * 3600 + i, 50 - int(i / 3600 * 6), +1500.0)
    r = L.result(None)
    check("sign: Deye wykryty (−1) z danych", r["sign"] == -1 and r["source"] == "wykryty z danych", (r, L.votes))
    check("sign: głosy zebrane tylko na jedną stronę", L.votes["pos"] == 0 and L.votes["neg"] >= 4, L.votes)

    # odwrotna konwencja: ładowanie = moc dodatnia
    L2 = SignLearner()
    for i in range(0, 4 * 3600, 30):
        L2.add(t + i, 20 + int(i / 3600 * 10), +2500.0)
    check("sign: odwrotna konwencja wykryta (+1)", L2.result(None)["sign"] == 1, L2.votes)
    # rozładowanie: SOC maleje, moc dodatnia w Deye -> też głos „ujemny = ładowanie”
    L3 = SignLearner()
    for i in range(0, 4 * 3600, 30):
        L3.add(t + i, 80 - int(i / 3600 * 10), +2500.0)
    check("sign: rozładowanie przy mocy dodatniej -> Deye (−1)", L3.result(None)["sign"] == -1, L3.votes)
    # słaby przepływ / stały SOC -> brak głosów
    L4 = SignLearner()
    for i in range(0, 4 * 3600, 30):
        L4.add(t + i, 50, -2500.0)                 # SOC stały mimo „mocy” (np. bateria pełna)
        L4.add(t + i + 7, 50 + (1 if i % 3600 > 1800 else 0), -100.0)
    check("sign: bez zmiany SOC / słaba moc -> brak głosów", sum(L4.votes.values()) == 0, L4.votes)
    # ręczny override
    check("sign: ręczne +1 wygrywa z wykrytym", L.result(1.0)["sign"] == 1 and L.result(1.0)["source"] == "ręcznie")
    check("sign: ręczne 0 = auto", L.result(0.0)["sign"] == -1 and L.result(0.0)["source"] == "wykryty z danych")
    # niejednoznaczne (mieszane) -> domyślny
    L5 = SignLearner({"pos": 3, "neg": 3})
    check("sign: remis -> domyślny", L5.result(None)["source"].startswith("domyślny") and L5.result(None)["sign"] == DEFAULT_SIGN)
    # wczytanie zapisanych głosów
    L6 = SignLearner({"pos": 9, "neg": 1})
    check("sign: zapisane głosy wczytane", L6.result(None)["sign"] == 1 and L6.result(None)["source"] == "wykryty z danych")
    check("sign: śmieci w zapisanych głosach nie wywalają", SignLearner("x").votes == {"pos": 0, "neg": 0} and SignLearner({"pos": None}).votes["pos"] == 0)
    # None na wejściu
    check("sign: brak SOC/mocy -> nic", not SignLearner().add(1.0, None, 100.0) and not SignLearner().add(1.0, 50.0, None))

    # ----- integracja z runtime + atrybuty
    hass, c, opt, rt = build()
    c.data = {"battery_power": -2500.0}
    for i in range(0, 3 * 3600, 30):
        stubs.CLOCK["now"] = datetime(2026, 10, 28, 8, 0, 0, tzinfo=TZ) + timedelta(seconds=i)
        hass.states.set(c.config["soc"], 30 + i / 3600 * 10)
        rt._learn_battery_sign(stubs.CLOCK["now"])
    check("runtime: uczy się znaku z ticków (−1)", rt.battery_sign()["sign"] == -1 and rt.battery_sign()["source"] == "wykryty z danych", rt._sign.votes)
    check("runtime: głosy trafiają do stanu do zapisu", rt.state["battery_sign_votes"]["neg"] >= 4)
    hass.states.set("number.bms_battery_charge_sign", 1)
    check("runtime: ręczne ustawienie numberem", rt.battery_sign()["sign"] == 1 and rt.battery_sign()["source"] == "ręcznie")

    from custom_components.bms_komp_dec.sensor import BmsRuntimeSensor
    sens = BmsRuntimeSensor(c, "reserve_soc", "x", "%", "mdi:x")
    sens.coordinator = c
    a = sens._floor_attrs(rt)
    check("atrybuty: znak baterii i źródło", a.get("battery_charge_sign") == 1 and a.get("battery_sign_source") == "ręcznie", a)
    check("atrybuty: taryfa", a.get("tariff_peaks") == "6-13,15-22" and a.get("tariff_night") == "22-6" and a.get("tariff_midday") == "13-15", a)
    check("atrybuty: prądy/moce", a.get("normal_charge_a") == 170 and a.get("sell_power_w") == 6000 and a.get("surplus_power_w") == 9700, a)
    print(f"SIGN PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
