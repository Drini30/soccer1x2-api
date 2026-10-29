"""Asistenti: urdhri me tekst duhet te kete te njejtin efekt si butoni."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from baza_prove import Baza
import financat
from fastapi import FastAPI
from fastapi.testclient import TestClient

baza = Baza(); financat._sb = baza.sb; financat.PROBLEMET.clear()
app = FastAPI(); app.include_router(financat.router)
kl = TestClient(app); K = {"X-Fin-Token": "token-prove"}

nr_ok = nr_keq = 0
def po(kusht, emri, detaj=""):
    global nr_ok, nr_keq
    if kusht: nr_ok += 1; print(f"  ✓ {emri}")
    else: nr_keq += 1; print(f"  ✗ {emri} — {detaj}")

def API(rruga, trupi=None, metoda="POST"):
    r = kl.request(metoda, "/api/fin" + rruga, headers=K, json=trupi)
    if r.status_code != 200:
        raise AssertionError(f"{rruga} → {r.status_code}: {r.text[:300]}")
    return r.json()

def panel():
    return kl.get("/api/fin/panel", headers=K).json()

def gjendja(emri):
    return {l["emri"]: l["bilanci"] for l in panel()["bilancet"]["llogarite"]}[emri]

def nr_trx():
    return len(kl.get("/api/fin/te-dhena/transaksionet?kufi=500", headers=K).json())

baza.te_dhenat["fin_cilesimet"] = [
    {"celes": "monedha_baze", "vlera": "ALL"},
    {"celes": "kurset", "vlera": {"ALL": 1.0, "EUR": 98.0}},
    {"celes": "zona_kohore", "vlera": "Europe/Tirane"},
    {"celes": "konfirmim_automatik", "vlera": False},
]
pers = API("/te-dhena/personat", {"emri": "Drini"})
banka = API("/te-dhena/llogarite", {"emri": "Ndricim Plaku", "lloji": "bank",
            "monedha": "ALL", "bilanci_fillestar": 180000, "personi_id": pers["id"]})
kesh = API("/te-dhena/llogarite", {"emri": "Kesh", "lloji": "cash",
           "monedha": "ALL", "bilanci_fillestar": 20000})
plani = API("/te-dhena/planet", {"emri": "Interneti", "drejtimi": "dalje",
            "shuma": 2500, "monedha": "ALL", "frekuenca": "mujore",
            "dita_pageses": 27, "data_fillimit": "2026-01-01",
            "probabiliteti": 100, "horizonti": "urgjent", "llogaria_id": kesh["id"]})
from datetime import date as _dt
# Dita e pageses lidhet me sot, qe prova te mos varet nga dita e kalendarit:
# "e lira" numeron vetem fikset qe bien PARA hyrjes se radhes.
API("/te-dhena/planet", {"emri": "Qiraja", "drejtimi": "dalje", "shuma": 35000,
    "monedha": "ALL", "frekuenca": "mujore", "dita_pageses": _dt.today().day,
    "data_fillimit": "2026-01-01", "probabiliteti": 100, "horizonti": "urgjent"})
rroga = API("/te-dhena/te-ardhurat", {"emri": "Rroga", "lloji": "page",
            "shuma_mujore": 95000, "monedha": "ALL", "dita_pageses": 5,
            "llogaria_id": banka["id"], "personi_id": pers["id"], "siguria": 5})
API("/te-dhena/detyrimet", {"lloji": "borxh", "pala": "Banka Kombetare",
    "shuma_totale": 400000, "shuma_paguar": 120000, "monedha": "ALL",
    "kesti_mujor": 18000, "afati": "2027-06-30"})

print("\n1. NJE URDHER NUK SHKRUAN ASGJE PA KONFIRMIM")
para_trx, para_gjendje = nr_trx(), gjendja("Kesh")
r = API("/urdher", {"teksti": "shto si te paguar internetin"})
po(r["kryer"] is False, "nuk u krye vetvetiu")
po(r.get("kerkon_konfirmim") is True, "kerkohet konfirmim", r)
po(r["propozimi"]["veprimi"] == "pagese_plani", "veprimi u kuptua",
   r["propozimi"]["veprimi"])
po(r["propozimi"]["burimi"]["id"] == plani["id"], "burimi i sakte",
   r["propozimi"].get("burimi"))
po("Interneti" in r["pergjigja"] and "2.500" in r["pergjigja"],
   f"permbledhja: {r['pergjigja']}")
po(nr_trx() == para_trx, "asnje transaksion i shkruar", (para_trx, nr_trx()))
po(gjendja("Kesh") == para_gjendje, "gjendja e paprekur")

print("\n2. KONFIRMIMI E KRYEN DHE PREK TOTALIN")
k = API("/konfirmo", {"mesazhi_id": r["mesazhi_id"]})
po(k["kryer"] is True, "u krye")
po(nr_trx() == para_trx + 1, "transaksioni u shkrua")
po(abs(gjendja("Kesh") - (para_gjendje - 2500)) < 0.01,
   f"Kesh zbriti 2.500 ({para_gjendje} → {gjendja('Kesh')})")
b = API("/mesazhet", metoda="GET")["biseda"]
i_konfirmuari = [m for m in b if m["id"] == r["mesazhi_id"]][0]
po(i_konfirmuari["statusi"] == "kryer", "mesazhi u mbyll si i kryer")
po(all(m["data"] and m["ora"] for m in b if m["lloji"] != "njoftim"),
   "cdo mesazh ka date dhe ore", [(m["data"], m["ora"]) for m in b[:3]])
v = kl.get("/api/fin/veprimet", headers=K).json()["veprimet"]
po(v[0]["veprimi"] == "pagese", "ditari e shenoi si pagese", v[0])

print("\n3. NJOFTIMI U ZHDUK SEPSE PAGESA U SHENUA")
# Krahasohet edhe lloji: plani #1 dhe burimi i te ardhurave #1 jane rreshta
# te ndryshem ne tabela te ndryshme, me te njejtin numer.
po(not any(n["veprimi"]["lloji"] == "plan" and n["veprimi"]["burimi_id"] == plani["id"]
           for n in panel()["njoftimet"]),
   "njoftimi i internetit iku", panel()["njoftimet"])

print("\n4. HYRJA ME NJE URDHER TE VETEM")
para_banke = gjendja("Ndricim Plaku")
r = API("/urdher", {"teksti": "shto rrogen te Ndricim Plaku 95000 lek",
                    "kryeje": True})
po(r["kryer"] is True, "u krye menjehere kur u kerkua")
po(abs(gjendja("Ndricim Plaku") - (para_banke + 95000)) < 0.01,
   f"banka u rrit 95.000 ({para_banke} → {gjendja('Ndricim Plaku')})")
po(r["propozimi"]["burimi"]["id"] == rroga["id"], "burimi = Rroga")

print("\n5. SHPENZIM I LIRE")
para_kesh = gjendja("Kesh")
r = API("/urdher", {"teksti": "shpenzova 1200 leke per ushqime dje",
                    "kryeje": True})
po(abs(gjendja("Kesh") - (para_kesh - 1200)) < 0.01, "Kesh zbriti 1.200")
t = kl.get("/api/fin/te-dhena/transaksionet?kufi=500", headers=K).json()
i_fundit = max(t, key=lambda x: x["id"])
po(i_fundit["kategoria"] == "ushqime", "kategoria u kuptua", i_fundit["kategoria"])
po(i_fundit["kryer_me"] is not None, "ruajti daten dhe oren", i_fundit["kryer_me"])

print("\n6. REZERVIMI ZBRET NGA 'E LIRA', JO NGA BILANCI")
p0 = panel()
lira0, likuid0 = p0["e_lira"]["e_lira"], p0["e_lira"]["likuiditeti"]
API("/urdher", {"teksti": "rezervo 50 mije per taksat", "kryeje": True})
p1 = panel()
po(abs(p1["e_lira"]["likuiditeti"] - likuid0) < 0.01,
   "likuiditeti s'ndryshoi", (likuid0, p1["e_lira"]["likuiditeti"]))
po(abs(p1["e_lira"]["e_lira"] - (lira0 - 50000)) < 0.01,
   f"e lira zbriti 50.000 ({lira0} → {p1['e_lira']['e_lira']})")
po(p1["e_lira"]["rezervat"] == 50000, "rezervat raportohen",
   p1["e_lira"]["rezervat"])
po(len(p1["rezervat"]) == 1 and p1["rezervat"][0]["emri"] == "Taksat",
   "rezerva ka emrin e arsyes", p1["rezervat"])

print("\n7. E LIRA MBLIDHET SIC E THOTE FORMULA")
el = p1["e_lira"]
pritej = (el["likuiditeti"] - el["rezervat"] - el["detyrimet"]
          - el["planet"] - el["buxheti_i_mbetur"])
po(abs(el["e_lira"] - pritej) < 0.01, "komponentet mbledhin totalin",
   (el["e_lira"], pritej))
po(el["planet"] > 0, "qiraja e papaguar numerohet", el["lista"]["planet"])
po(not any(x["emri"] == "Interneti" for x in el["lista"]["planet"]),
   "interneti i paguar NUK numerohet me", el["lista"]["planet"])

print("\n8. PYETJET NUK SHKRUAJNE ASGJE")
para = nr_trx()
r = API("/urdher", {"teksti": "sa kam?"})
po(r["kryer"] is False and nr_trx() == para, "asgje e shkruar")
po("te lira" in r["pergjigja"].lower(), f"pergjigja: {r['pergjigja'][:120]}")
r = API("/urdher", {"teksti": "cfare kam per te paguar"})
po("Qiraja" in r["pergjigja"], f"detyrimet: {r['pergjigja'][:120]}")

print("\n9. ANULIMI DHE KEQKUPTIMI")
# Pa llogari, pagesa e borxhit do te ishte nje dalje qe s'ikën nga askund.
r = API("/urdher", {"teksti": "paguaj borxhin e bankes 10000"})
po(r["kryer"] is False and "llogari" in r["pergjigja"].lower(),
   "pa llogari pyet per te", r["pergjigja"])
r = API("/urdher", {"teksti": "paguaj borxhin e bankes 10000 nga Ndricim Plaku"})
po(r.get("kerkon_konfirmim"), "borxhi kerkon konfirmim")
API("/anulo", {"mesazhi_id": r["mesazhi_id"]})
b = API("/mesazhet", metoda="GET")["biseda"]
po([m for m in b if m["id"] == r["mesazhi_id"]][0]["statusi"] == "anuluar",
   "u anulua")
gj = kl.get("/api/fin/te-dhena/detyrimet", headers=K).json()[0]
po(float(gj["shuma_paguar"]) == 120000, "borxhi i paprekur", gj["shuma_paguar"])
r = API("/urdher", {"teksti": "bla bla bla"})
po(r["propozimi"]["veprimi"] == "pa_kuptuar", "e pranon qe s'kuptoi")
po("Provo" in r["pergjigja"], "jep shembuj", r["pergjigja"][:80])

print("\n10. KONFIRMIMI I DYFISHTE REFUZOHET")
r = API("/urdher", {"teksti": "shpenzova 500 lek per kafe"})
API("/konfirmo", {"mesazhi_id": r["mesazhi_id"]})
dyte = kl.post("/api/fin/konfirmo", headers=K, json={"mesazhi_id": r["mesazhi_id"]})
po(dyte.status_code == 409, "nje propozim kryhet vetem nje here",
   dyte.status_code)

print(f"\n{'='*60}\nOK: {nr_ok}   DESHTIME: {nr_keq}\n{'='*60}")
sys.exit(1 if nr_keq else 0)
