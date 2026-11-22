"""Flota: do 10 falowników i 30 baterii w klastrach — konfiguracja, sumy i alarmy (etap 1: wyłącznie odczyt).

Klaster to grupa falowników (master + slave'y) i baterii, które pracują razem. Falowniki i baterie są niezależnymi listami,
każdy element wskazuje swój klaster, więc „jedna bateria na kilka falowników” i „kilka baterii na jeden falownik” są zwykłym
przypadkiem. SOC klastra to średnia ważona pojemnością baterii. Moduł jest czysty (bez Home Assistanta): odczyty dostaje jako
słownik {encja: {"v": liczba|None, "s": stan jako tekst|None}}; niczego nie zapisuje do urządzeń."""
from __future__ import annotations

import math
import re
from typing import Any

MAX_INVERTERS = 10
MAX_BATTERIES = 30
MAX_CLUSTERS = 10
ROLES = ("master", "slave", "single")
BATT_TYPES = ("LV", "HV")
SOC_OUTLIER_PTS = 15.0        # bateria odstaje od reszty klastra o tyle punktów SOC
TEMP_WARN_INV_C = 65.0
TEMP_WARN_BATT_C = 45.0
_ID_RE = re.compile(r"^[a-z0-9_]{1,24}$")
_EID_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
_BAD = ("unavailable", "unknown", "none", "")
_INV_EIDS = ("pv_eid", "power_eid", "temp_eid", "mode_eid")
_BAT_EIDS = ("soc_eid", "power_eid", "temp_eid")


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def _name(v: Any, default: str) -> str:
    s = re.sub(r"\s+", " ", str(v or "")).strip()[:40]
    return s or default


def _eid(v: Any) -> str:
    s = str(v or "").strip().lower()
    return s if _EID_RE.match(s) else ""


def _ids(items: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    """Unikalne, poprawne id (brakujące i zduplikowane dostają kolejne numery)."""
    seen: set[str] = set()
    n = 1
    for it in items:
        i = str(it.get("id") or "").strip().lower()
        if not _ID_RE.match(i) or i in seen:
            while f"{prefix}{n}" in seen:
                n += 1
            i = f"{prefix}{n}"
        seen.add(i)
        it["id"] = i
    return items


def sanitize(raw: Any) -> dict[str, Any]:
    """Konfiguracja floty z karty → bezpieczna: limity liczby elementów, poprawne id i encje, jeden z ról, klastry istniejące."""
    raw = raw if isinstance(raw, dict) else {}
    clusters = [{"id": str(c.get("id") or "").strip().lower(), "name": _name(c.get("name"), "Klaster")}
                for c in (raw.get("clusters") or []) if isinstance(c, dict)][:MAX_CLUSTERS]
    clusters = _ids(clusters, "k")
    cids = {c["id"] for c in clusters}
    invs = []
    for x in (raw.get("inverters") or []):
        if not isinstance(x, dict) or len(invs) >= MAX_INVERTERS:
            continue
        role = str(x.get("role") or "single")
        d = {"id": str(x.get("id") or ""), "name": _name(x.get("name"), "Falownik"), "cluster": str(x.get("cluster") or "").strip().lower(),
             "role": role if role in ROLES else "single"}
        for k in _INV_EIDS:
            d[k] = _eid(x.get(k))
        invs.append(d)
    bats = []
    for x in (raw.get("batteries") or []):
        if not isinstance(x, dict) or len(bats) >= MAX_BATTERIES:
            continue
        cap = _num(x.get("capacity_kwh"))
        typ = str(x.get("type") or "").upper()
        d = {"id": str(x.get("id") or ""), "name": _name(x.get("name"), "Bateria"), "cluster": str(x.get("cluster") or "").strip().lower(),
             "capacity_kwh": round(min(max(cap, 0.0), 1000.0), 2) if cap is not None else 0.0, "type": typ if typ in BATT_TYPES else "LV"}
        for k in _BAT_EIDS:
            d[k] = _eid(x.get(k))
        bats.append(d)
    invs, bats = _ids(invs, "f"), _ids(bats, "b")
    for it in invs + bats:                                                     # element bez istniejącego klastra → pierwszy klaster
        if it["cluster"] not in cids:
            it["cluster"] = clusters[0]["id"] if clusters else ""
    if not clusters and (invs or bats):
        clusters = [{"id": "k1", "name": "Klaster 1"}]
        for it in invs + bats:
            it["cluster"] = "k1"
    return {"clusters": clusters, "inverters": invs, "batteries": bats}


def _val(vals: dict[str, Any], eid: str) -> tuple[float | None, str | None]:
    r = vals.get(eid) if eid else None
    if not isinstance(r, dict):
        return None, None
    s = r.get("s")
    s = None if s is None or str(s).strip().lower() in _BAD else str(s).strip()
    return _num(r.get("v")), s


def _issue(level: str, cluster: str, kind: str, text: str) -> dict[str, str]:
    return {"level": level, "cluster": cluster, "id": f"{cluster}:{kind}", "text": text}


def evaluate(cfg: dict[str, Any], vals: dict[str, Any]) -> dict[str, Any]:
    """Sumy i alarmy floty. vals: {encja: {"v": liczba|None, "s": tekst|None}} (moc w kW, SOC w %, temperatura w °C)."""
    cfg = sanitize(cfg)
    out_clusters = []
    issues: list[dict[str, str]] = []
    tot_pv = tot_cap = 0.0
    soc_w = soc_cap = 0.0
    socs: list[float] = []
    for c in cfg["clusters"]:
        invs = [i for i in cfg["inverters"] if i["cluster"] == c["id"]]
        bats = [b for b in cfg["batteries"] if b["cluster"] == c["id"]]
        pv = 0.0
        pv_have = False
        inv_rows = []
        for i in invs:
            p, _ = _val(vals, i["pv_eid"])
            if p is None:
                p, _ = _val(vals, i["power_eid"])
            t, _ = _val(vals, i["temp_eid"])
            _, mode = _val(vals, i["mode_eid"])
            cfgd = [k for k in _INV_EIDS if i[k]]
            online = None if not cfgd else any(_val(vals, i[k]) != (None, None) for k in cfgd)       # None = brak encji do oceny
            if p is not None:
                pv += p
                pv_have = True
            inv_rows.append({"id": i["id"], "name": i["name"], "role": i["role"], "power_kw": None if p is None else round(p, 2),
                             "temp_c": None if t is None else round(t, 1), "mode": mode, "online": online})
            if online is False:
                issues.append(_issue("warn", c["id"], f"off_{i['id']}", f"{c['name']}: falownik „{i['name']}” nie odpowiada (encje niedostępne)."))
            if t is not None and t >= TEMP_WARN_INV_C:
                issues.append(_issue("warn", c["id"], f"hot_{i['id']}", f"{c['name']}: falownik „{i['name']}” ma {t:.0f} °C."))
        masters = [r for r in inv_rows if r["role"] == "master"]
        if invs and len(invs) > 1 and len(masters) != 1:
            issues.append(_issue("warn", c["id"], "master", f"{c['name']}: powinien być dokładnie jeden master (jest {len(masters)})."))
        if len(masters) == 1 and masters[0]["mode"]:
            for r in inv_rows:
                if r["role"] == "slave" and r["mode"] and r["mode"].lower() != masters[0]["mode"].lower():
                    r["mismatch"] = True
                    issues.append(_issue("warn", c["id"], f"mode_{r['id']}",
                                         f"{c['name']}: „{r['name']}” ma tryb „{r['mode']}”, a master „{masters[0]['mode']}”."))
        bat_rows = []
        wsum = csum = 0.0
        for b in bats:
            s, _ = _val(vals, b["soc_eid"])
            s = s if s is not None and 0.0 <= s <= 100.0 else None
            p, _ = _val(vals, b["power_eid"])
            t, _ = _val(vals, b["temp_eid"])
            bat_rows.append({"id": b["id"], "name": b["name"], "type": b["type"], "capacity_kwh": b["capacity_kwh"],
                             "soc": None if s is None else round(s, 1), "power_kw": None if p is None else round(p, 2),
                             "temp_c": None if t is None else round(t, 1)})
            tot_cap += b["capacity_kwh"]
            if s is not None and b["capacity_kwh"] > 0:
                wsum += s * b["capacity_kwh"]
                csum += b["capacity_kwh"]
            if b["soc_eid"] and s is None:
                issues.append(_issue("warn", c["id"], f"soc_{b['id']}", f"{c['name']}: brak odczytu SOC baterii „{b['name']}”."))
            if t is not None and t >= TEMP_WARN_BATT_C:
                issues.append(_issue("warn", c["id"], f"bhot_{b['id']}", f"{c['name']}: bateria „{b['name']}” ma {t:.0f} °C."))
        c_soc = round(wsum / csum, 1) if csum > 0 else None
        have = [r for r in bat_rows if r["soc"] is not None and r["capacity_kwh"] > 0]
        if len(have) == 2:                                   # dwie baterie: nie wiadomo, która „odstaje” — wskazujemy niższą, jeden alarm
            lo, hi = sorted(have, key=lambda r: r["soc"])
            gap = hi["soc"] - lo["soc"]
            if gap >= SOC_OUTLIER_PTS:
                lo["outlier"] = round(-gap, 1)
                issues.append(_issue("warn", c["id"], f"out_{lo['id']}",
                                     f"{c['name']}: bateria „{lo['name']}” ma o {gap:.0f} pkt niższy SOC niż „{hi['name']}”."))
        elif len(have) > 2:
            for r in have:
                others = [o for o in have if o is not r]
                oc = sum(o["capacity_kwh"] for o in others)
                mean = sum(o["soc"] * o["capacity_kwh"] for o in others) / oc
                diff = r["soc"] - mean
                if abs(diff) >= SOC_OUTLIER_PTS:
                    r["outlier"] = round(diff, 1)
                    issues.append(_issue("warn", c["id"], f"out_{r['id']}",
                                         f"{c['name']}: bateria „{r['name']}” odstaje o {abs(diff):.0f} pkt SOC od reszty klastra."))
        if csum > 0:
            soc_w += wsum
            soc_cap += csum
            socs.append(c_soc)
        if pv_have:
            tot_pv += pv
        out_clusters.append({"id": c["id"], "name": c["name"], "pv_kw": round(pv, 2) if pv_have else None,
                             "capacity_kwh": round(sum(b["capacity_kwh"] for b in bats), 2), "soc": c_soc,
                             "inverters": inv_rows, "batteries": bat_rows,
                             "status": "warn" if any(x["cluster"] == c["id"] for x in issues) else "ok"})
    return {"clusters": out_clusters, "issues": issues,
            "totals": {"clusters": len(cfg["clusters"]), "inverters": len(cfg["inverters"]), "batteries": len(cfg["batteries"]),
                       "pv_kw": round(tot_pv, 2), "capacity_kwh": round(tot_cap, 2),
                       "soc": round(soc_w / soc_cap, 1) if soc_cap > 0 else None,
                       "soc_spread": round(max(socs) - min(socs), 1) if len(socs) >= 2 else None}}
