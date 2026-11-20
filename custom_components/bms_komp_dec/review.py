"""Ocena trafności planu po dobie: co plan zakładał rano, co się faktycznie stało i co zawiodło najbardziej.

Czyste funkcje (bez Home Assistanta). Wejście to liczby i listy, które runtime zbiera z innych modułów (prognoza PV i zużycia,
plan SOC z rana, plan sprzedaży, księga zysków) — tu tylko oceniamy i opisujemy po polsku.

Każda pozycja ma poziom: ok / warn / bad. Werdykt dnia wynika z poziomów (nie ze średniej, bo jeden duży błąd nie powinien
ginąć wśród trzech dobrych): „trafny”, „częściowo trafny”, „chybiony”. Dla przeciętnego użytkownika najważniejsze jest zdanie
„co zawiodło najbardziej i jaki to miało skutek”."""
from __future__ import annotations

import math
from typing import Any

KEEP_DAYS = 30
PCT_OK, PCT_WARN = 15.0, 30.0           # błąd prognozy PV / zużycia w % faktu
SOC_OK, SOC_WARN = 8.0, 15.0            # średnia różnica planowanego i faktycznego SOC (punkty procentowe)
SALE_OK, SALE_WARN = 0.8, 0.5           # faktyczny eksport w oknach sprzedaży / plan
MIN_KWH = 0.5                           # poniżej tego błąd procentowy nie ma sensu
MIN_SOC_POINTS = 4                      # tyle godzin z planem i faktem potrzeba do oceny SOC
LIMITED_SHARE = 0.15                    # tyle prognozowanej produkcji w godzinach z ucięciem = „to nie błąd prognozy”
LEVEL_RANK = {"ok": 0, "warn": 1, "bad": 2}
LEVELS = tuple(LEVEL_RANK)
VERDICTS = ("trafny", "częściowo trafny", "chybiony")


def _n(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def _f(v: float, d: int = 1) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def _level(mag: float, ok: float, warn: float) -> str:
    return "ok" if mag <= ok else ("warn" if mag <= warn else "bad")


# ------------------------------------------------------------------ pozycje
def _energy_item(iid: str, label: str, fc: Any, act: Any, limited: Any = None) -> dict[str, Any] | None:
    """PV albo zużycie: prognoza dnia kontra wykonanie. `err` w % faktu: dodatni = prognoza zawyżona (jak na karcie trafności)."""
    f, a = _n(fc), _n(act)
    if f is None or a is None or f < 0 or a < MIN_KWH:
        return None
    err = (f - a) / a * 100.0
    lvl = _level(abs(err), PCT_OK, PCT_WARN)
    lim = _n(limited)
    capped = bool(iid == "pv" and err > 0 and lim is not None and lim >= LIMITED_SHARE and lvl != "ok")
    if capped:
        lvl = "warn" if lvl == "bad" else lvl                # bateria pełna, falownik ucinał produkcję — nie wina prognozy
    diff = abs(f - a)
    over = err > 0
    what = "prognoza PV" if iid == "pv" else "prognoza zużycia"
    if lvl == "ok":
        short = f"{'PV' if iid == 'pv' else 'zużycie'} ±{abs(err):.0f}%"
    else:
        short = f"{what} {'zawyżona' if over else 'zaniżona'} o {abs(err):.0f}%"
    if iid == "pv":
        if capped:
            effect = (f"Wyszło o {_f(diff)} kWh mniej, ale ok. {lim * 100:.0f}% prognozowanej produkcji przypadało na godziny, "
                      "w których bateria była pełna i falownik ucinał moc — to nie jest błąd prognozy.")
        elif over:
            effect = f"Słońca było o {_f(diff)} kWh mniej, niż zakładał plan — bateria miała mniej energii, niż planowano."
        else:
            effect = f"Słońca było o {_f(diff)} kWh więcej, niż zakładał plan — plan mógł zbyt ostrożnie dokupować energię z sieci."
    else:
        if over:
            effect = f"Dom zużył o {_f(diff)} kWh mniej, niż zakładał plan — energii zostało więcej, niż planowano."
        else:
            effect = f"Dom zużył o {_f(diff)} kWh więcej, niż zakładał plan — bateria schodziła szybciej i mogło zabraknąć na wieczór."
    return {"id": iid, "label": label, "level": lvl, "plan": round(f, 2), "actual": round(a, 2), "unit": "kWh",
            "err": round(err, 1), "short": short, "text": effect if lvl != "ok" else "",
            "detail": f"prognoza {_f(f)} kWh, wykonanie {_f(a)} kWh",
            "weight": abs(err) / PCT_WARN}


def _soc_item(plan: Any, actual: Any) -> dict[str, Any] | None:
    if not isinstance(plan, list) or not isinstance(actual, list):
        return None
    pairs = []
    for h, (p, a) in enumerate(zip(plan, actual)):
        pn, an = _n(p), _n(a)
        if pn is not None and an is not None:
            pairs.append((h, pn, an))
    if len(pairs) < MIN_SOC_POINTS:
        return None
    mae = sum(abs(p - a) for _h, p, a in pairs) / len(pairs)
    h, p, a = max(pairs, key=lambda x: abs(x[1] - x[2]))
    lvl = _level(mae, SOC_OK, SOC_WARN)
    below = a < p
    short = f"SOC ±{mae:.0f} pp" if lvl == "ok" else f"SOC odbiegał od planu o {mae:.0f} pp"
    effect = (f"Bateria odbiegała od planu średnio o {mae:.0f} pp; najbardziej o {h:02d}:00 (plan {p:.0f}%, było {a:.0f}%) — "
              f"{'miała mniej energii, niż planowano' if below else 'miała więcej energii, niż planowano'}.")
    return {"id": "soc", "label": "Poziom baterii", "level": lvl, "plan": None, "actual": None, "unit": "pp",
            "err": round(mae, 1), "short": short, "text": effect if lvl != "ok" else "",
            "detail": f"średnio ±{mae:.0f} pp na godzinę ({len(pairs)} godz.), największa różnica o {h:02d}:00",
            "weight": mae / SOC_WARN}


def _sale_item(plan: Any, act: Any) -> dict[str, Any] | None:
    if not isinstance(plan, dict):
        return None
    pk = _n(plan.get("kwh"))
    if pk is None or pk < MIN_KWH:
        return None
    ak = _n((act or {}).get("kwh") if isinstance(act, dict) else None) or 0.0
    ratio = max(0.0, ak) / pk
    lvl = "ok" if ratio >= SALE_OK else ("warn" if ratio >= SALE_WARN else "bad")
    short = f"sprzedaż {ratio * 100:.0f}% planu"
    effect = (f"W oknach sprzedaży wyeksportowano {_f(ak)} kWh zamiast planowanych {_f(pk)} kWh — bateria miała za mało energii, "
              "okno było zablokowane albo cena była niższa niż zakładał plan.")
    return {"id": "sale", "label": "Sprzedaż z baterii", "level": lvl, "plan": round(pk, 2), "actual": round(ak, 2), "unit": "kWh",
            "err": round((ratio - 1.0) * 100.0, 1), "short": short, "text": effect if lvl != "ok" else "",
            "detail": f"plan ~{_f(pk)} kWh, wyeksportowano {_f(ak)} kWh",
            "weight": max(0.0, 1.0 - ratio) / SALE_WARN}


# ------------------------------------------------------------------ ocena dnia
def build(day: str, *, pv_fc: Any = None, pv_act: Any = None, pv_limited: Any = None, load_fc: Any = None, load_act: Any = None,
          soc_plan: Any = None, soc_act: Any = None, sale_plan: Any = None, sale_act: Any = None, net: Any = None,
          guards: int = 0, autos: int = 0) -> dict[str, Any] | None:
    """Ocena jednej doby albo None, gdy nie ma z czym porównać (żadnej pary plan–wykonanie)."""
    items = [it for it in (_energy_item("pv", "Produkcja PV", pv_fc, pv_act, pv_limited),
                           _energy_item("load", "Zużycie domu", load_fc, load_act),
                           _soc_item(soc_plan, soc_act),
                           _sale_item(sale_plan, sale_act)) if it]
    if not items:
        return None
    bad = sum(1 for i in items if i["level"] == "bad")
    warn = sum(1 for i in items if i["level"] == "warn")
    if bad >= 2 or (bad >= 1 and len(items) == 1):
        verdict = "chybiony"
    elif bad == 0 and warn <= 1:
        verdict = "trafny"
    else:
        verdict = "częściowo trafny"
    points = sum(LEVEL_RANK[i["level"]] for i in items)
    score = round(100.0 - points / (2.0 * len(items)) * 100.0)
    worst = max(items, key=lambda i: (LEVEL_RANK[i["level"]], i["weight"]))
    culprit = None
    if worst["level"] != "ok":
        culprit = {"id": worst["id"], "label": worst["label"], "level": worst["level"], "text": worst["text"]}
    facts: list[str] = []
    nn = _n(net)
    if nn is not None:
        facts.append(f"Bilans dnia: {nn:+.2f} zł".replace(".", ","))
    if guards:
        facts.append(f"Zabezpieczenia zadziałały {int(guards)}×")
    if autos:
        facts.append(f"Automat zmieniał ustawienia {int(autos)}×")
    for i in items:
        i.pop("weight", None)
    rev = {"date": day, "verdict": verdict, "score": score, "items": items, "culprit": culprit, "facts": facts}
    rev["line"] = summary_line(rev)
    return rev


def summary_line(rev: dict[str, Any]) -> str:
    """Jedno zdanie do podsumowania dnia i dziennika."""
    items = [i for i in (rev.get("items") or []) if isinstance(i, dict)]
    parts = [str(i.get("short")) for i in items if i.get("short")]
    cul = rev.get("culprit") if isinstance(rev.get("culprit"), dict) else None
    head = f"Ocena planu z {rev.get('date')}: {rev.get('verdict')}"
    body = "; ".join(parts)
    if cul and cul.get("label"):
        body += f" (najbardziej zawiodło: {str(cul['label']).lower()})"
    return f"{head} — {body}" if body else head


# ------------------------------------------------------------------ zapis w stanie runtime
def valid(rev: Any) -> bool:
    """Wpis z pliku musi dać się wyświetlić: data, werdykt z listy i lista pozycji słowników."""
    return (isinstance(rev, dict) and isinstance(rev.get("date"), str) and rev.get("verdict") in VERDICTS
            and isinstance(rev.get("items"), list) and all(isinstance(i, dict) for i in rev["items"])
            and (rev.get("culprit") is None or isinstance(rev.get("culprit"), dict))
            and isinstance(rev.get("facts", []), list))


def store(reviews: dict[str, Any], rev: dict[str, Any]) -> None:
    """Dopisuje ocenę dnia i przycina do KEEP_DAYS (najnowsze zostają)."""
    reviews[rev["date"]] = rev
    for k in sorted(reviews)[:-KEEP_DAYS]:
        reviews.pop(k, None)


def recent(reviews: Any, n: int = 14) -> list[dict[str, Any]]:
    """Ostatnie oceny, najnowsze pierwsze; uszkodzone wpisy są pomijane."""
    if not isinstance(reviews, dict):
        return []
    rows = [r for k, r in reviews.items() if isinstance(k, str) and valid(r)]
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows[:max(0, int(n))]


def tally(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Ile ostatnich dób plan był trafny / częściowo / chybiony i co zawodziło najczęściej."""
    counts = {v: 0 for v in VERDICTS}
    culprits: dict[str, int] = {}
    for r in rows:
        if r.get("verdict") in counts:
            counts[r["verdict"]] += 1
        c = r.get("culprit")
        if isinstance(c, dict) and c.get("id"):
            culprits[str(c["id"])] = culprits.get(str(c["id"]), 0) + 1
    top = max(culprits.items(), key=lambda kv: kv[1]) if culprits else None
    return {"n": len(rows), "counts": counts, "top_culprit": top[0] if top else None, "top_culprit_n": top[1] if top else 0}
