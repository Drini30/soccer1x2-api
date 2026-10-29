"""Mesataret ditore, ndarja vjetore/mujore, dhe mbrojtja e totalit."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from baza_prove import Baza
import financat
from fastapi import FastAPI
from fastapi.testclient import TestClient

baza = Baza(); financat._sb = baza.sb; financat.PROBLEMET.clear()
app = FastAPI(); app.include_router(financat.router)
kl = TestClient(app); K = {"X-Fin-Token": "token-prove"}

ok = keq = 0
def po(k_, emri, detaj=""):
    global ok, keq
    if k_: ok += 1; print(f"  ✓ {emri}")
    else: keq += 1; print(f"  ✗ {emri} — {detaj}")

def API(rruga, trupi=None, metoda="POST"):
    r = kl.request(metoda, "/api/fin" + rruga, headers=K, json=trupi)
    if r.status_code != 200:
        raise AssertionError(f"{rruga} → {r.status_code}: {r.text[:300]}")
    return r.json()

baza.te_dhenat["fin_cilesimet"] = [
    {"celes": "monedha_baze", "vlera": "ALL"},
    {"celes": "kurset", "vlera": {"ALL": 1.0, "EUR": 98.0}},
    {"celes": "zona_kohore", "vlera": "Europe/Tirane"},
]
banka = API("/te-dhena/llogarite", {"emri": "Banka", "lloji": "bank",
            "monedha": "ALL", "bilanci_fillestar": 300000})
API("/te-dhena/te-ardhurat", {"emri": "Rroga", "lloji": "page",
    "shuma_mujore": 90000, "monedha": "ALL", "dita_pageses": 5,
    "llogaria_id": banka["id"], "siguria": 5})
# Fikse mujore: 30.000/muaj
API("/te-dhena/planet", {"emri": "Qiraja", "drejtimi": "dalje", "shuma": 30000,
    "monedha": "ALL", "frekuenca": "mujore", "dita_pageses": 5,
    "data_fillimit": "2026-01-01", "probabiliteti": 100, "horizonti": "urgjent"})
# Fikse VJETORE: 24.000/vit = 2.000/muaj — nuk duhet te perzihet me mujoret
API("/te-dhena/planet", {"emri": "Siguracioni i makines", "drejtimi": "dalje",
    "shuma": 24000, "monedha": "ALL", "frekuenca": "vjetore",
    "muaji_pageses": 10, "dita_pageses": 15, "data_fillimit": "2026-01-01",
    "probabiliteti": 100, "horizonti": "afatmesem"})

print("\n1. VJETORET NUK PERZIHEN ME MUJORET")
p = API("/panel", metoda="GET")
sh = p["shpenzimet"]
po(sh["fikse_mujore"] == 30000, "fikse mujore = 30.000", sh["fikse_mujore"])
po(sh["fikse_vjetore"] == 24000, "fikse vjetore = 24.000 (ne vit)",
   sh["fikse_vjetore"])
po(sh["vjetore_ne_muaj"] == 2000, "vjetorja i bie 2.000/muaj",
   sh["vjetore_ne_muaj"])
po(sh["nr_fikse_mujore"] == 1 and sh["nr_fikse_vjetore"] == 1,
   "numerohen vec e vec", (sh["nr_fikse_mujore"], sh["nr_fikse_vjetore"]))

print("\n2. SHIRITAT: MESATARE DITORE ME MUAJIN 30-DITESH")
rd = p["rrjedha_ditore"]
po(rd["dite_ne_muaj"] == 30, "muaji numerohet 30 dite")
po(abs(rd["hyrje"]["mujore"] - 90000) < 1, "hyrje 90.000/muaj",
   rd["hyrje"]["mujore"])
po(abs(rd["hyrje"]["ditore"] - 3000) < 1, "hyrje 3.000/dite",
   rd["hyrje"]["ditore"])
po(abs(rd["hyrje"]["javore"] - 21000) < 1, "hyrje 21.000/jave",
   rd["hyrje"]["javore"])
po(abs(rd["dalje"]["mujore"] - 32000) < 1,
   "dalje 32.000/muaj (30.000 mujore + 2.000 nga vjetorja)",
   rd["dalje"]["mujore"])
po(abs(rd["dalje"]["ditore"] - 32000/30) < 0.1, "dalje ~1.067/dite",
   rd["dalje"]["ditore"])
po(abs(rd["bilanci"]["ditore"] - (3000 - 32000/30)) < 0.1,
   "bilanci ditor = hyrje − dalje", rd["bilanci"]["ditore"])
po(abs(rd["bilanci"]["mujore"] - 58000) < 1, "bilanci mujor 58.000",
   rd["bilanci"]["mujore"])

print("\n3. ZBERTHIMI I TREGON TE DYJA VEC E VEC")
emrat = {z["emri"]: z["mujore"] for z in rd["zberthimi_i_daljes"]}
po(emrat.get("Fikse mujore") == 30000, "rreshti mujor", emrat)
po(emrat.get("Fikse vjetore") == 2000,
   "rreshti vjetor mban ekuivalentin mujor", emrat)
po("ne vit" in [z["shenim"] for z in rd["zberthimi_i_daljes"]
                if z["emri"] == "Fikse vjetore"][0],
   "shenimi thote sa eshte ne vit")

print("\n4. VJETORJA HYN TE 'E LIRA' VETEM NE MUAJIN E VET")
import datetime
el = p["e_lira"]
sot = datetime.date.today()
emrat_e_planeve = [x["emri"] for x in el["lista"]["planet"]]
# Rregulli: numerohet vetem nese dita e saj bie brenda horizontit (deri te
# hyrja e radhes), dhe vetem ne muajin e vet.
brenda = (sot.month == 10
          and sot <= datetime.date(sot.year, 10, 15)
          <= datetime.date.fromisoformat(el["deri"]))
po(("Siguracioni i makines" in emrat_e_planeve) == brenda,
   f"brenda horizontit ({el['deri']}): {'po' if brenda else 'jo'}",
   emrat_e_planeve)

# Dhe prova e drejtperdrejte: nje vjetore qe bie SOT duhet te numerohet.
API("/te-dhena/planet", {"emri": "Taksa e tokes", "drejtimi": "dalje",
    "shuma": 12000, "monedha": "ALL", "frekuenca": "vjetore",
    "muaji_pageses": sot.month, "dita_pageses": sot.day,
    "data_fillimit": "2026-01-01", "probabiliteti": 100,
    "horizonti": "afatmesem"})
el2 = API("/panel", metoda="GET")["e_lira"]
po("Taksa e tokes" in [x["emri"] for x in el2["lista"]["planet"]],
   "vjetorja qe bie sot numerohet te 'e lira'",
   [x["emri"] for x in el2["lista"]["planet"]])
# …por nuk i shtohet totalit te fikseve mujore.
sh2 = API("/panel", metoda="GET")["shpenzimet"]
po(sh2["fikse_mujore"] == 30000, "fikset mujore mbeten 30.000",
   sh2["fikse_mujore"])
po(sh2["fikse_vjetore"] == 36000, "fikset vjetore behen 36.000",
   sh2["fikse_vjetore"])

print("\n5. GJENDJA TOTALE NUK SHKON NE MINUS")
API("/portofoli/rimbush", {"llogaria_id": banka["id"], "shuma": 50000})
x = API("/portofoli", metoda="GET")["portofoli"]
po(x["gjendja"] == 50000, "portofoli u mbush", x["gjendja"])
# Portofoli SHKON ne minus sa kohe totali e mbulon
r = API("/portofoli/urdher", {"teksti": "60 mije lek mobilje"})
po(r["portofoli"]["gjendja"] == -10000, "portofoli ne −10.000",
   r["portofoli"]["gjendja"])
likuid = API("/panel", metoda="GET")["bilancet"]["likuiditet"]
po(abs(likuid - 240000) < 1, f"totali mbetet pozitiv ({likuid})")
# Por nje shpenzim qe e kalon totalin REFUZOHET
dyte = kl.post("/api/fin/portofoli/urdher", headers=K,
               json={"teksti": "500 mije lek makine"})
po(dyte.status_code == 400, "shpenzimi mbi totalin refuzohet", dyte.status_code)
po("totale" in dyte.text.lower(), "mesazhi e shpjegon", dyte.text[:220])
po(abs(API("/panel", metoda="GET")["bilancet"]["likuiditet"] - 240000) < 1,
   "asgje nuk u shkrua")
po(API("/portofoli", metoda="GET")["portofoli"]["gjendja"] == -10000,
   "portofoli i paprekur")

print(f"\n{'='*60}\nOK: {ok}   DESHTIME: {keq}\n{'='*60}")
sys.exit(1 if keq else 0)
