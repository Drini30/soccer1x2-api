"""Portofoli: cdo gje qe shkruhet aty i zbritet ATIJ, dhe vetem atij."""
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

def xhepi(): return API("/portofoli", metoda="GET")["portofoli"]
def llogarite(): return {l["emri"]: l["bilanci"]
                         for l in API("/panel", metoda="GET")["bilancet"]["llogarite"]}

baza.te_dhenat["fin_cilesimet"] = [
    {"celes": "monedha_baze", "vlera": "ALL"},
    {"celes": "kurset", "vlera": {"ALL": 1.0, "EUR": 98.0}},
    {"celes": "zona_kohore", "vlera": "Europe/Tirane"},
    {"celes": "portofoli_prag", "vlera": 3000},
]
banka = API("/te-dhena/llogarite", {"emri": "Ndricim Plaku", "lloji": "bank",
            "monedha": "ALL", "bilanci_fillestar": 200000})
kesh = API("/te-dhena/llogarite", {"emri": "Kesh", "lloji": "cash",
           "monedha": "ALL", "bilanci_fillestar": 15000})

print("\n1. PORTOFOLI KRIJOHET VETE, BOSH")
x = xhepi()
po(x["ka"] is True and x["gjendja"] == 0, "gjendja fillon 0", x)
po(x["ngjyra"] == "e_kuqe", "bosh = i kuq", x["ngjyra"])
po(x["pragu"] == 3000, "pragu nga cilesimet", x["pragu"])
po(len(API("/portofoli", metoda="GET")["llogarite"]) == 2,
   "llogarite per rimbushje, pa portofolin vete")

print("\n2. RIMBUSHJA ZBRET NGA LLOGARIA E ZGJEDHUR")
para = llogarite()
r = API("/portofoli/rimbush", {"llogaria_id": banka["id"], "shuma": 20000})
po(r["portofoli"]["gjendja"] == 20000, "portofoli u mbush", r["portofoli"])
pas = llogarite()
po(abs(pas["Ndricim Plaku"] - (para["Ndricim Plaku"] - 20000)) < 0.01,
   f"banka zbriti 20.000 ({para['Ndricim Plaku']} → {pas['Ndricim Plaku']})")
po(pas["Kesh"] == para["Kesh"], "Kesh i paprekur")
po(r["portofoli"]["ngjyra"] == "jeshile", "mbi prag = jeshil")

print("\n3. SHPENZIMI ME FJALE ZBRET VETEM NGA PORTOFOLI")
para = llogarite()
r = API("/portofoli/urdher", {"teksti": "i hodha 5 mij lek benzin"})
po(r["kryer"] is True, "u krye menjehere, pa konfirmim")
po(r["portofoli"]["gjendja"] == 15000, "20.000 − 5.000 = 15.000",
   r["portofoli"]["gjendja"])
pas = llogarite()
po(pas["Ndricim Plaku"] == para["Ndricim Plaku"]
   and pas["Kesh"] == para["Kesh"],
   "asnje llogari tjeter nuk levizi", (para, pas))

print("\n4. ARSYEJA DHE SHUMA RUHEN PER RAPORT")
t = [x for x in kl.get("/api/fin/te-dhena/transaksionet?kufi=500",
                       headers=K).json() if x.get("kategoria") == "karburant"]
po(len(t) == 1, "nje transaksion i vetem")
po(float(t[0]["shuma"]) == 5000, "shuma e ruajtur", t[0]["shuma"])
po("benzin" in (t[0]["pershkrimi"] or ""), "arsyeja e ruajtur",
   t[0]["pershkrimi"])
po(t[0]["kryer_me"] is not None, "me date dhe ore", t[0]["kryer_me"])

print("\n5. NGJYRAT")
API("/portofoli/urdher", {"teksti": "12 mije lek ushqime"})
x = xhepi()
po(x["gjendja"] == 3000 and x["ngjyra"] == "portokalli",
   f"ne 3.000 behet portokalli ({x['gjendja']}, {x['ngjyra']})")
API("/portofoli/urdher", {"teksti": "2000 lek kafe"})
x = xhepi()
po(x["gjendja"] == 1000 and x["ngjyra"] == "portokalli",
   f"nen prag mbetet portokalli ({x['gjendja']})")

print("\n6. MINUSI LEJOHET DHE THUHET")
r = API("/portofoli/urdher", {"teksti": "dhashe 4000 lek per farmaci"})
po(r["portofoli"]["gjendja"] == -3000, "shkoi −3.000",
   r["portofoli"]["gjendja"])
po(r["portofoli"]["ngjyra"] == "e_kuqe", "minus = i kuq")
po("minus" in r["pergjigja"].lower(), "pergjigja e thote",
   r["pergjigja"])
po(xhepi()["gjendja"] == -3000, "minusi qendron")

print("\n7. BISEDA MBAN CDO GJE ME DATE DHE ORE")
b = API("/portofoli", metoda="GET")["biseda"]
po(len(b) >= 8, f"{len(b)} mesazhe ne bisede")
po(all(m["data"] and m["ora"] for m in b), "te gjitha me date dhe ore",
   [(m["data"], m["ora"]) for m in b[:2]])
kohet = [m["kur"] for m in b]
po(kohet == sorted(kohet), "renditur nga me i vjetri te me i riu")
po(any(m["kush"] == "une" and "benzin" in m["teksti"] for m in b),
   "teksti im origjinal eshte aty")

print("\n8. PYETJA NUK SHKRUAN ASGJE")
para_trx = len(kl.get("/api/fin/te-dhena/transaksionet?kufi=500", headers=K).json())
r = API("/portofoli/urdher", {"teksti": "sa kam?"})
po(r["kryer"] is False, "asnje levizje")
po(len(kl.get("/api/fin/te-dhena/transaksionet?kufi=500",
              headers=K).json()) == para_trx, "numri i transaksioneve i njejte")
po("-3.000" in r["pergjigja"] or "−3.000" in r["pergjigja"],
   f"pergjigja: {r['pergjigja']}")

print("\n9. ANULIMI E KTHEN MBRAPSHT")
r = API("/portofoli/urdher", {"teksti": "1500 lek taksi"})
po(xhepi()["gjendja"] == -4500, "u zbrit", xhepi()["gjendja"])
API("/portofoli/anulo", {"mesazhi_id": r["mesazhi_id"]})
po(xhepi()["gjendja"] == -3000, "u kthye", xhepi()["gjendja"])
dyte = kl.post("/api/fin/portofoli/anulo", headers=K,
               json={"mesazhi_id": r["mesazhi_id"]})
po(dyte.status_code == 409, "anulohet vetem nje here", dyte.status_code)
b = API("/portofoli", metoda="GET")["biseda"]
po(any(m["statusi"] == "anuluar" for m in b), "shenohet si e anuluar")

print("\n10. PORTOFOLI NUMEROHET NE LIKUIDITET DHE NE 'E LIRA'")
p = API("/panel", metoda="GET")
emrat = [l["emri"] for l in p["bilancet"]["llogarite"]]
po("Portofoli" in emrat, "del si llogari ne panel", emrat)
gj = {l["emri"]: l["bilanci"] for l in p["bilancet"]["llogarite"]}
po(gj["Portofoli"] == -3000, "me te njejten shifer si /portofoli", gj)

print("\n11. BISEDA E ASISTENTIT DHE AJO E PORTOFOLIT JANE TE NDARA")
API("/urdher", {"teksti": "sa kam?"})
bp = API("/portofoli", metoda="GET")["biseda"]
po(not any("llogarite likuide" in (m["teksti"] or "") for m in bp),
   "pergjigja e asistentit s'hyri ne portofol")
ba = API("/mesazhet", metoda="GET")["biseda"]
po(not any("benzin" in (m["teksti"] or "") for m in ba),
   "urdhrat e portofolit s'hyne te asistenti")

print(f"\n{'='*60}\nOK: {ok}   DESHTIME: {keq}\n{'='*60}")
sys.exit(1 if keq else 0)
