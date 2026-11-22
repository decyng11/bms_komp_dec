"""Flota (etap 1): konfiguracja do 10 falowników i 30 baterii, SOC ważony pojemnością, alarmy, odporność na śmieci."""
import json, sys
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import fleet as F


def V(**k):
    return {e: {"v": (v if not isinstance(v, str) else None), "s": str(v)} for e, v in k.items()}


CFG = {"clusters": [{"id": "k1", "name": "Dom"}, {"id": "k2", "name": "Garaż"}],
       "inverters": [
           {"id": "a", "name": "A", "cluster": "k1", "role": "master", "pv_eid": "sensor.a_pv", "temp_eid": "sensor.a_t", "mode_eid": "select.a_mode"},
           {"id": "b", "name": "B", "cluster": "k1", "role": "slave", "pv_eid": "sensor.b_pv", "mode_eid": "select.b_mode"},
           {"id": "c", "name": "C", "cluster": "k2", "role": "master", "pv_eid": "sensor.c_pv", "mode_eid": "select.c_mode"},
           {"id": "d", "name": "D", "cluster": "k2", "role": "slave", "pv_eid": "sensor.d_pv", "mode_eid": "select.d_mode"}],
       "batteries": [
           {"id": "b1", "name": "Szafa 1", "cluster": "k1", "capacity_kwh": 10, "type": "HV", "soc_eid": "sensor.b1_soc"},
           {"id": "b2", "name": "Szafa 2", "cluster": "k1", "capacity_kwh": 10, "type": "HV", "soc_eid": "sensor.b2_soc"},
           {"id": "g1", "name": "Pakiet 1", "cluster": "k2", "capacity_kwh": 10, "soc_eid": "sensor.g1_soc"},
           {"id": "g2", "name": "Pakiet 2", "cluster": "k2", "capacity_kwh": 5, "soc_eid": "sensor.g2_soc"}]}
OK = V(**{"sensor.a_pv": 3.0, "sensor.b_pv": 2.2, "sensor.c_pv": 1.3, "sensor.d_pv": 0.9, "sensor.a_t": 41,
          "select.a_mode": "Zero export", "select.b_mode": "Zero export", "select.c_mode": "Selling first", "select.d_mode": "Selling first",
          "sensor.b1_soc": 74, "sensor.b2_soc": 70, "sensor.g1_soc": 63, "sensor.g2_soc": 60})


def part_sanitize():
    s = F.sanitize(CFG)
    check("sanitize: zachowuje poprawną konfigurację", len(s["clusters"]) == 2 and len(s["inverters"]) == 4 and len(s["batteries"]) == 4 and s["batteries"][0]["type"] == "HV")
    big = {"inverters": [{"name": f"f{i}"} for i in range(40)], "batteries": [{"name": f"b{i}", "capacity_kwh": 5} for i in range(80)],
           "clusters": [{"name": f"k{i}"} for i in range(30)]}
    s = F.sanitize(big)
    check("limity: 10 falowników, 30 baterii, 10 klastrów", len(s["inverters"]) == 10 and len(s["batteries"]) == 30 and len(s["clusters"]) == 10)
    check("id unikalne i poprawne", len({x["id"] for x in s["inverters"]}) == 10 and all(F._ID_RE.match(x["id"]) for x in s["batteries"]))
    s = F.sanitize({"inverters": [{"name": "x", "cluster": "nie_ma", "role": "szef", "pv_eid": "złe encja", "temp_eid": "SENSOR.T_1"}]})
    check("sanitize: bez klastra tworzy Klaster 1, zła rola → single, zła encja pusta, duże litery obniżone",
          s["clusters"][0]["id"] == "k1" and s["inverters"][0]["cluster"] == "k1" and s["inverters"][0]["role"] == "single" and s["inverters"][0]["pv_eid"] == "" and s["inverters"][0]["temp_eid"] == "sensor.t_1", s)
    s = F.sanitize({"clusters": [{"id": "k1", "name": "A"}, {"id": "k1", "name": "B"}]})
    check("zduplikowane id klastrów rozróżnione", len({c["id"] for c in s["clusters"]}) == 2)
    for bad in (None, 5, "x", [], {"inverters": "x"}, {"batteries": [None, 3, {"capacity_kwh": "abc"}]}):
        r = F.sanitize(bad)
        check(f"sanitize: śmieć {str(bad)[:20]!r} bez wyjątku", isinstance(r, dict) and set(r) == {"clusters", "inverters", "batteries"})
    s = F.sanitize({"batteries": [{"capacity_kwh": -5}, {"capacity_kwh": 99999}]})
    check("pojemność przycięta do 0–1000", s["batteries"][0]["capacity_kwh"] == 0.0 and s["batteries"][1]["capacity_kwh"] == 1000.0)


def part_eval():
    r = F.evaluate(CFG, OK)
    json.dumps(r, allow_nan=False)
    t = r["totals"]
    check("sumy: 4 falowniki, 4 baterie, 2 klastry, PV 7,4 kW, 35 kWh", t["inverters"] == 4 and t["batteries"] == 4 and t["clusters"] == 2 and t["pv_kw"] == 7.4 and t["capacity_kwh"] == 35.0, t)
    k1, k2 = r["clusters"]
    check("SOC klastra 1: (74+70)/2 = 72", k1["soc"] == 72.0, k1["soc"])
    check("SOC klastra 2 ważony pojemnością: (63·10+60·5)/15 = 62", k2["soc"] == 62.0, k2["soc"])
    check("SOC floty ważony: (72·20 + 62·15)/35 = 67,7", t["soc"] == 67.7, t["soc"])
    check("rozrzut SOC klastrów = 10", t["soc_spread"] == 10.0, t)
    check("PV klastra 1 = 5,2 kW", k1["pv_kw"] == 5.2)
    check("brak alarmów w zdrowej flocie", r["issues"] == [] and all(c["status"] == "ok" for c in r["clusters"]), r["issues"])

    v = dict(OK); v["select.d_mode"] = {"v": None, "s": "Zero export"}
    r = F.evaluate(CFG, v)
    check("rozjazd trybu slave ≠ master → alarm", any(i["id"] == "k2:mode_d" for i in r["issues"]) and r["clusters"][1]["status"] == "warn", r["issues"])

    v = dict(OK); v["sensor.g2_soc"] = {"v": 20.0, "s": "20"}
    r = F.evaluate(CFG, v)
    check("bateria odstająca o ≥ 15 pkt → alarm z wartością", any(i["id"] == "k2:out_g2" for i in r["issues"]) and r["clusters"][1]["batteries"][1].get("outlier") == -43.0, r["issues"])

    v = dict(OK); v["sensor.b1_soc"] = {"v": None, "s": "unavailable"}
    r = F.evaluate(CFG, v)
    check("brak SOC baterii → alarm, SOC klastra z pozostałej", any(i["id"] == "k1:soc_b1" for i in r["issues"]) and r["clusters"][0]["soc"] == 70.0, r["issues"])

    v = {k: {"v": None, "s": "unavailable"} for k in OK}
    r = F.evaluate(CFG, v)
    check("wszystko niedostępne: falowniki nie odpowiadają, bez wyjątków i bez PV", sum(1 for i in r["issues"] if "nie odpowiada" in i["text"]) == 4 and r["totals"]["pv_kw"] == 0.0 and r["totals"]["soc"] is None)

    v = dict(OK); v["sensor.a_t"] = {"v": 70.0, "s": "70"}
    check("temperatura falownika ≥ 65 °C → alarm", any(i["id"] == "k1:hot_a" for i in F.evaluate(CFG, v)["issues"]))

    cfg2 = json.loads(json.dumps(CFG)); cfg2["inverters"][1]["role"] = "master"
    check("dwa mastery w klastrze → alarm", any(i["id"] == "k1:master" for i in F.evaluate(cfg2, OK)["issues"]))
    cfg3 = json.loads(json.dumps(CFG)); cfg3["inverters"] = [dict(cfg3["inverters"][0], role="single")]
    check("jeden falownik (single) nie wymaga mastera", not any(i["id"].endswith(":master") for i in F.evaluate(cfg3, OK)["issues"]))
    check("pusta flota → puste sumy", F.evaluate({}, {})["totals"]["inverters"] == 0 and F.evaluate(None, None)["clusters"] == [])
    v = dict(OK); v["sensor.b1_soc"] = {"v": 150.0, "s": "150"}
    check("SOC poza 0–100 odrzucony", F.evaluate(CFG, v)["clusters"][0]["batteries"][0]["soc"] is None)
    cfg4 = json.loads(json.dumps(CFG)); cfg4["batteries"][0]["capacity_kwh"] = 0; cfg4["batteries"][1]["capacity_kwh"] = 0
    check("pojemność 0 → SOC klastra None, bez dzielenia przez zero", F.evaluate(cfg4, OK)["clusters"][0]["soc"] is None)


part_sanitize()
part_eval()


import asyncio
from custom_components.bms_komp_dec import notify_cfg as N


async def runtime_part():
    hass, c, opt, rt = build()
    at(2026, 11, 22, 10, 0)
    check("fleet_get bez konfiguracji: puste sumy, limity", rt.fleet_get()["totals"]["inverters"] == 0 and rt.fleet_get()["limits"] == {"inverters": 10, "batteries": 30, "clusters": 10})
    cfg = rt.fleet_set(CFG)
    check("fleet_set zapisuje oczyszczoną konfigurację w stanie", rt.state["fleet"] == cfg and len(cfg["inverters"]) == 4)
    for eid, v in (("sensor.a_pv", 3000), ("sensor.b_pv", 2200), ("sensor.c_pv", 1.3), ("sensor.d_pv", 0.9)):
        hass.states.set(eid, v, {"unit_of_measurement": "W" if v > 100 else "kW"})
    for eid, v in (("sensor.b1_soc", 74), ("sensor.b2_soc", 70), ("sensor.g1_soc", 63), ("sensor.g2_soc", 20)):
        hass.states.set(eid, v)
    hass.states.set("select.a_mode", "Zero export"); hass.states.set("select.b_mode", "Zero export")
    hass.states.set("select.c_mode", "Selling first"); hass.states.set("select.d_mode", "Selling first")
    hass.states.set("sensor.a_t", 41)
    r = rt.fleet_get()
    json.dumps(r, allow_nan=False)
    check("moc w W przeliczona na kW (3000 W + 2200 W = 5,2 kW)", r["clusters"][0]["pv_kw"] == 5.2, r["clusters"][0])
    check("alarm odstającej baterii z odczytów encji", any(i["id"] == "k2:out_g2" for i in r["issues"]), r["issues"])
    rt.state["notify_cfg"] = N.effective({"phone_level": "all"})
    await rt.monitor._fleet(at(2026, 11, 22, 10, 0))
    inb = [i for i in rt.state.get("inbox", []) if i.get("kind") == "fleet_alert"]
    check("monitor: jedno powiadomienie o alarmie floty", len(inb) == 1, inb)
    await rt.monitor._fleet(at(2026, 11, 22, 11, 0))
    check("monitor: bez powtórki tego samego zestawu tego dnia", len([i for i in rt.state.get("inbox", []) if i.get("kind") == "fleet_alert"]) == 1)
    hass2, c2, opt2, rt2 = build()
    await rt2.monitor._fleet(at(2026, 11, 22, 10, 0))
    check("monitor: bez floty cisza i bez wyjątku", not [i for i in rt2.state.get("inbox", []) if i.get("kind") == "fleet_alert"])
    check("katalog: fleet_alert, priorytet 2, grupa istnieje", N.PRIORITY["fleet_alert"] == 2 and N.CATALOG["fleet_alert"][0] in N.GROUPS)
    rt.state["fleet"] = "śmieć"
    check("śmieciowy stan floty nie psuje odczytu", rt.fleet_get()["totals"]["inverters"] == 0)

asyncio.run(runtime_part())
print(f"FLEET(runtime) PASS={common.PASS} FAIL={common.FAIL}")


def three():
    cfg = {"clusters": [{"id": "k1", "name": "K"}], "inverters": [],
           "batteries": [{"id": f"b{i}", "name": f"B{i}", "cluster": "k1", "capacity_kwh": 5, "soc_eid": f"sensor.s{i}"} for i in range(1, 5)]}
    v = V(**{"sensor.s1": 70, "sensor.s2": 72, "sensor.s3": 71, "sensor.s4": 40})
    r = F.evaluate(cfg, v)
    ids = [i["id"] for i in r["issues"]]
    check("cztery baterie: odstaje tylko jedna (ta z 40%)", ids == ["k1:out_b4"], ids)
    two = dict(cfg, batteries=cfg["batteries"][:2])
    r = F.evaluate(two, V(**{"sensor.s1": 70, "sensor.s2": 30}))
    check("dwie baterie: jeden alarm wskazujący niższą", [i["id"] for i in r["issues"]] == ["k1:out_b2"], r["issues"])


three()
print(f"FLEET(3) PASS={common.PASS} FAIL={common.FAIL}")
