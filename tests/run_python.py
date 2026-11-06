"""Uruchamia testy Pythona (atrapy Home Assistanta) — lokalnie i w GitHub Actions: python tests/run_python.py"""
import os, re, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent / "python"
TESTS = sorted(p.name for p in HERE.glob("test_*.py"))
ARGS = {"test_fuzz.py": ["11", "60"]}
BAD = re.compile(r"(^FAIL\b|FAIL[=:]\s*[1-9]|problemy=[1-9]|Traceback)", re.M)

failed = []
for t in TESTS:
    t0 = time.time()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-B", t, *ARGS.get(t, [])], cwd=HERE, capture_output=True, text=True, env=env, timeout=900)
    out = (r.stdout or "") + (r.stderr or "")
    last = (r.stdout or "").strip().splitlines()[-1:] or ["(brak wyniku)"]
    bad = r.returncode != 0 or bool(BAD.search(r.stdout or ""))
    print(f"{'BŁĄD' if bad else 'OK  '} {t:32s} {time.time() - t0:5.1f} s  {last[0][:110]}")
    if bad:
        failed.append(t)
        print("\n".join(out.strip().splitlines()[-25:]))
print(f"\n{len(TESTS) - len(failed)}/{len(TESTS)} plików testów bez błędów")
sys.exit(1 if failed else 0)
