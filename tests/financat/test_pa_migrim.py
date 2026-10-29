"""Pa migrimin 7: asgje nuk duhet te thyhet, dhe asgje nuk duhet te heshtet."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from baza_prove import Baza

import financat
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Baze si e djeshmja: pa fin_veprimet dhe pa kolonen kryer_me.
ekzistuese = {"fin_llogarite", "fin_transaksionet", "fin_detyrimet",
              "fin_planet", "fin_te_ardhurat", "fin_investimet",
              "fin_objektivat", "fin_raportet", "fin_cilesimet",
              "fin_bizneset", "fin_biznes_zerat", "fin_buxhetet",
              "fin_personat"}
baza = Baza(tabelat_ekzistuese=ekzistuese)
baza.migrimi7 = False
financat._sb = baza.sb
financat.PROBLEMET.clear()

app = FastAPI(); app.include_router(financat.router)
kl = TestClient(app)
K = {"X-Fin-Token": "token-prove"}

nr_ok = nr_keq = 0
def po(kusht, emri, detaj=""):
    global nr_ok, nr_keq
    if kusht: nr_ok += 1; print(f"  ✓ {emri}")
    else: nr_keq += 1; print(f"  ✗ {emri} — {detaj}")

baza.te_dhenat["fin_cilesimet"] = [
    {"celes": "monedha_baze", "vlera": "ALL"},
    {"celes": "kurset", "vlera": {"ALL": 1.0, "EUR": 98.0}},
]

print("\n1. SHKRIMI VAZHDON PA MIGRIMIN")
llog = kl.post("/api/fin/te-dhena/llogarite", headers=K, json={
    "emri": "Kesh", "lloji": "cash", "monedha": "ALL",
    "bilanci_fillestar": 5000})
po(llog.status_code == 200, "llogaria u shtua", llog.text[:200])
r = kl.post("/api/fin/te-dhena/transaksionet", headers=K, json={
    "data": "2026-09-20", "ora": "21:15", "lloji": "dalje", "shuma": 700,
    "monedha": "ALL", "llogaria_id": llog.json()["id"]})
po(r.status_code == 200, "transaksioni u shkrua edhe pa kolonen", r.text[:250])
po(r.json().get("kryer_me") is None, "pa ore, sic pritej", r.json())
po(r.json()["data"] == "2026-09-20", "data mbetet", r.json().get("data"))

print("\n2. MUNGESA RAPORTOHET, NUK FSHIHET")
mesazhet = " | ".join(p["mesazhi"] for p in financat.PROBLEMET)
po("financat_migrim_7.sql" in mesazhet,
   "problemi emerton skedarin qe e ndreq", mesazhet)
po("kryer_me" in mesazhet, "kolona qe mungon permendet", mesazhet)
po("Ditari" in mesazhet, "edhe ditari qe mungon permendet", mesazhet)

sh = kl.get("/api/fin/shendeti").json()
po(len(sh.get("problemet") or []) >= 2, "/shendeti i tregon", sh.get("problemet"))

print("\n3. PANELI NGRIHET DHE ALARMON")
p = kl.get("/api/fin/panel", headers=K)
po(p.status_code == 200, "paneli s'u rrezua", p.text[:250])
p = p.json()
titujt = [a["titulli"] for a in p["alarmet"]]
po(any("fin_veprimet" in t for t in titujt),
   "tabela qe mungon del si alarm", titujt)
po(any("nuk u regjistrua plotesisht" in t for t in titujt),
   "problemi i heshtur del si alarm", titujt)
detajet = " | ".join(a["veprimi"] + " " + a["detaji"] for a in p["alarmet"])
po("financat_migrim_7.sql" in detajet, "alarmi thote cfare te ekzekutosh")
po(p["levizjet"] and p["levizjet"][0]["ora"] is None,
   "levizja pa ore nuk shpik nje te tille", p["levizjet"][:1])
po(p.get("veprimet") == [], "ditari bosh, jo gabim", p.get("veprimet"))

print("\n4. /veprimet SHPJEGON VETEN")
v = kl.get("/api/fin/veprimet", headers=K)
po(v.status_code == 200, "endpoint-i pergjigjet", v.text[:200])
po("financat_migrim_7.sql" in (v.json().get("shenim") or ""),
   "thote si te ndreqet", v.json())

print(f"\n{'='*58}\nOK: {nr_ok}   DESHTIME: {nr_keq}\n{'='*58}")
sys.exit(1 if nr_keq else 0)
