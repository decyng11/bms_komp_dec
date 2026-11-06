"""Taryfa dynamiczna (0.8.0): szczyty z cen godzinowych, ładowanie w najtańszych godzinach, okna sprzedaży per dzień,
czytnik cen zakupu (Pstryk w dwóch wariantach), ochrona sprzedaży, diagnostyka, dane losowe."""
import asyncio, json, math, random, sys
from datetime import date, datetime, timedelta
sys.path.insert(0, ".")
from common import *   # noqa
import common
from custom_components.bms_komp_dec import health as hlt, sensor as sens
T = tariff; SCH = scheduler

def hourly(d, f, step=60, key="time", valkey="price", tz="+01:00"):
    out = []
    for m in range(0, 24 * 60, step):
        h, mi = divmod(m, 60)
        v = f(h)
        out.append({key: f"{d.isoformat()}T{h:02d}:{mi:02d}:00{tz}", valkey: v})
    return out

TODAY = [0.55, 0.50, 0.45, 0.42, 0.44, 0.50, 0.70, 1.10, 1.25, 1.15, 0.75, 0.45, 0.40, 0.42, 0.48, 0.85, 1.20, 1.40, 1.55, 1.45, 1.25, 0.95, 0.62, 0.50]
TOMOR = [0.52, 0.48, 0.44, 0.41, 0.43, 0.47, 0.51, 0.95, 1.30, 1.05, 0.70, 0.46, 0.38, 0.40, 0.47, 0.60, 0.90, 1.35, 1.60, 1.50, 1.30, 0.80, 0.60, 0.52]

async def env(now, soc=40.0, mode="auto", buy=("bankilo", TODAY, TOMOR), cfg_extra=None, sw=None, nums=None, pv=0.6, load=12.0):
    hass, c, opt0, rt = build(); S = hass.states
    c.data = {"load_forecast": {"tomorrow_forecast": load}, "energy_battery_charge_today": 0.0, "energy_pv_today": 3.0}
    cfg = dict(const.SCHEDULER_DEFAULTS); cfg.update({"tariff_mode": mode, "battery_capacity_kwh": 10.0, "max_charge_power_w": 3000, "target_soc_grid_charge": 90})
    kind = buy[0] if buy else None
    if kind == "bankilo": cfg["price_buy_entity"] = "sensor.pstryk_buy_price"
    elif kind == "kriskomp": cfg["price_buy_entity"] = "sensor.pstryk_current_buy_price"
    elif kind == "g12w": cfg["price_buy_entity"] = "sensor.energy_hub_aktualna_cena_g12w"
    cfg.update(cfg_extra or {})
    at(*now); d0 = date(*now[:3]); d1 = d0 + timedelta(days=1)
    if kind == "bankilo":
        S.set("sensor.pstryk_buy_price", buy[1][now[3]], {"prices_today": hourly(d0, lambda h: buy[1][h]), "prices_tomorrow": hourly(d1, lambda h: buy[2][h]) if buy[2] else []})
    elif kind == "kriskomp":
        S.set("sensor.pstryk_current_buy_price", buy[1][now[3]], {"Best prices": [{"start": f"{d0.isoformat()}T{h:02d}:00:00+01:00", "price": buy[1][h]} for h in (2, 3, 12)]})
        S.set("sensor.pstryk_json_buy", 0, {"prices_today": hourly(d0, lambda h: buy[1][h]), "prices_tomorrow": hourly(d1, lambda h: buy[2][h]) if buy[2] else [],
                                             "prices": hourly(d0, lambda h: buy[1][h]) + (hourly(d1, lambda h: buy[2][h]) if buy[2] else [])})
    elif kind == "g12w":
        g = lambda d: (lambda h: 1.29 if (d.weekday() < 5 and (6 <= h < 13 or 15 <= h < 22)) else 0.62)
        S.set("sensor.energy_hub_aktualna_cena_g12w", g(d0)(now[3]), {"prices": hourly(d0, g(d0)) + hourly(d1, g(d1))})
    rce = lambda h: 300 if 10 <= h < 15 else (900 if 17 <= h < 21 else 500)
    S.set("sensor.rce_pse_cena", 0.6, {"prices": arr(d0, rce) + arr(d1, lambda h: rce(h) + 10)})   # jutro ≠ dziś (kopia byłaby odrzucona)
    def solc(d, f): return {"detailedHourly": [{"period_start": f"{d.isoformat()}T{h:02d}:00:00+01:00", "pv_estimate": f(h)} for h in range(24)]}
    S.set("sensor.solcast_pv_forecast_forecast_today", 4, solc(d0, lambda h: pv if 9 <= h < 15 else 0.0))
    S.set("sensor.solcast_pv_forecast_forecast_tomorrow", 4, solc(d1, lambda h: pv if 9 <= h < 15 else 0.0))
    S.set(c.config["soc"], soc)
    for k, v in (sw or {}).items(): S.set(f"switch.bms_{k}", "on" if v else "off")
    for k, v in (nums or {}).items(): S.set(f"number.bms_{k}", v)
    sched = SCH.ScheduleOptimizer(hass, c, cfg)
    sched.tariff.prices = {"peak": 1.29, "off_peak": 0.62}
    T.set_profile(T.make_profile(cfg, prices_fn=sched.buy_hourly_for, eff_fn=lambda: 0.9, source="test"))
    return hass, c, sched, rt, d0, d1

async def main():
    # ---------------- derive_peaks
    check("G12w (2 poziomy): szczyty = 6–13 i 15–22", T.derive_peaks([1.29 if (6 <= h < 13 or 15 <= h < 22) else 0.62 for h in range(24)]) == ((6, 13), (15, 22)))
    check("dzień TGE: dwa szczyty z przerwą w południe", T.derive_peaks(TODAY) == ((6, 11), (15, 23)), T.derive_peaks(TODAY))
    check("płasko: brak szczytów (pusta krotka)", T.derive_peaks([0.8] * 24) == ())
    check("za mało cen (20/24): None", T.derive_peaks([0.8] * 20 + [None] * 4) is None)
    three = [0.4] * 24
    for h in (2, 3, 9, 10, 18, 19): three[h] = 1.5
    p3 = T.derive_peaks(three)
    check("trzy szczyty → najwyżej dwa (scalone najbliższe)", p3 is not None and len(p3) == 2 and p3[0] == (2, 11) and p3[1] == (18, 20), p3)
    gap = [0.4] * 24
    for h in (7, 8, 10, 11): gap[h] = 1.2
    check("luka 1 h jest scalana", T.derive_peaks(gap) == ((7, 12),), T.derive_peaks(gap))
    neg = [-0.2] * 6 + [0.3] * 18
    check("ujemne ceny: próg liczony ostrożnie, szczyt = droższe godziny", T.derive_peaks(neg) == ((6, 24),), T.derive_peaks(neg))
    check("śmieci w liście (NaN, tekst, bool) są pomijane", T.derive_peaks([float("nan"), "x", True] + [0.4] * 21) is None and T.derive_peaks([float("nan")] + [0.4] * 23) == ())
    check("price_levels", T.price_levels([1.29, 0.62, 1.29, None, "x"]) == 2)

    # ---------------- profil dynamiczny: auto vs dynamic, brak jutra
    base = T.profile_from_config({"tariff_peaks": "6-13,15-22"})
    lists = {date(2026, 11, 4): TODAY, date(2026, 11, 5): None}
    pd = T.DynamicTariffProfile(base, lambda d: lists.get(d), mode="auto")
    at(2026, 11, 4, 12)
    check("auto: dzień z cenami → okna z cen", pd.peaks_for(date(2026, 11, 4)) == ((6, 11), (15, 23)) and pd.dynamic_for(date(2026, 11, 4)))
    check("auto: dzień bez cen → okna z konfiguracji", pd.peaks_for(date(2026, 11, 5)) == ((6, 13), (15, 22)) and not pd.dynamic_for(date(2026, 11, 5)))
    check("is_peak per dzień", pd.is_peak(datetime(2026, 11, 4, 22, tzinfo=TZ)) and not pd.is_peak(datetime(2026, 11, 5, 22, tzinfo=TZ)))
    check("okno południowe z cen", pd.midday_window_for(date(2026, 11, 4)) == (11, 15))
    check("granice nocy (dziś koniec 23, dziś start 6, jutro start 6 z konfiguracji)", pd.night_bounds(datetime(2026, 11, 4, 20, tzinfo=TZ)) == (23, 6, 6))
    g12 = [1.29 if (6 <= h < 13 or 15 <= h < 22) else 0.62 for h in range(24)]
    pa = T.DynamicTariffProfile(T.profile_from_config({"tariff_peaks": "7-21"}), lambda d: g12, mode="auto")
    check("auto + lista 2-poziomowa (G12w) → taryfa strefowa z konfiguracji", not pa.dynamic_for(date(2026, 11, 4)) and pa.peaks_for(date(2026, 11, 4)) == ((7, 21),))
    pdy = T.DynamicTariffProfile(T.profile_from_config({"tariff_peaks": "7-21"}), lambda d: g12, mode="dynamic")
    check("dynamic + lista 2-poziomowa → okna z cen", pdy.dynamic_for(date(2026, 11, 4)) and pdy.peaks_for(date(2026, 11, 4)) == ((6, 13), (15, 22)))
    pz = T.make_profile({"tariff_mode": "zone"}, prices_fn=lambda d: TODAY)
    check("tryb zone → zwykły profil strefowy", isinstance(pz, T.TariffProfile))
    check("brak pola tariff_mode (wpis sprzed 0.8.0) → zone", T.tariff_mode_from_config({}) == "zone" and T.tariff_mode_from_config({"tariff_mode": "x"}) == "zone")
    boom = T.DynamicTariffProfile(base, lambda d: 1 / 0, mode="auto")
    check("wyjątek w źródle cen → okna z konfiguracji, bez wyjątku", boom.peaks_for(date(2026, 11, 4)) == ((6, 13), (15, 22)))

    # ---------------- planer: ładowanie nocne w NAJTAŃSZYCH godzinach
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30), soc=30.0)
    prof = T.get_profile()
    check("profil: dynamiczny dziś i jutro", prof.dynamic_for(d0) and prof.dynamic_for(d1), (prof.peaks_for(d0), prof.peaks_for(d1)))
    res = await sch.suggest()
    P = res["proposals"]
    st, sp = P.get("start_grid_charge", {}), P.get("stop_grid_charge", {})
    check("noc: jest propozycja ładowania", not st.get("skip") and st.get("proposed"), (st, sp))
    if st.get("proposed") and not st.get("skip"):
        h_s = int(st["proposed"][:2]); h_e = int(sp["proposed"][:2]) if sp["proposed"] != "23:59" else 24
        n = (h_e - h_s) % 24 or 24
        start_abs = h_s + (24 if h_s < 20 else 0)
        end_peak = 24 + prof.peaks_for(d1)[0][0]
        price = lambda ha: (TODAY[ha] if ha < 24 else TOMOR[ha - 24])
        blocks = [(sum(price(x) for x in range(s, s + n)) / n, s) for s in range(23, end_peak - n + 1)]
        best = min(b[0] for b in blocks)
        mine = sum(price(x) for x in range(start_abs, start_abs + n)) / n
        check("noc: wybrany blok jest najtańszy z możliwych (sprawdzenie siłowe)", abs(mine - best) < 1e-9, (st["proposed"], sp["proposed"], mine, best))
        check("noc: blok mieści się przed szczytem jutro", start_abs >= 23 and start_abs + n <= end_peak, (start_abs, n, end_peak))
        check("noc: uzasadnienie mówi o najtańszych godzinach", "najtańsze godziny" in st["reason"], st["reason"])
        cur = res["curve"]
        t0 = datetime.fromisoformat(cur["start"])
        idx = [i for i in range(cur["hours"]) if (t0 + timedelta(hours=i)).hour == end_peak - 24 and (t0 + timedelta(hours=i)).date() == d1]
        target = float(st["reason"].split("zostało ~")[1].split("%")[0])
        soc_at_peak = cur["soc"][idx[0] - 1] if idx else None
        check("noc: o początku szczytu SOC ≥ cel (zużycie po ładowaniu uwzględnione)", soc_at_peak is not None and soc_at_peak >= target - 1.5, (soc_at_peak, target))
        check("noc: krzywa — ceny zakupu = ceny godzinowe", all(abs(cur["buy"][i] - price(t0.hour + i if (t0 + timedelta(hours=i)).date() == d0 else 24 + (t0 + timedelta(hours=i)).hour)) < 1e-6 for i in range(cur["hours"])), cur["buy"][:6])
        check("noc: krzywa — znaczniki szczytu z okien dnia", all(cur["peak"][i] == (1 if prof.is_peak(t0 + timedelta(hours=i)) else 0) for i in range(cur["hours"])))
    check("suggest: tryb i ceny taryfy dla dziś", res.get("tariff_mode") == "auto" and res.get("tariff_dynamic") is True and abs(res["g12w_peak"] - sum(TODAY[h] for h in list(range(6, 11)) + list(range(15, 23))) / 13) < 1e-9, (res.get("tariff_mode"), res.get("g12w_peak")))
    sch.tariff.prices = {"peak": 9.0, "off_peak": 9.0}; sch.tariff.sample()
    check("taryfa dynamiczna: kubełki szczyt/noc NIE są uczone z bieżącej ceny", sch.tariff.prices == {"peak": 9.0, "off_peak": 9.0}, sch.tariff.prices)

    # ---------------- jutro bez cen → okna z konfiguracji dla jutra
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30), soc=30.0, buy=("bankilo", TODAY, None), cfg_extra={"tariff_peaks": "7-13,16-21"})
    prof = T.get_profile()
    check("jutro bez cen: dziś z cen, jutro z konfiguracji", prof.dynamic_for(d0) and not prof.dynamic_for(d1) and prof.peaks_for(d1) == ((7, 13), (16, 21)))
    res = await sch.suggest()
    sp = res["proposals"].get("stop_grid_charge", {})
    check("jutro bez cen: ładowanie kończy się najpóźniej o 7:00 (początek szczytu z konfiguracji)", sp.get("skip") or int((sp.get("proposed") or "99")[:2]) <= 7, sp)

    # ---------------- nieopłacalne ładowanie nocne → pominięte z wyjaśnieniem
    # noc droga, tanie tylko południe (realistyczne wahania cen)
    night_exp = [0.95, 0.97, 0.96, 0.94, 0.95, 0.98, 1.02, 1.10, 1.05, 0.70, 0.40, 0.32, 0.30, 0.31, 0.35, 0.60, 1.00, 1.20, 1.30, 1.25, 1.10, 1.00, 0.97, 0.96]
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 21, 30), soc=15.0, buy=("bankilo", night_exp, night_exp[1:] + night_exp[:1]))
    res = await sch.suggest()
    st = res["proposals"].get("start_grid_charge", {})
    check("noc droga: brak opłacalnego ładowania nocnego", st.get("skip") is True, st)

    # ---------------- ładowanie w południe (zestaw 2) w najtańszym bloku
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 9, 30), soc=22.0, sw={"ladowanie_z_sieci_2": True}, pv=0.1, load=18.0)
    res = await sch.suggest()
    s2, e2 = res["proposals"].get("start_grid_charge_2", {}), res["proposals"].get("stop_grid_charge_2", {})
    check("południe: propozycja zestawu 2", not s2.get("skip") and s2.get("proposed"), (s2.get("reason"), e2.get("reason")))
    if s2.get("proposed") and not s2.get("skip"):
        a, b = int(s2["proposed"][:2]), int(e2["proposed"][:2])
        n = b - a
        blocks = [sum(TODAY[x] for x in range(s, s + n)) / n for s in range(11, 15 - n + 1)]
        check("południe: blok w oknie 11–15 i najtańszy", 11 <= a and b <= 15 and abs(sum(TODAY[x] for x in range(a, b)) / n - min(blocks)) < 1e-9, (a, b, blocks))

    # ---------------- sprzedaż: zestaw bierze okno szczytu z dnia, którego dotyczy
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 21, 30), soc=95.0, load=4.0, nums={"min_soc_for_sell": 20, "minimalny_soc_dla_wylaczenia_sprzedazy": 15})
    seen = []
    orig = sch._best_window
    def spy(prices, lo, b, n):
        seen.append((lo, b)); return orig(prices, lo, b, n)
    sch._best_window = spy
    await sch.suggest()
    p1 = T.get_profile().peaks_for(d1)
    check("sprzedaż: zestaw 1 → szczyt poranny JUTRO z cen jutra", any(x == (p1[0][0], p1[0][1]) for x in seen), (seen, p1))
    check("sprzedaż: zestaw 2 → reszta szczytu wieczornego DZIŚ (22–23)", any(x == (22, 23) for x in seen), seen)

    # ---------------- auto + G12w z listą 2-poziomową = zachowanie strefowe
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30), soc=30.0, buy=("g12w", None, None), cfg_extra={"tariff_peaks": "6-13,15-22"})
    r_auto = await sch.suggest()
    check("auto + G12w: profil nie jest dynamiczny", not T.get_profile().dynamic_for(d0))
    T.set_profile(T.profile_from_config({"tariff_peaks": "6-13,15-22"}))
    r_zone = await sch.suggest()
    for r in (r_auto, r_zone):
        r.pop("generated_at", None); r.pop("tariff_mode", None); r.pop("tariff_dynamic", None)
    check("auto + G12w: propozycje identyczne jak w trybie strefowym", r_auto == r_zone)

    # ---------------- czytnik cen zakupu: Pstryk (kriskomp) — lista z encji json, nie z „Best prices”
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30), buy=("kriskomp", TODAY, TOMOR))
    b = sch.buy_hourly_for(d0)
    check("kriskomp: pełna lista dziś z sensor.pstryk_json_buy", b and all(abs(b[h] - TODAY[h]) < 1e-9 for h in range(24)) and "pstryk_json_buy" in (sch.buy_report()["today"]["source"] or ""), sch.buy_report().get("today"))
    check("kriskomp: jutro też", (sch.buy_hourly_for(d1) or [None])[3] == TOMOR[3])
    # kwadranse + MWh
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30))
    hass.states.set("sensor.pstryk_buy_price", 0.9, {"prices_today": hourly(d0, lambda h: TODAY[h] * 1000, 15)})
    b = sch.buy_hourly_for(d0)
    check("kwadranse w PLN/MWh → godzinowe PLN/kWh", b and abs(b[18] - TODAY[18]) < 1e-9, b and b[18])
    # zmiana encji → od razu nowe ceny (bez starej pamięci podręcznej)
    before = T.get_profile().peaks_for(d0)
    hass.states.set("sensor.pstryk_buy_price", 0.9, {"prices_today": hourly(d0, lambda h: TOMOR[h])})
    check("zmiana cen zakupu widoczna od razu (ceny i okna szczytu)", (sch.buy_hourly_for(d0) or [0])[5] == TOMOR[5]
          and T.get_profile().peaks_for(d0) == T.derive_peaks(TOMOR, 0.9) != before, (before, T.get_profile().peaks_for(d0)))

    # ---------------- ochrona: ceny zakupu nie mogą zostać cenami sprzedaży
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30))
    hass.states.set("sensor.rce_pse_cena", 0.5, {"prices": arr(d0, lambda h: 300)[:12]})
    hass.states.set("sensor.pstryk_buy_price_today", 0.9, {"prices": hourly(d0, lambda h: 0.9 + 0.01 * h)})
    sch._read_rce_arrays()
    src = (sch.rce_report()["today"] or {}).get("source") or ""
    check("encja z „buy” w nazwie nie jest źródłem cen sprzedaży", "buy" not in src, sch.rce_report()["today"])
    sch.config["price_sell_entity"] = "sensor.pstryk_buy_price_today"
    sch._read_rce_arrays()
    check("…chyba że użytkownik sam ją wskaże jako cenę sprzedaży", "pstryk_buy_price_today" in (sch.rce_report()["today"]["source"] or ""))

    # ---------------- atrybuty sensora (karta pokazuje dokładnie te ceny)
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30))
    rt.optimizer = sch
    attrs = sens.BmsRuntimeSensor._price_attrs(rt)
    check("sensor: ceny sprzedaży i zakupu dziś/jutro + tryb", attrs.get("prices_buy_today") and abs(attrs["prices_buy_today"][8] - TODAY[8]) < 1e-9
          and attrs.get("prices_sell_today") and attrs.get("tariff_mode") == "auto" and attrs.get("tariff_dynamic") is True, {k: (v if not isinstance(v, list) else len(v)) for k, v in attrs.items()})
    json.dumps(attrs, allow_nan=False)

    # ---------------- diagnostyka (kreator)
    chk = {x["id"]: x for x in hlt.health_check(rt)["checks"]}
    check("diagnostyka: taryfa dynamiczna OK ze źródłem cen", chk["tariff"]["status"] == "ok" and "dynamiczna" in chk["tariff"]["detail"], chk["tariff"])
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30), mode="dynamic", buy=None)
    rt.optimizer = sch
    chk = {x["id"]: x for x in hlt.health_check(rt)["checks"]}
    check("diagnostyka: tryb dynamiczny bez listy cen → błąd z podpowiedzią", chk["tariff"]["status"] == "error" and "pstryk_json_buy" in chk["tariff"]["fix"], chk["tariff"])

    # ---------------- diagnostyka: encje sterujące z falownika dodanego bezpośrednio, z wyłączonym zapisem
    import types as _t
    class _Reg:
        def __init__(self, m): self.m = m
        def async_get(self, eid): return self.m.get(eid)
    class _CE:
        def __init__(self, e): self.e = e
        def async_get_entry(self, i): return self.e.get(i)
    for allow, expect in ((False, True), (True, False)):
        hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30))
        rt.optimizer = sch
        inv = _t.SimpleNamespace(entry_id="inv1", title="Falownik test", data={"kind": "inverter"}, options={"host": "1.2.3.4", **({"allow_write": True} if allow else {})})
        hass.config_entries = _CE({"inv1": inv})
        ents = {rt.eid(r): _t.SimpleNamespace(config_entry_id="inv1") for r in ("work_mode", "charge_current", "export_surplus", "tou_select")}
        sys.modules["homeassistant.helpers.entity_registry"].async_get = lambda h, ents=ents: _Reg(ents)
        chk = {x["id"]: x for x in hlt.health_check(rt)["checks"]}
        has = "direct_write" in chk and chk["direct_write"]["status"] == "error" and "Falownik test" in chk["direct_write"]["detail"]
        check(f"diagnostyka: zapis {'włączony' if allow else 'WYŁĄCZONY'} → ostrzeżenie {'brak' if not expect else 'jest'}", has == expect, chk.get("direct_write"))
    check("diagnostyka: informacja o bibliotece wykresów", "chartjs" in chk and chk["chartjs"]["status"] in ("ok", "warn"), chk.get("chartjs"))

    # ---------------- wykrywanie encji cen (nowa instalacja / „Wykryj encje ponownie”)
    from custom_components.bms_komp_dec import presets as prs
    h2 = stubs.FakeHass()
    h2.states.set("sensor.pstryk_current_buy_price", 0.9); h2.states.set("sensor.pstryk_current_sell_price", 0.4); h2.states.set("sensor.pstryk_json_buy", 0)
    dp = prs.detect_price_entities(h2)
    check("wykrywanie: tylko Pstryk → zakup i sprzedaż z Pstryka, bez mieszania stron", dp == {"price_buy_entity": "sensor.pstryk_current_buy_price", "price_sell_entity": "sensor.pstryk_current_sell_price"}, dp)
    h2.states.set("sensor.rce_pse_cena", 0.5)
    check("wykrywanie: RCE PSE ma pierwszeństwo dla sprzedaży", prs.detect_price_entities(h2)["price_sell_entity"] == "sensor.rce_pse_cena")
    check("wykrywanie: brak encji → pusto", prs.detect_price_entities(stubs.FakeHass()) == {})

    # ---------------- dane losowe: bez wyjątków, wynik czytelny dla przeglądarki
    R = random.Random(5); bad = 0
    for i in range(250):
        junk = lambda: R.choice([None, float("nan"), "x", -5.0, 0.0, 1e9, R.random() * 3, R.random() * 3, R.random() * 3])
        a = [junk() for _ in range(24)]; b2 = [junk() for _ in range(24)] if R.random() < 0.7 else None
        now = R.choice([(2026, 11, 4, R.randrange(24), R.randrange(60)), (2027, 3, 28, R.randrange(24), 0), (2026, 10, 25, R.randrange(24), 0), (2026, 12, 31, 23, 59)])
        try:
            hass, c, sch, rt, d0, d1 = await env(now, soc=R.choice([0, 10, 50, 100, "abc"]), mode=R.choice(["auto", "dynamic"]), buy=("bankilo", a, b2),
                                                 sw={"ladowanie_z_sieci_2": R.random() < 0.5}, pv=R.choice([0, 0.3, 2.0]), load=R.choice([0, 5, 30]))
            r = await sch.suggest()
            json.dumps(r, allow_nan=False)
            cur = r.get("curve")
            if cur and len({len(v) for v in cur.values() if isinstance(v, list)}) > 1: raise ValueError("różne długości krzywej")
        except Exception as e:  # noqa: BLE001
            bad += 1
            if bad <= 3: print("LOSOWE:", type(e).__name__, e, now)
    check("dane losowe (250): bez wyjątków i bez NaN w wyniku", bad == 0, bad)
    # stan encji ceny „nan” nie może zatruć nauczonych cen taryfy (błąd także w 0.7.0)
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 12, 0), mode="zone", buy=("g12w", None, None))
    T.set_profile(T.profile_from_config({}))
    hass.states.set("sensor.energy_hub_aktualna_cena_g12w", "nan"); sch.tariff.sample()
    hass.states.set("sensor.energy_hub_aktualna_cena_g12w", "inf"); sch.tariff.sample()
    check("„nan”/„inf” w stanie ceny nie trafia do nauczonych cen", all(math.isfinite(v) for v in sch.tariff.prices.values() if v is not None), sch.tariff.prices)
    sch.tariff.prices = {"peak": float("nan"), "off_peak": None}
    check("zatruta cena z pamięci → wartość zastępcza zamiast NaN", math.isfinite(sch.tariff.get_price(datetime(2026, 11, 4, 8, tzinfo=TZ))))
    # ---------------- 0.8.5: koszt zużycia baterii (10 zł/kWh — zawsze nieopłacalne) w każdej ścieżce planera
    WEAR = {"battery_price_pln": 100000, "battery_cycles": 1000}
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30), soc=30.0)
    base = (await sch.suggest())["proposals"]["start_grid_charge"]
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30), soc=30.0, nums=WEAR)
    P = (await sch.suggest())["proposals"]["start_grid_charge"]
    check("dynamiczna: bez kosztu zużycia ładowanie jest, z kosztem 10 zł/kWh — pominięte z wyjaśnieniem",
          not base["skip"] and P["skip"] and "zużycia baterii" in P["reason"], (base["reason"], P["reason"]))
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 9, 30), soc=22.0, sw={"ladowanie_z_sieci_2": True}, pv=0.1, load=18.0, nums=WEAR)
    s2 = (await sch.suggest())["proposals"].get("start_grid_charge_2", {})
    check("południe (dynamiczna): koszt zużycia → pominięte", s2.get("skip") and "zużycia" in s2.get("reason", ""), s2.get("reason"))
    sells = lambda r: [v for k, v in r["proposals"].items() if k.startswith("bateria_sprzedaz_start")]
    SN = {"min_soc_for_sell": 20, "minimalny_soc_dla_wylaczenia_sprzedazy": 15}
    hass, c, sched = await mk((2026, 11, 4, 12, 0), 95, load=4.0, pvt=lambda h: 2.0 if 9 <= h < 15 else 0.0, nums=SN)
    b_sell = sells(await sched.suggest())
    hass, c, sched = await mk((2026, 11, 4, 12, 0), 95, load=4.0, pvt=lambda h: 2.0 if 9 <= h < 15 else 0.0, nums=dict(SN, **WEAR))
    w_sell = sells(await sched.suggest())
    check("sprzedaż: bez kosztu zużycia jest okno, z kosztem — pominięte z „zużycie baterii”",
          any(not x["skip"] for x in b_sell) and all(x["skip"] for x in w_sell) and any("zużycie baterii" in x["reason"] for x in w_sell),
          ([x["reason"][:80] for x in b_sell], [x["reason"][:140] for x in w_sell]))
    # strefowa G12w: okno 13–15 (zestaw 2)
    for wear_nums in (None, WEAR):
        hass, c, sched = await mk((2026, 11, 4, 9, 30), 22, load=18.0, pvt=lambda h: 0.1 if 9 <= h < 15 else 0.0, nums=wear_nums)
        hass.states.set("switch.bms_ladowanie_z_sieci_2", "on")
        T.set_profile(T.make_profile(dict(const.SCHEDULER_DEFAULTS), prices_fn=sched.buy_hourly_for, eff_fn=lambda: 0.9, source="test"))
        p2 = (await sched.suggest())["proposals"].get("start_grid_charge_2", {})
        if wear_nums is None:
            zone_base = p2
        else:
            check("południe (G12w): bez kosztu zużycia doładowanie, z kosztem — pominięte",
                  not zone_base.get("skip") and p2.get("skip") and "zużycia" in p2.get("reason", ""), (zone_base.get("reason"), p2.get("reason")))

    print(f"DYN-TARIFF PASS={common.PASS} FAIL={common.FAIL}")
asyncio.run(main())
sys.exit(1 if common.FAIL else 0)
