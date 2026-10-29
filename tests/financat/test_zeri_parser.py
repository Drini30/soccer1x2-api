"""Shumat ashtu si i shkruan njohja e zerit, plus rastet e vjetra qe s'duhet te prishen."""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from datetime import date
import asistenti as A
G = {"llogarite": [{"id": 1, "emri": "NDRICIM PLAKU", "lloji": "bank"},
                   {"id": 9, "emri": "Portofoli", "lloji": "portofol"}]}
C = {"monedha_baze": "LEK"}
RASTET = [
    # zeri
    ("I hodha 20.000 lekë benzinë", 20000), ("i hodha 20 000 lekë benzinë", 20000),
    ("njëzet mijë lekë benzinë", 20000), ("pesëqind lekë kafe", 500),
    ("dy mijë e pesëqind lekë ushqime", 2500), ("një mijë e dyqind lekë parkim", 1200),
    ("njëzet e pesë mijë lekë qiraja e garazhit", 25000), ("tre mijë lekë farmaci", 3000),
    ("dhashë 1 500 lekë për taksi", 1500), ("150 lekë kafe", 150),
    ("një mijë e gjysmë lekë taksi", 1500), ("dy qind lekë kafe", 200),
    ("pesëmbëdhjetë mijë lekë veshje", 15000), ("tetëdhjetë lekë bukë", 80),
    ("bleva një kafe 150 lekë", 150), ("dy kafe 300", 300),
    ("20 mijë e 500 lekë", 20500), ("I hodha 20.000 lekë benzinë.", 20000),
    # te vjetrat
    ("95000", 95000), ("95.000 leke", 95000), ("95,000 leke", 95000),
    ("95 mije", 95000), ("95mije", 95000), ("2.5 milion", 2500000), ("50k", 50000),
    ("nje mije", 1000), ("dy mije", 2000),
    ("pagova 2500 per internetin me 25/09", 2500),
    ("shpenzova 450 lek per kafe sot ne oren 14:20", 450),
    ("paguajta qiran 35 mije nga Ndricim Plaku me 1 shtator", 35000),
    ("800 lek per nje dhurate te vogel", 800), ("bleva ca gjera", None),
]
ok = keq = 0
for f, pritej in RASTET:
    v = A.lexo_shumen(f)
    if v == pritej: ok += 1
    else: keq += 1; print(f"  ✗ {f!r:52} → {v}  (pritej {pritej})")
print(f"\n{'='*60}\nOK: {ok}   DESHTIME: {keq}\n{'='*60}")
sys.exit(1 if keq else 0)
