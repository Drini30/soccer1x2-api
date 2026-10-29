"""Provat e migrimit 7: cdo veprim ruan daten DHE oren."""
import sys, re
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from baza_prove import Baza, ZONA
from datetime import datetime

import financat
from fastapi import FastAPI
from fastapi.testclient import TestClient

baza = Baza()
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

def lokale(x):
    return datetime.fromisoformat(str(x)).astimezone(ZONA)

# ── Pergatitja ───────────────────────────────────────────────────────────
baza.te_dhenat["fin_cilesimet"] = [
    {"celes": "monedha_baze", "vlera": "ALL"},
    {"celes": "kurset", "vlera": {"ALL": 1.0, "EUR": 98.0}},
    {"celes": "zona_kohore", "vlera": "Europe/Tirane"},
]
llog = kl.post("/api/fin/te-dhena/llogarite", headers=K, json={
    "emri": "Ndricim Plaku", "lloji": "bank", "monedha": "ALL",
    "bilanci_fillestar": 100000}).json()
pers = kl.post("/api/fin/te-dhena/personat", headers=K,
               json={"emri": "Drini"}).json()

print("\n1. SHTIMI I NJE TRANSAKSIONI")
r = kl.post("/api/fin/te-dhena/transaksionet", headers=K, json={
    "data": "2026-09-20", "ora": "21:15", "lloji": "dalje", "shuma": 2500,
    "monedha": "ALL", "kategoria": "ushqime", "pershkrimi": "Supermarket",
    "llogaria_id": llog["id"], "personi_id": pers["id"]})
po(r.status_code == 200, "kerkesa kalon", r.text[:200])
t = r.json()
po(t.get("kryer_me") is not None, "u ruajt momenti i sakte", t)
po(lokale(t["kryer_me"]).strftime("%Y-%m-%d %H:%M") == "2026-09-20 21:15",
   "data dhe ora jane ato qe u shtypen", t.get("kryer_me"))
po(t["data"] == "2026-09-20", "data mbetet e njejte", t.get("data"))
po("ora" not in t, "'ora' s'shkon si kolone ne baze", list(t))

print("\n2. PA ORE TE DHENE → ORA E MOMENTIT")
t2 = kl.post("/api/fin/te-dhena/transaksionet", headers=K, json={
    "data": "2026-09-20", "lloji": "dalje", "shuma": 300, "monedha": "ALL",
    "llogaria_id": llog["id"]}).json()
po(t2.get("kryer_me") is not None, "prapeseprape ka ore", t2)
po(lokale(t2["kryer_me"]).date().isoformat() == "2026-09-20",
   "data e zgjedhur nuk zhvendoset", t2.get("kryer_me"))
tash = datetime.now(ZONA)
po(abs((lokale(t2["kryer_me"]).time().hour * 60
        + lokale(t2["kryer_me"]).time().minute)
       - (tash.hour * 60 + tash.minute)) <= 2,
   "ora eshte ajo e momentit te shkrimit", t2.get("kryer_me"))

print("\n3. NDRYSHIMI QE S'E PREK OREN NUK E ZHVENDOS ATE")
me_vone = kl.patch(f"/api/fin/te-dhena/transaksionet/{t['id']}", headers=K,
                   json={"shuma": 2600}).json()
po(me_vone["kryer_me"] == t["kryer_me"],
   "ora e pagese s'levizi kur u ndreq shuma", me_vone.get("kryer_me"))
po(float(me_vone["shuma"]) == 2600, "shuma u ndryshua", me_vone.get("shuma"))

print("\n4. NDRYSHIMI I ORES")
me_ore = kl.patch(f"/api/fin/te-dhena/transaksionet/{t['id']}", headers=K,
                  json={"data": "2026-09-20", "ora": "08:05"}).json()
po(lokale(me_ore["kryer_me"]).strftime("%H:%M") == "08:05",
   "ora e re u ruajt", me_ore.get("kryer_me"))
po(me_ore["data"] == "2026-09-20", "data mbeti", me_ore.get("data"))

print("\n5. NDRYSHIMI VETEM I DATES E MERR OREN ME VETE")
me_date = kl.patch(f"/api/fin/te-dhena/transaksionet/{t['id']}", headers=K,
                   json={"data": "2026-09-18"}).json()
po(me_date["data"] == "2026-09-18", "data e re", me_date.get("data"))
po(lokale(me_date["kryer_me"]).strftime("%Y-%m-%d %H:%M") == "2026-09-18 08:05",
   "ora 08:05 e ndoqi daten", me_date.get("kryer_me"))

print("\n6. PAGESA NGA NJOFTIMET")
ta = kl.post("/api/fin/te-dhena/te-ardhurat", headers=K, json={
    "emri": "Rroga", "lloji": "page", "shuma_mujore": 90000, "monedha": "ALL",
    "dita_pageses": 5, "llogaria_id": llog["id"], "personi_id": pers["id"]}).json()
r = kl.post("/api/fin/regjistro-pagese", headers=K, json={
    "lloji": "te_ardhura", "burimi_id": ta["id"], "shuma": 90000,
    "monedha": "ALL", "data": "2026-09-05", "ora": "10:42",
    "llogaria_id": llog["id"]})
po(r.status_code == 200, "pagesa kalon", r.text[:200])
p = r.json()["transaksioni"]
po(lokale(p["kryer_me"]).strftime("%Y-%m-%d %H:%M") == "2026-09-05 10:42",
   "momenti i hyrjes u ruajt", p.get("kryer_me"))
po(p["data"] == "2026-09-05", "data perputhet me momentin", p.get("data"))

print("\n7. PAGESA E NJE BORXHI")
det = kl.post("/api/fin/te-dhena/detyrimet", headers=K, json={
    "lloji": "borxh", "pala": "Banka", "shuma_totale": 10000, "monedha": "ALL",
    "afati": "2026-12-31"}).json()
r = kl.post("/api/fin/paguaj-borxh", headers=K, json={
    "detyrimi_id": det["id"], "shuma": 10000, "monedha": "ALL",
    "data": "2026-09-22", "ora": "16:30", "llogaria_id": llog["id"]})
po(r.status_code == 200, "shlyerja kalon", r.text[:200])
b = r.json()
po(lokale(b["transaksioni"]["kryer_me"]).strftime("%Y-%m-%d %H:%M")
   == "2026-09-22 16:30", "momenti i shlyerjes", b["transaksioni"].get("kryer_me"))
po(b["shlyer"] is True, "borxhi u mbyll", b)

print("\n8. DITARI I VEPRIMEVE")
v = kl.get("/api/fin/veprimet", headers=K).json()
lloj = [x["veprimi"] for x in v["veprimet"]]
po(v["gjithsej"] >= 9, f"u shenuan {v['gjithsej']} veprime", lloj)
po("shtim" in lloj and "ndryshim" in lloj, "shtimet dhe ndryshimet jane aty", lloj)
po("pagese" in lloj and "shlyerje" in lloj, "pagesat jane aty", lloj)
po(all(x["data"] and x["ora"] for x in v["veprimet"]),
   "cdo veprim ka date dhe ore", v["veprimet"][:2])
po(all(re.match(r"^\d{2}:\d{2}$", x["ora"]) for x in v["veprimet"]),
   "ora ne formatin HH:MM", [x["ora"] for x in v["veprimet"][:3]])
# radha: me i riu i pari
kohet = [x["kur"] for x in v["veprimet"]]
po(kohet == sorted(kohet, reverse=True), "me i fundit del i pari", kohet[:3])

print("\n9. FSHIRJA RUHET E PLOTE (E KTHYESHME)")
i_ri = kl.post("/api/fin/te-dhena/transaksionet", headers=K, json={
    "data": "2026-09-01", "ora": "12:00", "lloji": "dalje", "shuma": 111,
    "monedha": "ALL", "llogaria_id": llog["id"]}).json()
kl.delete(f"/api/fin/te-dhena/transaksionet/{i_ri['id']}", headers=K)
v = kl.get("/api/fin/veprimet", headers=K).json()["veprimet"]
fsh = [x for x in v if x["veprimi"] == "fshirje"]
po(len(fsh) == 1, "fshirja u shenua", len(fsh))
rresht = [r for r in baza.te_dhenat["fin_veprimet"]
          if r["veprimi"] == "fshirje"][0]
po(float(rresht["detaje"]["rreshti"]["shuma"]) == 111,
   "rreshti i fshire u ruajt i plote", rresht["detaje"])

print("\n10. PANELI: LEVIZJET ME ORE, RADHA BRENDA DITES")
p = kl.get("/api/fin/panel", headers=K)
po(p.status_code == 200, "paneli ndertohet", p.text[:300])
p = p.json()
po(all(l.get("ora") for l in p["levizjet"]), "cdo levizje ka ore",
   [(l["data"], l.get("ora")) for l in p["levizjet"][:3]])
po(p.get("zona_kohore") == "Europe/Tirane", "zona raportohet", p.get("zona_kohore"))
po(p.get("koha_lokale") and len(p["koha_lokale"]) == 16,
   "koha lokale ne panel", p.get("koha_lokale"))
po(len(p.get("veprimet") or []) >= 9, "ditari vjen me panelin",
   len(p.get("veprimet") or []))
celesat = [(l["data"], l["ora"]) for l in p["levizjet"]]
po(celesat == sorted(celesat, reverse=True),
   "levizjet renditen me date e me ore", celesat[:4])

print("\n11. BILANCI NUK U PREK NGA KOHA")
gj = {l["emri"]: l["bilanci"] for l in p["bilancet"]["llogarite"]}
# 100000 − 2600 (u ndryshua) − 300 + 90000 − 10000 = 177100
po(abs(gj["Ndricim Plaku"] - 177100) < 0.01,
   "gjendja e llogarise mbetet e sakte", gj)

print(f"\n{'='*58}\nOK: {nr_ok}   DESHTIME: {nr_keq}\n{'='*58}")
sys.exit(1 if nr_keq else 0)
