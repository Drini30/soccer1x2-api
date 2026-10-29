"""Nje rroge, nga cilado rruge, arrin ne cdo hallke — pa u numeruar dy here."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from datetime import date
from baza_prove import Baza
import financat
from fastapi import FastAPI
from fastapi.testclient import TestClient

ok = keq = 0
def po(k_, emri, detaj=""):
    global ok, keq
    if k_: ok += 1; print(f"  ✓ {emri}")
    else: keq += 1; print(f"  ✗ {emri} — {detaj}")

def nis():
    baza = Baza(); financat._sb = baza.sb; financat.PROBLEMET.clear()
    app = FastAPI(); app.include_router(financat.router)
    kl = TestClient(app); K = {"X-Fin-Token": "token-prove"}
    def API(r, t=None, m="POST", status=200):
        x = kl.request(m, "/api/fin" + r, headers=K, json=t)
        assert x.status_code == status, (r, x.status_code, x.text[:300])
        return x.json()
    baza.te_dhenat["fin_cilesimet"] = [
        {"celes": "monedha_baze", "vlera": "LEK"},
        {"celes": "kurset", "vlera": {"ALL": 1.0, "EUR": 98.0}},
        {"celes": "zona_kohore", "vlera": "Europe/Tirane"}]
    pers = API("/te-dhena/personat", {"emri": "Ndricim"})
    llog = API("/te-dhena/llogarite", {"emri": "NDRICIM PLAKU", "lloji": "bank",
               "monedha": "LEK", "bilanci_fillestar": 50000, "personi_id": pers["id"]})
    API("/te-dhena/objektivat", {"emri": "Fondi", "shuma_synim": 300000,
        "shuma_aktuale": 0, "monedha": "LEK", "afati": "2027-06-30", "prioriteti": 1})
    return API, llog, pers, baza

def incoming(API):
    return round(API("/panel", m="GET")["rrjedha_ditore"]["hyrje"]["mujore"])

def rroga(API, llog, pers, shuma=95000, dita=5):
    return API("/te-dhena/te-ardhurat", {"emri": "Rroga", "lloji": "page",
        "shuma_mujore": shuma, "monedha": "LEK", "dita_pageses": dita,
        "llogaria_id": llog["id"], "personi_id": pers["id"], "siguria": 5})

def hyrje(API, llog, shuma, kat="page", personi=None):
    t = {"data": date.today().isoformat(), "lloji": "hyrje", "shuma": shuma,
         "monedha": "LEK", "kategoria": kat, "pershkrimi": kat,
         "llogaria_id": llog["id"]}
    if personi: t["personi_id"] = personi
    return API("/te-dhena/transaksionet", t)

print("\n1. RROGA SI TRANSAKSION, PA BURIM: ARRIN KUDO")
API, llog, pers, _ = nis()
hyrje(API, llog, 95000)
p = API("/panel", m="GET")
po(p["bilancet"]["llogarite"][0]["bilanci"] == 145000, "llogaria")
po(round(p["rrjedha_ditore"]["hyrje"]["mujore"]) == 95000, "INCOMING",
   p["rrjedha_ditore"]["hyrje"])
po(round(p["kapaciteti"]["rrjedha_neto_mujore"]) == 95000, "rrjedha mujore",
   p["kapaciteti"]["rrjedha_neto_mujore"])
po(p["objektivat"][0]["plani"]["ne_dispozicion"] > 0, "objektivi merr kapacitet",
   p["objektivat"][0]["plani"])
po([x for x in p["personat"] if x["emri"] == "Ndricim"][0]["te_ardhura_mujore"] == 95000,
   "personi — edhe pa 'Kush e beri', nga pronari i llogarise", p["personat"])
po(any(z["emri"] == "Hyrje jashte burimeve" and z["mujore"] == 95000
       for z in p["rrjedha_ditore"]["zberthimi_i_hyrjes"]),
   "INCOMING e tregon nga vjen")

print("\n2. BURIMI I DEKLARUAR + RROGA SI TRANSAKSION: NJE HERE, JO DY")
API, llog, pers, _ = nis()
b = rroga(API, llog, pers)
t = hyrje(API, llog, 95000)
po(t.get("te_ardhura_id") == b["id"], "u lidh vete me burimin", t)
po(incoming(API) == 95000, "INCOMING 95.000, jo 190.000", incoming(API))
po(not any(n["veprimi"].get("burimi_id") == b["id"]
           for n in API("/njoftimet", m="GET")["njoftimet"]),
   "njoftimi 'konfirmo pagesen' u mbyll")

print("\n3. NJE DHURATE NE LLOGARINE E RROGES NUK BEHET RROGE")
API, llog, pers, _ = nis()
b = rroga(API, llog, pers)
t = hyrje(API, llog, 5000, kat="dhurate")
po(not t.get("te_ardhura_id"), "nuk u lidh (jashte ±50%)", t)
po(incoming(API) == 100000, "INCOMING 95.000 + 5.000", incoming(API))

print("\n4. NJE BONUS PASI RROGA ESHTE PAGUAR: SHTESE, JO RROGE")
API, llog, pers, _ = nis()
b = rroga(API, llog, pers)
API("/regjistro-pagese", {"lloji": "te_ardhura", "burimi_id": b["id"],
    "shuma": 95000, "monedha": "LEK", "llogaria_id": llog["id"]})
t = hyrje(API, llog, 90000, kat="bonus")
po(not t.get("te_ardhura_id"), "burimi ishte paguar — nuk lidhet perseri", t)
po(incoming(API) == 185000, "INCOMING 95.000 + 90.000", incoming(API))

print("\n5. DY BURIME NE TE NJEJTEN LLOGARI: NUK HAMENDESON")
API, llog, pers, _ = nis()
rroga(API, llog, pers)
API("/te-dhena/te-ardhurat", {"emri": "Qiraja e dyqanit", "lloji": "qira",
    "shuma_mujore": 90000, "monedha": "LEK", "dita_pageses": 10,
    "llogaria_id": llog["id"], "siguria": 4})
t = hyrje(API, llog, 92000)
po(not t.get("te_ardhura_id"), "dy kandidate → asnje lidhje", t)

print("\n6. BURIM ME SHUME TE NDRYSHUESHME: CDO SHUME LIDHET")
API, llog, pers, _ = nis()
b = API("/te-dhena/te-ardhurat", {"emri": "Freelance", "lloji": "freelance",
    "monedha": "LEK", "dita_pageses": 1, "shuma_e_ndryshueshme": True,
    "llogaria_id": llog["id"], "siguria": 3})
t = hyrje(API, llog, 37000, kat="freelance")
po(t.get("te_ardhura_id") == b["id"], "u lidh", t)

print("\n7. HYRJE PA LLOGARI: REFUZOHET ME ARSYE")
API, llog, pers, _ = nis()
r = API("/te-dhena/transaksionet", {"lloji": "hyrje", "shuma": 95000,
        "monedha": "LEK"}, status=400)
po("llogari" in r["detail"].lower(), "mesazhi thote cfare mungon", r)
API("/te-dhena/transaksionet", {"lloji": "dalje", "shuma": 500, "monedha": "LEK"},
    status=400)
po(True, "edhe dalja pa llogari refuzohet")

print("\n8. LEVIZJET E VJETRA PA LLOGARI DALIN SI ALARM")
API, llog, pers, baza = nis()
baza.rreshtat("fin_transaksionet").append({"id": 999, "user_id": "une",
    "data": date.today().isoformat(), "lloji": "hyrje", "shuma": 95000,
    "monedha": "LEK", "llogaria_id": None, "kryer_me": None})
al = [a["titulli"] for a in API("/panel", m="GET")["alarmet"]]
po(any("pa llogari" in a for a in al), "alarmi i numeron", al)
r = API("/te-dhena/transaksionet/999", {"shuma": 96000}, m="PATCH", status=400)
po(True, "ndryshimi pa i dhene llogari refuzohet")
API("/te-dhena/transaksionet/999", {"llogaria_id": llog["id"]}, m="PATCH")
po(API("/panel", m="GET")["bilancet"]["llogarite"][0]["bilanci"] == 145000,
   "me llogarine e shtuar, paraja del aty")

print("\n9. BURIM I SHTUAR PAS DITES SE PAGESES: NJOFTIMI DEL")
API, llog, pers, _ = nis()
b = rroga(API, llog, pers, dita=max(1, date.today().day - 1))
po(any(n["veprimi"].get("burimi_id") == b["id"]
       for n in API("/njoftimet", m="GET")["njoftimet"]),
   "pyet menjehere per pagesen e ketij muaji")

print("\n10. ASISTENTI: RROGA PA BURIM, ME LLOGARI")
API, llog, pers, _ = nis()
r = API("/urdher", {"teksti": "shto rrogen 95000 lek te NDRICIM PLAKU", "kryeje": True})
po(r["kryer"] is True, "u krye", r.get("pergjigja"))
po(incoming(API) == 95000, "INCOMING", incoming(API))
r = API("/urdher", {"teksti": "mora 20000 lek", "kryeje": True})
po(r["kryer"] is False and "llogari" in r["pergjigja"].lower(),
   "pa llogari → pyet, s'shkruan", r["pergjigja"])

print(f"\n{'='*60}\nOK: {ok}   DESHTIME: {keq}\n{'='*60}")
sys.exit(1 if keq else 0)
