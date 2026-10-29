import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from datetime import date
import asistenti as A

SOT = date(2026, 9, 28)
G = {"llogarite": [
    {"id": 1, "emri": "Ndricim Plaku", "lloji": "bank"},
    {"id": 2, "emri": "Kesh", "lloji": "cash"},
    {"id": 9, "emri": "Portofoli", "lloji": "portofol"}]}
C = {"monedha_baze": "ALL"}

RASTET = [
 ("i hodha 20 mij lek benzin", "shpenzim", {"shuma":20000.0,"kategoria":"karburant"}),
 ("500 lek kafe", "shpenzim", {"shuma":500.0,"kategoria":"kafe"}),
 ("3200 ushqime", "shpenzim", {"shuma":3200.0,"kategoria":"ushqime"}),
 ("dhashe 1500 per parkim", "shpenzim", {"shuma":1500.0,"kategoria":"transport"}),
 ("2 mije lek taksi dje", "shpenzim", {"shuma":2000.0,"data":"2026-09-27"}),
 # pa kategori te njohur — prapeseprape shpenzim, me arsyen e ruajtur
 ("800 lek per nje dhurate te vogel", "shpenzim", {"shuma":800.0}),
 ("1200 lek elektricistit", "shpenzim", {"shuma":1200.0,"kategoria":"shtepia"}),
 # rimbushje
 ("rimbush 20 mije nga Ndricim Plaku", "rimbushje",
  {"shuma":20000.0,"llogaria.id":1}),
 ("mora nga kesh 5000", "rimbushje", {"shuma":5000.0,"llogaria.id":2}),
 # pyetje
 ("sa kam?", "pyetje", {}),
 ("sa me ka mbetur", "pyetje", {}),
 # mungesa
 ("bleva ca gjera", "shpenzim", {"shuma":None}),
 ("rimbush 10000", "rimbushje", {"shuma":10000.0,"llogaria":None}),
]

def merr(p, rruga):
    v = p
    for c in rruga.split("."):
        v = (v or {}).get(c) if isinstance(v, dict) else None
    return v

ok = keq = 0
for fjalia, pritej, kontrollet in RASTET:
    p = A.kupto_portofolin(fjalia, G, C, SOT)
    probleme = []
    if p["veprimi"] != pritej:
        probleme.append(f"veprimi={p['veprimi']} (pritej {pritej})")
    for rruga, vlera in kontrollet.items():
        a = merr(p, rruga)
        if a != vlera: probleme.append(f"{rruga}={a!r} (pritej {vlera!r})")
    if probleme:
        keq += 1
        print(f"  ✗ {fjalia!r}\n      " + "\n      ".join(probleme))
    else:
        ok += 1
        detaj = (p['pyetja'] if p['mungon']
                 else f"{p['shuma']:.0f} · {p.get('kategoria')} · \"{p.get('arsyeja')}\""
                      if p['veprimi'] == 'shpenzim' else p['veprimi'])
        print(f"  ✓ {fjalia!r}  →  {detaj}")
print(f"\n{'='*62}\nOK: {ok}   DESHTIME: {keq}\n{'='*62}")
sys.exit(1 if keq else 0)
