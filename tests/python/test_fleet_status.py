"""Narzędzie tools/fleet_status.py: konfiguracja, streszczenie czujników, odczyt z lokalnego serwera próbnego (401/404/śmieci/timeout),
wyjście tekstowe i HTML (escape cudzych danych), tryby wywołania."""
import contextlib, io, json, os, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, ".")
import common
from common import *   # noqa
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
import fleet_status as FS

MON_OK = {"state": "ok", "attributes": {"issues": [], "alarms": []}}
ACC_OK = {"state": "1", "attributes": {"reviews": [
    {"date": "2026-11-18", "verdict": "trafny", "culprit": None},
    {"date": "2026-11-19", "verdict": "częściowo trafny", "culprit": {"label": "Prognoza PV"}}]}}
MON_BAD = {"state": "x", "attributes": {"issues": [
    {"id": "a", "level": "info", "title": "Ceny jutra jeszcze nie ma"},
    {"id": "b", "level": "error", "title": "Brak odczytu SOC", "fix": "sprawdź integrację"},
    {"id": "c", "level": "warn", "title": "Prognoza PV z zapasu"}], "alarms": []}}

ROUTES = {}      # (token, path) → (status, body, delay)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        tok = (self.headers.get("Authorization") or "").replace("Bearer ", "")
        self.server.seen.append((self.command, self.path, tok))
        if tok != self.server.token:
            self.send_response(401); self.end_headers(); return
        r = ROUTES.get(self.path)
        if r is None:
            self.send_response(404); self.end_headers(); return
        status, body, delay = r
        if delay:
            time.sleep(delay)
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        try:
            self.send_response(status); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        except OSError:
            pass


def serve(token="good"):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.token, srv.seen = token, []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def inst(url, token="good", name="Dom", **kw):
    return {"name": name, "url": url, "token": token, "timeout": kw.pop("timeout", 3.0), "monitor": kw.pop("monitor", FS.MONITOR), "accuracy": kw.pop("accuracy", FS.ACCURACY), **kw}


def tmpcfg(obj, mode=0o600):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(obj, f); f.close(); os.chmod(f.name, mode)
    return f.name


def config_part():
    p = tmpcfg({"installations": [{"name": "Dom", "url": "http://100.64.0.1:8123/", "token": "t1"}, {"name": "Dom", "url": "https://x.example", "token": "t2", "timeout": 999},
                                   {"url": "ftp://zly", "token": "t"}, {"name": "Bez tokenu", "url": "http://a"}, "śmieć", {"name": "Inny", "url": "http://b", "token": "t", "monitor_entity": "sensor.x_mon", "timeout": "abc"}]})
    c = FS.load_config(p)
    check("config: 5 wpisów (śmieć pominięty)", len(c) == 5, [x["name"] for x in c])
    check("config: końcowy ukośnik adresu obcięty", c[0]["url"] == "http://100.64.0.1:8123")
    check("config: duplikat nazwy dostaje numer", c[0]["name"] == "Dom" and c[1]["name"] != "Dom", [x["name"] for x in c])
    check("config: timeout ograniczony do 30 s", c[1]["timeout"] == 30.0, c[1]["timeout"])
    check("config: zły adres i brak tokenu oznaczone jako błędne", c[2].get("bad") and c[3].get("bad") and not c[0].get("bad"), c[2:4])
    check("config: własne nazwy encji i zły timeout → domyślny", c[4]["monitor"] == "sensor.x_mon" and c[4]["accuracy"] == FS.ACCURACY and c[4]["timeout"] == FS.TIMEOUT, c[4])
    p2 = tmpcfg([{"name": "A", "url": "http://a", "token": "t"}])
    check("config: sama lista bez klucza installations", len(FS.load_config(p2)) == 1)
    for bad in ({"installations": "x"}, 5, {"foo": 1}):
        try:
            FS.load_config(tmpcfg(bad)); ok_ = False
        except ValueError:
            ok_ = True
        check(f"config: zły kształt ({str(bad)[:20]}) → ValueError", ok_)
    big = tmpcfg({"installations": [{"name": f"i{n}", "url": "http://a", "token": "t"} for n in range(80)]})
    check("config: limit liczby instalacji", len(FS.load_config(big)) == FS.MAX_INSTALLATIONS)
    check("uprawnienia: plik czytelny dla innych → ostrzeżenie", FS.permissions_warning(tmpcfg({}, 0o644)) is not None)
    check("uprawnienia: plik 600 → bez ostrzeżenia", FS.permissions_warning(tmpcfg({}, 0o600)) is None)
    check("uprawnienia: brak pliku → bez wyjątku", FS.permissions_warning("/nie/ma/takiego") is None)


def summary_part():
    s = FS.summarize(MON_OK, ACC_OK)
    check("streszczenie: wszystko ok, ostatnia ocena z 19.11 (najnowsza, nie pierwsza)", s["status"] == "ok" and s["review"]["date"] == "2026-11-19" and s["review"]["culprit"] == "Prognoza PV", s)
    s = FS.summarize(MON_BAD, ACC_OK)
    check("streszczenie: problemy posortowane od najpoważniejszych, status = najgorszy", [i["level"] for i in s["issues"]] == ["error", "warn", "info"] and s["status"] == "error", s["issues"])
    check("streszczenie: podpowiedź naprawy zachowana", s["issues"][0]["fix"] == "sprawdź integrację")
    s = FS.summarize({"attributes": {"issues": [], "alarms": [{"entity_id": "x", "state": "F55"}]}}, None)
    check("streszczenie: aktywny alarm falownika = błąd", s["status"] == "error" and s["alarms"] == 1 and s["review"] is None, s)
    s = FS.summarize(MON_OK, {"attributes": {"reviews": [{"date": "2026-11-19", "verdict": "chybiony"}]}})
    check("streszczenie: chybiony plan bez problemów = info", s["status"] == "info", s)
    s = FS.summarize(MON_OK, {"attributes": {"reviews": [{"date": "2026-11-19", "verdict": "wymyślony"}, {"verdict": "trafny"}, "x"]}})
    check("streszczenie: oceny z nieznanym werdyktem/bez daty pominięte", s["review"] is None and s["status"] == "ok", s)
    s = FS.summarize({"attributes": {"issues": [{"title": "x", "level": "dziwny"}, {"level": "warn"}, "x", None]}}, None)
    check("streszczenie: nieznany poziom → info; wpis bez tytułu pominięty", len(s["issues"]) == 1 and s["issues"][0]["level"] == "info", s)
    s = FS.summarize({"attributes": {"issues": [{"title": f"p{n}", "level": "warn"} for n in range(30)]}}, None)
    check("streszczenie: limit pokazanych problemów, licznik pełny", len(s["issues"]) == FS.MAX_ISSUES_SHOWN and s["issues_total"] == 30, (len(s["issues"]), s["issues_total"]))
    for bad in (None, 5, "x", [], {"attributes": "x"}, {"attributes": {"issues": "x", "alarms": 5, "reviews": 7}}):
        s = FS.summarize(bad, bad)
        check(f"streszczenie: śmieci ({str(bad)[:20]}) nie wywalają", s["status"] == "ok" and s["issues"] == [] and s["alarms"] == 0, s)
    s = FS.summarize({"attributes": {"issues": [{"title": "T" * 999, "level": "warn", "fix": "F" * 999}]}}, None)
    check("streszczenie: długie teksty przycięte", len(s["issues"][0]["title"]) == 200 and len(s["issues"][0]["fix"]) == 300)


def fetch_part():
    srv, url = serve("good")
    ROUTES.clear()
    ROUTES["/api/states/sensor.bms_monitor_status"] = (200, MON_BAD, 0)
    ROUTES["/api/states/sensor.bms_forecast_accuracy"] = (200, ACC_OK, 0)
    r = FS.check_one(inst(url))
    check("odczyt: dwie encje, status error, ocena planu", r["status"] == "error" and r["issues_total"] == 3 and r["review"]["verdict"] == "częściowo trafny" and r["error"] is None, r)
    check("odczyt: tylko GET na dwie encje (nic więcej)", sorted((m, p) for m, p, _ in srv.seen) == [("GET", "/api/states/sensor.bms_forecast_accuracy"), ("GET", "/api/states/sensor.bms_monitor_status")], srv.seen)
    check("odczyt: token poszedł w nagłówku, nie w adresie", all(t == "good" and "good" not in p for _, p, t in srv.seen))

    r = FS.check_one(inst(url, token="zly-token-123"))
    check("zły token: offline z opisem, bez tokenu w komunikacie", r["status"] == "offline" and "token odrzucony" in r["error"] and "zly-token-123" not in json.dumps(r), r)

    ROUTES.pop("/api/states/sensor.bms_forecast_accuracy")
    r = FS.check_one(inst(url))
    check("brak czujnika oceny: instalacja nadal działa, bez oceny", r["status"] == "error" and r["review"] is None and r["error"] is None, r)
    ROUTES.pop("/api/states/sensor.bms_monitor_status")
    r = FS.check_one(inst(url))
    check("brak czujnika EMS (404): offline z podpowiedzią", r["status"] == "offline" and "brak encji" in r["error"], r)

    ROUTES["/api/states/sensor.bms_monitor_status"] = (200, b"<html>to nie JSON</html>", 0)
    r = FS.check_one(inst(url))
    check("odpowiedź nie-JSON: offline", r["status"] == "offline" and "JSON" in r["error"], r)
    ROUTES["/api/states/sensor.bms_monitor_status"] = (200, b"[1,2,3]", 0)
    check("JSON o złym kształcie: offline", FS.check_one(inst(url))["status"] == "offline")
    ROUTES["/api/states/sensor.bms_monitor_status"] = (500, b"boom", 0)
    check("HTTP 500: offline z kodem", "HTTP 500" in FS.check_one(inst(url))["error"])
    ROUTES["/api/states/sensor.bms_monitor_status"] = (200, b"x" * (FS.MAX_BYTES + 10), 0)
    check("zbyt duża odpowiedź: odrzucona", "zbyt duża" in FS.check_one(inst(url))["error"])
    ROUTES["/api/states/sensor.bms_monitor_status"] = (200, MON_OK, 2.5)
    t0 = time.time()
    r = FS.check_one(inst(url, timeout=1.0))
    check("timeout: offline po ~1 s, nie wisi", r["status"] == "offline" and time.time() - t0 < 2.4, (r["status"], round(time.time() - t0, 1)))

    dead = serve()[1]
    s2, u2 = serve(); s2.shutdown(); s2.server_close()
    r = FS.check_one(inst(u2))
    check("serwer wyłączony: offline (brak połączenia)", r["status"] == "offline" and "brak połączenia" in r["error"], r)
    check("zły wpis konfiguracji: offline z opisem", FS.check_one({"name": "X", "bad": "brak tokenu"})["error"] == "brak tokenu")

    for evil in ("sensor.x/../../config", "light.x", "sensor.a b", "sensor.a?b=1", ""):
        n0 = len(srv.seen)
        r = FS.check_one(inst(url, monitor=evil))
        check(f"zła nazwa encji „{evil}” nie jest wysyłana", r["status"] == "offline" and "zła nazwa encji" in r["error"] and len(srv.seen) == n0, r)

    # kilka instalacji naraz, kolejność jak w pliku
    ROUTES["/api/states/sensor.bms_monitor_status"] = (200, MON_OK, 0.4)
    ROUTES["/api/states/sensor.bms_forecast_accuracy"] = (200, ACC_OK, 0)
    items = [inst(url, name=f"I{n}") for n in range(4)] + [inst(url, token="zly", name="Zły")]
    t0 = time.time()
    res = FS.check_all(items)
    el = time.time() - t0
    check("równolegle: kolejność wyniku jak w pliku", [r["name"] for r in res] == ["I0", "I1", "I2", "I3", "Zły"], [r["name"] for r in res])
    check("równolegle: 4 odczyty po 0,4 s trwają krócej niż po kolei", el < 1.4, round(el, 2))
    check("równolegle: jedna zła nie psuje reszty", [r["status"] for r in res] == ["ok"] * 4 + ["offline"], [r["status"] for r in res])
    check("pusta lista → pusty wynik", FS.check_all([]) == [])
    srv.shutdown()


def view_part():
    evil = '<img src=x onerror="alert(1)">'
    res = [{"name": "Dobra", "status": "ok", "issues": [], "issues_total": 0, "alarms": 0, "review": {"date": "2026-11-19", "verdict": "trafny", "culprit": None}, "error": None, "checked_at": "10:00:00"},
           {"name": evil, "status": "error", "issues": [{"level": "error", "title": evil, "fix": ""}, {"level": "warn", "title": "Ostrz", "fix": ""}], "issues_total": 5, "alarms": 2,
            "review": {"date": "2026-11-19", "verdict": "chybiony", "culprit": evil}, "error": None, "checked_at": "10:00:01"},
           {"name": "Off", "status": "offline", "issues": [], "issues_total": 0, "alarms": 0, "review": None, "error": evil, "checked_at": "10:00:02"}]
    t = FS.render_text(res)
    check("tekst: najgorsze na górze (error, offline, ok)", t.index("Off") > t.index(evil) and t.index("Dobra") > t.index("Off"), t[:300])
    check("tekst: dla zdrowej „wszystko działa”, dla offline powód, ‘i N więcej’", "wszystko działa" in t and "brak odczytu" in t and "i 3 więcej" in t, t)
    h = FS.render_html(res)
    check("HTML: cudzy tekst w escape (brak żywego znacznika img)", "<img" not in h and "&lt;img" in h, h[h.find("Status"):][:400])
    check("HTML: brak skryptów i zdarzeń", "<script" not in h.lower() and "onerror=\"" not in h, "")
    check("HTML: wszystkie trzy karty, offline widoczny", h.count('class="card') == 3 and "Brak odczytu" in h)
    check("HTML: pusty wynik też się renderuje", "<div class=\"grid\"></div>" in FS.render_html([]))
    check("tekst: pusty wynik", "Status instalacji" in FS.render_text([]))
    bad = FS.render_html([{"name": "Z", "status": "dziwny", "issues": [], "issues_total": 0, "alarms": 0, "review": None, "error": "x", "checked_at": "1"}])
    check("HTML: nieznany status traktowany jak offline", 'class="card offline"' in bad, bad[-300:])


def main_part():
    srv, url = serve("good")
    ROUTES.clear()
    ROUTES["/api/states/sensor.bms_monitor_status"] = (200, MON_BAD, 0)
    ROUTES["/api/states/sensor.bms_forecast_accuracy"] = (200, ACC_OK, 0)
    cfg = tmpcfg({"installations": [{"name": "Dom", "url": url, "token": "good"}, {"name": "Kuba", "url": url, "token": "zly"}]})
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = FS.main([cfg])
    check("main: tabela w terminalu, kod 0, token nie wycieka", rc == 0 and "Dom" in out.getvalue() and "Kuba" in out.getvalue() and "good" not in out.getvalue() + err.getvalue(), out.getvalue()[:300])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = FS.main([cfg, "--json"])
    data = json.loads(out.getvalue())
    check("main --json: lista wyników bez tokenów", rc == 0 and len(data) == 2 and "good" not in out.getvalue() and "zly" not in out.getvalue(), data)
    path = os.path.join(tempfile.mkdtemp(), "o.html")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = FS.main([cfg, "--html", path])
    check("main --html: plik strony zapisany", rc == 0 and os.path.exists(path) and "<!doctype html>" in open(path, encoding="utf-8").read(), out.getvalue())
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = FS.main(["/nie/ma/pliku.json"])
    check("main: brak pliku → kod 2 z komunikatem", rc == 2 and "Nie mogę wczytać" in err.getvalue(), err.getvalue())
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        rc = FS.main([tmpcfg({"installations": []}, 0o644)])
    check("main: plik czytelny dla innych → ostrzeżenie na stderr", "chmod 600" in err.getvalue(), err.getvalue())
    bad = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); bad.write("{nie json"); bad.close()
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = FS.main([bad.name])
    check("main: uszkodzony JSON → kod 2, bez zrzutu stosu", rc == 2, err.getvalue())
    srv.shutdown()


config_part()
summary_part()
fetch_part()
view_part()
main_part()
print(f"FLEET_STATUS PASS={common.PASS} FAIL={common.FAIL}")
