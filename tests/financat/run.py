"""Ekzekuton te gjitha provat e financave dhe jep nje total.

    python3 tests/financat/run.py

Kerkon: fastapi, httpx, requests, tzdata. Nuk prek Supabase: cdo prove
perdor bazen e rreme te baza_prove.py, me te njejtat rregulla si migrimet.
"""
import pathlib
import re
import subprocess
import sys

dosja = pathlib.Path(__file__).resolve().parent
gjithsej_ok = gjithsej_keq = 0
for prova in sorted(dosja.glob("test_*.py")):
    r = subprocess.run([sys.executable, str(prova)], capture_output=True, text=True)
    m = re.search(r"OK: (\d+)\s+DESHTIME: (\d+)", r.stdout)
    if not m or r.returncode != 0:
        print(f"  ✗ {prova.name:26s} u rrezua")
        print("    " + (r.stdout + r.stderr).strip().replace("\n", "\n    ")[-1500:])
        gjithsej_keq += 1
        continue
    ok, keq = int(m.group(1)), int(m.group(2))
    gjithsej_ok += ok; gjithsej_keq += keq
    print(f"  {'✓' if not keq else '✗'} {prova.name:26s} {ok} ok, {keq} deshtime")
print(f"\n{'='*50}\nGJITHSEJ: {gjithsej_ok} ok, {gjithsej_keq} deshtime\n{'='*50}")
sys.exit(1 if gjithsej_keq else 0)
