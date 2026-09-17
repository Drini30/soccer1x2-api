"""
============================================================================
FINANCAT — moduli personal i kontrollit financiar
============================================================================
I ndare qellimisht nga soccer_api.py: ky eshte nje produkt tjeter qe thjesht
rri ne te njejtin proces (i njejti Render, i njejti Supabase, i njejti deploy).
soccer_api.py e merr vetem me `include_router` — asnje rresht i logjikes se
parashikimeve nuk preket.

Cfare ben:
  1. Mban regjistrin: llogari, transaksione, borxhe, arketime, plane,
     te ardhura, investime, objektiva.
  2. E llogarit vete gjendjen — balanca, likuiditet, rrjedhje parash,
     projeksion 12-mujor, skor sjelljeje, alarme, kapacitet perballues.
     Kjo pjese eshte DETERMINISTIKE: te njejtat te dhena japin gjithmone
     te njejtin numer. Asnje model gjuhesor nuk prek llogarite.
  3. Vetem MBI ate gjendje te llogaritur therret Claude (me kerkim ne
     internet) per gjerat qe kerkojne bote te jashtme: norma interesi,
     opsione investimi, cmime, alternativa rifinancimi.

Autentikimi: header `X-Fin-Token` == env FIN_TOKEN. Nese FIN_TOKEN s'eshte
vendosur, moduli ndalon cdo kerkese (fail-closed) — me mire i palexueshem
sesa i hapur.
============================================================================
"""

from fastapi import APIRouter, Header, HTTPException, Query, Body
from fastapi.responses import HTMLResponse
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional
import calendar
import hmac
import json
import os
import statistics

import requests

router = APIRouter(prefix="/api/fin", tags=["Financat"])

# ==========================================================================
# KONFIGURIMI
# ==========================================================================
SUPABASE_BASE = os.environ.get(
    "SUPABASE_URL", "https://oqfhlyybwwkjbkvfpsxi.supabase.co"
).rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
FIN_TOKEN = os.environ.get("FIN_TOKEN", "").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
FIN_MODELI = os.environ.get("FIN_MODELI", "claude-opus-5").strip()
# Nje perdorues i vetem per tani. Skema e mban kolonen user_id qe kalimi ne
# shume perdorues te jete ndryshim auth-i, jo migrim te dhenash.
USER_ID = os.environ.get("FIN_USER_ID", "une").strip() or "une"

TABELAT = {
    "llogarite":     "fin_llogarite",
    "transaksionet": "fin_transaksionet",
    "detyrimet":     "fin_detyrimet",
    "planet":        "fin_planet",
    "te-ardhurat":   "fin_te_ardhurat",
    "investimet":    "fin_investimet",
    "objektivat":    "fin_objektivat",
    "raportet":      "fin_raportet",
}

# Fushat qe lejohen te shkruhen nga jashte. Cdo gje tjeter ne trup shperfillet
# ne heshtje — nuk duam qe nje POST te vendose id, user_id apo krijuar_me.
FUSHAT = {
    "llogarite": {"emri", "lloji", "monedha", "bilanci_fillestar", "limiti",
                  "likuide", "aktiv", "shenime"},
    "transaksionet": {"data", "llogaria_id", "lloji", "shuma", "monedha",
                      "kategoria", "pershkrimi", "detyrimi_id", "plani_id",
                      "te_ardhura_id", "llogaria_dest_id", "etiketa"},
    "detyrimet": {"lloji", "pala", "pershkrimi", "shuma_totale", "shuma_paguar",
                  "monedha", "interesi_vjetor", "kesti_mujor", "afati",
                  "prioriteti", "statusi", "siguria"},
    "planet": {"emri", "drejtimi", "shuma", "monedha", "kategoria", "frekuenca",
               "data_fillimit", "data_mbarimit", "horizonti", "domosdoshmeria",
               "probabiliteti", "aktiv", "shenime", "dita_pageses",
               "dita_pageses_fund", "muaji_pageses", "llogaria_id"},
    "te-ardhurat": {"emri", "lloji", "shuma_mujore", "monedha", "siguria",
                    "oret_mujore", "aktiv", "dita_pageses",
                    "shuma_e_ndryshueshme", "llogaria_id"},
    "investimet": {"emri", "lloji", "simboli", "sasia", "cmimi_blerje",
                   "cmimi_aktual", "monedha", "data_blerje", "rreziku",
                   "kthimi_pritshem", "aktiv", "shenime", "perditesuar_me"},
    "objektivat": {"emri", "shuma_synim", "shuma_aktuale", "monedha", "afati",
                   "prioriteti", "lloji", "arritur"},
    "raportet": set(),   # vetem lexim; shkruhet nga keshilltari
}

CILESIMET_PARAZGJEDHUR = {
    "monedha_baze": "EUR",
    "kurset": {"EUR": 1.0, "ALL": 0.0102, "USD": 0.92, "GBP": 1.17, "CHF": 1.05},
    "rezerva_muaj": 3,
    "synimi_kursimit": 20,
    "paralajmerim_dite": 14,
}

# 'LEK' eshte emri i perditshem i monedhes qe standardi e quan 'ALL'. Kush e
# shkruan LEK-un nuk duhet te dale me nje kolone te panjohur qe numerohet 1:1
# me euron. Kanonizimi behet vetem per kerkimin e kursit — teksti qe shkruan
# perdoruesi ruhet dhe shfaqet ashtu si eshte.
SINONIMET_E_MONEDHAVE = {
    "LEK": "ALL", "LEKE": "ALL", "LEKË": "ALL", "L": "ALL",
    "EURO": "EUR", "€": "EUR", "$": "USD", "USD$": "USD", "DOLLAR": "USD",
}


def monedha_kanonike(m: Optional[str]) -> str:
    e = (m or "").strip().upper()
    return SINONIMET_E_MONEDHAVE.get(e, e)


# Sa here ne muaj ndodh nje frekuence.
HERE_NE_MUAJ = {
    "nje_here": 0.0, "ditore": 365 / 12, "javore": 52 / 12, "dyjavore": 26 / 12,
    "mujore": 1.0, "tremujore": 1 / 3, "vjetore": 1 / 12,
}


# ==========================================================================
# SUPABASE — nje helper i vetem
# ==========================================================================
def _koka() -> Dict[str, str]:
    if not SUPABASE_SERVICE_KEY:
        raise HTTPException(503, "SUPABASE_SERVICE_KEY mungon ne mjedis.")
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _sb(tabela: str, metoda: str = "get", params: Optional[dict] = None,
        trupi: Any = None, prefer: Optional[str] = None) -> Any:
    """Thirrje e vetme ndaj PostgREST. Kthen JSON ose ngre HTTPException."""
    url = f"{SUPABASE_BASE}/rest/v1/{tabela}"
    koka = _koka()
    if prefer:
        koka["Prefer"] = prefer
    try:
        r = requests.request(metoda.upper(), url, headers=koka,
                             params=params, json=trupi, timeout=20)
    except requests.RequestException as e:
        raise HTTPException(503, f"Supabase i paarritshem: {e}")
    if r.status_code >= 400:
        raise HTTPException(r.status_code,
                            f"Supabase ({tabela}): {r.text[:300]}")
    if not r.text.strip():
        return []
    try:
        return r.json()
    except ValueError:
        return []


def _lexo(tabela: str, filtra: Optional[dict] = None,
          rendit: Optional[str] = None, kufi: Optional[int] = None) -> List[dict]:
    p = {"select": "*", "user_id": f"eq.{USER_ID}"}
    if filtra:
        p.update(filtra)
    if rendit:
        p["order"] = rendit
    if kufi:
        p["limit"] = str(kufi)
    dalja = _sb(tabela, "get", params=p)
    return dalja if isinstance(dalja, list) else []


# ==========================================================================
# AUTENTIKIMI
# ==========================================================================
def kerko_token(x_fin_token: Optional[str] = Header(None)) -> None:
    """Fail-closed: pa FIN_TOKEN te vendosur, moduli eshte i mbyllur fare."""
    if not FIN_TOKEN:
        raise HTTPException(503, "FIN_TOKEN nuk eshte vendosur — moduli i mbyllur.")
    if not x_fin_token or not hmac.compare_digest(x_fin_token.strip(), FIN_TOKEN):
        raise HTTPException(401, "Token i pavlefshem (header X-Fin-Token).")


# ==========================================================================
# NDIHMESA TE VOGLA
# ==========================================================================
def _num(x: Any, parazgjedhur: float = 0.0) -> float:
    try:
        if x is None:
            return parazgjedhur
        return float(x)
    except (TypeError, ValueError):
        return parazgjedhur


def _dat(x: Any) -> Optional[date]:
    if not x:
        return None
    if isinstance(x, date):
        return x
    try:
        return datetime.fromisoformat(str(x)[:10]).date()
    except ValueError:
        return None


def _shto_muaj(d: date, n: int) -> date:
    """Shton n muaj duke shmangur 31 shkurt: kap diten e fundit te muajit."""
    muaji = d.month - 1 + n
    viti = d.year + muaji // 12
    muaji = muaji % 12 + 1
    dita = min(d.day, calendar.monthrange(viti, muaji)[1])
    return date(viti, muaji, dita)


def _rrum(x: float, shifra: int = 2) -> float:
    return round(x + 0.0, shifra)


def lexo_cilesimet() -> Dict[str, Any]:
    """Cilesimet nga baza, me rikthim te plote te parazgjedhjeve qe mungojne."""
    c = dict(CILESIMET_PARAZGJEDHUR)
    try:
        rreshtat = _sb("fin_cilesimet", "get", params={"select": "celes,vlera"})
        for rr in rreshtat or []:
            if rr.get("celes"):
                c[rr["celes"]] = rr.get("vlera")
    except HTTPException:
        pass   # pa baze → punojme me parazgjedhjet
    kurset = c.get("kurset") or {}
    if not isinstance(kurset, dict) or not kurset:
        kurset = dict(CILESIMET_PARAZGJEDHUR["kurset"])
    # Monedha baze ruhet ashtu si e shkroi perdoruesi (LEK mbetet LEK ne ekran),
    # por kurset indeksohen me kodin kanonik.
    c["monedha_baze"] = str(c.get("monedha_baze") or "EUR").strip().upper()
    c["kurset"] = {monedha_kanonike(k): _num(v, 0.0) for k, v in kurset.items()}
    c["kurset"][monedha_kanonike(c["monedha_baze"])] = 1.0   # 1 ndaj vetes
    return c


def kthe(shuma: Any, monedha: Optional[str], cilesimet: Dict[str, Any]) -> float:
    """Konverton ne monedhen baze. Monedhe e panjohur → trajtohet 1:1 dhe
    raportohet ne alarme, jo e fshire ne heshtje."""
    return _num(shuma) * kursi_i(cilesimet, monedha)


def kursi_i(cilesimet: Dict[str, Any], monedha: Optional[str]) -> float:
    """Sa njesi te monedhes baze ben 1 njesi e kesaj monedhe."""
    m = monedha_kanonike(monedha) or monedha_kanonike(cilesimet.get("monedha_baze"))
    kursi = cilesimet["kurset"].get(m)
    return kursi if (kursi and kursi > 0) else 1.0


# ==========================================================================
# MOTORI — llogaritjet deterministike
# ==========================================================================
def mbledh_gjendjen() -> Dict[str, Any]:
    """Nje foto e plote e te dhenave te papërpunuara."""
    return {
        "llogarite":     _lexo("fin_llogarite", {"aktiv": "eq.true"}, "id.asc"),
        "transaksionet": _lexo("fin_transaksionet", None, "data.desc", 2000),
        "detyrimet":     _lexo("fin_detyrimet", None, "afati.asc"),
        "planet":        _lexo("fin_planet", {"aktiv": "eq.true"}, "data_fillimit.asc"),
        "te_ardhurat":   _lexo("fin_te_ardhurat", {"aktiv": "eq.true"}, "id.asc"),
        "investimet":    _lexo("fin_investimet", {"aktiv": "eq.true"}, "id.asc"),
        "objektivat":    _lexo("fin_objektivat", None, "afati.asc"),
    }


def vleresoj_te_ardhurat(g: Dict[str, Any], c: Dict[str, Any]) -> Dict[int, dict]:
    """Sa sjell çdo burim ne muaj, ne monedhen baze.

    Nje e ardhur freelance s'ka shume fikse — kolona lihet bosh me qellim.
    Ne ate rast shifra nxirret nga pagesat e vertetuara te atij burimi
    (mesatarja e muajve me pagese, brenda 6 muajve te fundit). Keshtu
    projeksioni nuk e trajton nje burim te vertete si zero, dhe as nuk
    hamendeson nje shume qe s'ka ndodhur kurre.
    """
    sot = date.today()
    sipas_burimit: Dict[int, Dict[str, float]] = {}
    for t in g["transaksionet"]:
        bid = t.get("te_ardhura_id")
        if bid is None:
            continue
        d = _dat(t.get("data"))
        if not d or (sot - d).days > 190 or d > sot:
            continue
        try:
            bid = int(bid)
        except (TypeError, ValueError):
            continue
        muaji = f"{d.year:04d}-{d.month:02d}"
        sipas_burimit.setdefault(bid, {})
        sipas_burimit[bid][muaji] = (sipas_burimit[bid].get(muaji, 0.0)
                                     + kthe(t.get("shuma"), t.get("monedha"), c))

    dalja: Dict[int, dict] = {}
    for a in g["te_ardhurat"]:
        try:
            aid = int(a.get("id"))
        except (TypeError, ValueError):
            continue
        deklaruar = a.get("shuma_mujore")
        if deklaruar is not None and _num(deklaruar) > 0:
            dalja[aid] = {
                "mujore_baze": kthe(deklaruar, a.get("monedha"), c),
                "burimi": "deklaruar", "pagesa": 0,
                "shpjegim": "shuma e deklaruar",
            }
            continue
        muajt = sipas_burimit.get(aid, {})
        if muajt:
            mesatarja = statistics.fmean(muajt.values())
            dalja[aid] = {
                "mujore_baze": mesatarja, "burimi": "historik",
                "pagesa": len(muajt),
                "shpjegim": f"mesatarja e {len(muajt)} pagesave te fundit",
            }
        else:
            dalja[aid] = {"mujore_baze": 0.0, "burimi": "pa_te_dhena",
                          "pagesa": 0,
                          "shpjegim": "pa shume te deklaruar dhe pa pagesa te shenuara"}
    return dalja


def llogarit_bilancet(g: Dict[str, Any], c: Dict[str, Any]) -> Dict[str, Any]:
    """Balanca per llogari + totalet ne monedhen baze."""
    bazat = {int(l["id"]): _num(l.get("bilanci_fillestar")) for l in g["llogarite"]}
    monedhat = {int(l["id"]): (l.get("monedha") or c["monedha_baze"]).upper()
                for l in g["llogarite"]}
    levizja = {i: 0.0 for i in bazat}

    for t in g["transaksionet"]:
        lid = t.get("llogaria_id")
        shuma = _num(t.get("shuma"))
        mon = (t.get("monedha") or c["monedha_baze"]).upper()
        lloji = (t.get("lloji") or "dalje").lower()
        if lid is not None and int(lid) in levizja:
            lid = int(lid)
            # Transaksioni mund te jete ne monedhe tjeter nga llogaria:
            # kalo ne baze, pastaj ne monedhen e llogarise.
            kursi_ll = kursi_i(c, monedhat[lid])
            ne_llogari = kthe(shuma, mon, c) / kursi_ll
            if lloji == "hyrje":
                levizja[lid] += ne_llogari
            else:                       # dalje dhe transfer largohen nga burimi
                levizja[lid] -= ne_llogari
        if lloji == "transfer":
            dest = t.get("llogaria_dest_id")
            if dest is not None and int(dest) in levizja:
                dest = int(dest)
                kursi_d = kursi_i(c, monedhat[dest])
                levizja[dest] += kthe(shuma, mon, c) / kursi_d

    rreshtat, likuiditet, total = [], 0.0, 0.0
    for l in g["llogarite"]:
        lid = int(l["id"])
        bilanci = bazat[lid] + levizja[lid]
        ne_baze = kthe(bilanci, monedhat[lid], c)
        rreshtat.append({
            "id": lid, "emri": l.get("emri"), "lloji": l.get("lloji"),
            "monedha": monedhat[lid], "bilanci": _rrum(bilanci),
            "bilanci_baze": _rrum(ne_baze), "likuide": bool(l.get("likuide", True)),
        })
        total += ne_baze
        if l.get("likuide", True) and (l.get("lloji") or "") != "kartekredit":
            likuiditet += ne_baze

    return {"llogarite": rreshtat, "total_baze": _rrum(total),
            "likuiditet": _rrum(likuiditet)}


def llogarit_rrjedhen(g: Dict[str, Any], c: Dict[str, Any]) -> Dict[str, Any]:
    """Hyrje/dalje mujore nga historiku real i transaksioneve.

    'Baza' = daljet qe NUK jane te lidhura me nje plan ose me nje detyrim.
    Ato te lidhurat modelohen vecmas ne projeksion, keshtu shmanget numerimi
    i dyfishte i te njejtes pagese.
    """
    sot = date.today()
    kova: Dict[str, Dict[str, float]] = {}
    for t in g["transaksionet"]:
        d = _dat(t.get("data"))
        if not d or d > sot or (sot - d).days > 400:
            continue
        lloji = (t.get("lloji") or "dalje").lower()
        if lloji == "transfer":
            continue
        celes = f"{d.year:04d}-{d.month:02d}"
        k = kova.setdefault(celes, {"hyrje": 0.0, "dalje": 0.0, "dalje_baze": 0.0})
        vlera = kthe(t.get("shuma"), t.get("monedha"), c)
        if lloji == "hyrje":
            k["hyrje"] += vlera
        else:
            k["dalje"] += vlera
            if not t.get("plani_id") and not t.get("detyrimi_id"):
                k["dalje_baze"] += vlera

    muajt = sorted(kova.keys())
    # Muaji rrjedhes eshte i paplote — nuk hyn ne mesatare.
    i_plote = [m for m in muajt if m != f"{sot.year:04d}-{sot.month:02d}"]
    fundit = i_plote[-6:]

    def _mes(fusha: str) -> float:
        vlerat = [kova[m][fusha] for m in fundit]
        return statistics.fmean(vlerat) if vlerat else 0.0

    daljet = [kova[m]["dalje"] for m in fundit]
    paqendrueshmeria = 0.0
    if len(daljet) >= 3 and statistics.fmean(daljet) > 0:
        paqendrueshmeria = statistics.pstdev(daljet) / statistics.fmean(daljet)

    vleresimet = vleresoj_te_ardhurat(g, c)
    te_ardhurat_deklaruara = sum(v["mujore_baze"] for v in vleresimet.values())
    hyrje_historike = _mes("hyrje")

    # Planet e perseritshme, te kthyera ne kosto mujore ekuivalente.
    plane_dalje = plane_hyrje = 0.0
    for p in g["planet"]:
        frek = (p.get("frekuenca") or "mujore").lower()
        if frek == "nje_here":
            continue                       # nuk eshte barre e perhershme mujore
        mbarimi = _dat(p.get("data_mbarimit"))
        if mbarimi and mbarimi < sot:
            continue
        mujore = (kthe(p.get("shuma"), p.get("monedha"), c)
                  * HERE_NE_MUAJ.get(frek, 1.0)
                  * min(max(_num(p.get("probabiliteti"), 100), 0.0), 100.0) / 100.0)
        if (p.get("drejtimi") or "dalje") == "hyrje":
            plane_hyrje += mujore
        else:
            plane_dalje += mujore

    dalje_baze = _mes("dalje_baze")
    dalje_mes = _mes("dalje")
    te_ardhura_baze = te_ardhurat_deklaruara or hyrje_historike

    return {
        "muajt": [{"muaji": m, **{k: _rrum(v) for k, v in kova[m].items()}}
                  for m in muajt[-12:]],
        "hyrje_mesatare": _rrum(hyrje_historike),
        "dalje_mesatare": _rrum(dalje_mes),
        "dalje_baze_mujore": _rrum(dalje_baze),
        "plane_dalje_mujore": _rrum(plane_dalje),
        "plane_hyrje_mujore": _rrum(plane_hyrje),
        # Shpenzimi i pritshem = baza (pa planet e pa kestet) + planet e
        # perseritshme + kestet. Nese s'ka ende asnje te dhene, bie te
        # mesatarja historike qe te mos dale zero artificiale.
        "shpenzim_pa_keste": _rrum((dalje_baze + plane_dalje) or dalje_mes),
        "te_ardhura_totale": _rrum(te_ardhura_baze + plane_hyrje),
        "te_ardhura_deklaruara": _rrum(te_ardhurat_deklaruara),
        # Burimi i te ardhurave: deklarimi yt ka perparesi; nese s'ke deklaruar
        # asnje burim, bie te mesatarja e hyrjeve reale.
        "te_ardhura_mujore": _rrum(te_ardhurat_deklaruara or hyrje_historike),
        "paqendrueshmeria": _rrum(paqendrueshmeria, 3),
        "muaj_te_plote": len(i_plote),
    }


def permbledh_detyrimet(g: Dict[str, Any], c: Dict[str, Any]) -> Dict[str, Any]:
    sot = date.today()
    borxhe, arketime = [], []
    for d in g["detyrimet"]:
        if (d.get("statusi") or "aktiv") == "shlyer":
            continue
        mbetur = _num(d.get("shuma_totale")) - _num(d.get("shuma_paguar"))
        if mbetur <= 0.005:
            continue
        afati = _dat(d.get("afati"))
        rr = {
            "id": d.get("id"), "pala": d.get("pala"),
            "pershkrimi": d.get("pershkrimi"),
            "mbetur": _rrum(mbetur),
            "mbetur_baze": _rrum(kthe(mbetur, d.get("monedha"), c)),
            "monedha": (d.get("monedha") or c["monedha_baze"]).upper(),
            "interesi_vjetor": _num(d.get("interesi_vjetor")),
            "kesti_mujor_baze": _rrum(kthe(d.get("kesti_mujor"), d.get("monedha"), c)),
            "afati": afati.isoformat() if afati else None,
            "dite_mbetur": (afati - sot).days if afati else None,
            "vonuar": bool(afati and afati < sot),
            "prioriteti": int(_num(d.get("prioriteti"), 3)),
            "siguria": int(_num(d.get("siguria"), 100)),
        }
        (borxhe if (d.get("lloji") or "borxh") == "borxh" else arketime).append(rr)

    total_borxh = sum(b["mbetur_baze"] for b in borxhe)
    kestet = sum(b["kesti_mujor_baze"] for b in borxhe)
    # Arketimet peshohen me sigurine — 1000 € nga nje klient qe paguan 50%
    # te rasteve nuk jane 1000 € pasuri.
    pritur_bruto = sum(a["mbetur_baze"] for a in arketime)
    pritur_neto = sum(a["mbetur_baze"] * a["siguria"] / 100.0 for a in arketime)

    return {
        "borxhe": sorted(borxhe, key=lambda x: (-x["interesi_vjetor"], x["mbetur_baze"])),
        "arketime": sorted(arketime, key=lambda x: (x["afati"] or "9999")),
        "total_borxh": _rrum(total_borxh),
        "kestet_mujore": _rrum(kestet),
        "arketime_bruto": _rrum(pritur_bruto),
        "arketime_neto": _rrum(pritur_neto),
        "vonuar_borxh": _rrum(sum(b["mbetur_baze"] for b in borxhe if b["vonuar"])),
        "vonuar_arketim": _rrum(sum(a["mbetur_baze"] for a in arketime if a["vonuar"])),
    }


def vlereso_investimet(g: Dict[str, Any], c: Dict[str, Any]) -> Dict[str, Any]:
    rreshtat, vlera, kostoja = [], 0.0, 0.0
    sipas_llojit: Dict[str, float] = {}
    for i in g["investimet"]:
        sasia = _num(i.get("sasia"))
        blerje = _num(i.get("cmimi_blerje"))
        aktual = _num(i.get("cmimi_aktual")) or blerje
        v = kthe(sasia * aktual, i.get("monedha"), c)
        k = kthe(sasia * blerje, i.get("monedha"), c)
        vlera += v
        kostoja += k
        lloji = i.get("lloji") or "tjeter"
        sipas_llojit[lloji] = sipas_llojit.get(lloji, 0.0) + v
        rreshtat.append({
            "id": i.get("id"), "emri": i.get("emri"), "lloji": lloji,
            "simboli": i.get("simboli"), "sasia": sasia,
            "vlera_baze": _rrum(v), "kostoja_baze": _rrum(k),
            "fitimi_baze": _rrum(v - k),
            "fitimi_perqind": _rrum((v / k - 1) * 100, 1) if k > 0 else 0.0,
            "rreziku": int(_num(i.get("rreziku"), 3)),
            "kthimi_pritshem": _num(i.get("kthimi_pritshem")),
            "perditesuar_me": i.get("perditesuar_me"),
        })
    perqendrimi = (max(sipas_llojit.values()) / vlera * 100) if vlera > 0 else 0.0
    rrezik_mes = 0.0
    if vlera > 0:
        rrezik_mes = sum(r["vlera_baze"] * r["rreziku"] for r in rreshtat) / vlera
    return {
        "investimet": sorted(rreshtat, key=lambda x: -x["vlera_baze"]),
        "vlera_baze": _rrum(vlera), "kostoja_baze": _rrum(kostoja),
        "fitimi_baze": _rrum(vlera - kostoja),
        "sipas_llojit": {k: _rrum(v) for k, v in sipas_llojit.items()},
        "perqendrimi_max": _rrum(perqendrimi, 1),
        "rreziku_mesatar": _rrum(rrezik_mes, 2),
    }


def _plani_ne_dritare(p: dict, nga: date, deri: date, c: Dict[str, Any]) -> float:
    """Sa kushton nje plan brenda nje dritareje [nga, deri)."""
    fillimi = _dat(p.get("data_fillimit")) or nga
    mbarimi = _dat(p.get("data_mbarimit"))
    if fillimi >= deri:
        return 0.0
    if mbarimi and mbarimi < nga:
        return 0.0
    shuma = kthe(p.get("shuma"), p.get("monedha"), c)
    prob = min(max(_num(p.get("probabiliteti"), 100), 0.0), 100.0) / 100.0
    frek = (p.get("frekuenca") or "mujore").lower()
    if frek == "nje_here":
        return shuma * prob if nga <= fillimi < deri else 0.0
    return shuma * HERE_NE_MUAJ.get(frek, 1.0) * prob


def projekto(g: Dict[str, Any], c: Dict[str, Any], bil: Dict[str, Any],
             rrj: Dict[str, Any], det: Dict[str, Any], muaj: int = 12) -> Dict[str, Any]:
    """Simulim muaj-pas-muaji i bilancit likuid.

    Borxhet amortizohen realisht: interesi mujor mbi mbetjen, pastaj kesti.
    Nje borxh pa kest fiks por me afat shlyhet i teri ne muajin e afatit.
    """
    sot = date.today()
    bilanci = bil["likuiditet"]
    mbetjet = {b["id"]: b["mbetur_baze"] for b in det["borxhe"]}
    arketime_marra: set = set()
    rreshtat: List[dict] = []
    muaji_negativ = None
    pikoja = bilanci

    for i in range(1, muaj + 1):
        nga, deri = _shto_muaj(sot, i - 1), _shto_muaj(sot, i)

        hyrje = rrj["te_ardhura_mujore"]
        dalje = rrj["dalje_baze_mujore"]
        for p in g["planet"]:
            v = _plani_ne_dritare(p, nga, deri, c)
            if (p.get("drejtimi") or "dalje") == "hyrje":
                hyrje += v
            else:
                dalje += v

        for a in det["arketime"]:
            af = _dat(a["afati"])
            # af < deri kap edhe ato qe e kane kaluar afatin: priten ne
            # muajin e pare, jo ne asnje muaj.
            if af and af < deri and a["id"] not in arketime_marra:
                arketime_marra.add(a["id"])
                hyrje += a["mbetur_baze"] * a["siguria"] / 100.0

        pagesa_borxhi = 0.0
        for b in det["borxhe"]:
            mbetur = mbetjet.get(b["id"], 0.0)
            if mbetur <= 0.005:
                continue
            mbetur += mbetur * (b["interesi_vjetor"] / 100.0) / 12.0
            af = _dat(b["afati"])
            if b["kesti_mujor_baze"] > 0:
                pagese = min(b["kesti_mujor_baze"], mbetur)
            elif af and af < deri:      # perfshin edhe afatet e skaduara
                pagese = mbetur
            else:
                pagese = 0.0
            mbetjet[b["id"]] = mbetur - pagese
            pagesa_borxhi += pagese

        neto = hyrje - dalje - pagesa_borxhi
        bilanci += neto
        pikoja = min(pikoja, bilanci)
        if bilanci < 0 and muaji_negativ is None:
            muaji_negativ = i
        rreshtat.append({
            "muaji": i, "nga": nga.isoformat(), "deri": deri.isoformat(),
            "etiketa": f"{deri.year:04d}-{deri.month:02d}",
            "hyrje": _rrum(hyrje), "dalje": _rrum(dalje),
            "kestet": _rrum(pagesa_borxhi), "neto": _rrum(neto),
            "bilanci": _rrum(bilanci),
        })

    return {
        "muajt": rreshtat,
        "bilanci_fundor": _rrum(bilanci),
        "pika_me_e_ulet": _rrum(pikoja),
        "muaji_i_pare_negativ": muaji_negativ,
        "borxhi_i_mbetur": _rrum(sum(mbetjet.values())),
    }


def _kufizo(x: float, ulet: float = 0.0, larte: float = 1.0) -> float:
    return max(ulet, min(larte, x))


def skor_sjelljeje(c: Dict[str, Any], bil: Dict[str, Any], rrj: Dict[str, Any],
                   det: Dict[str, Any], inv: Dict[str, Any],
                   g: Dict[str, Any]) -> Dict[str, Any]:
    """Skor 0-100 i sjelljes financiare, i zberthyer ne 6 perberes.

    Cdo perberes ka nje formule te dukshme — nese skori bie, e sheh saktesisht
    ku ra dhe sa pikë kushton secila sjellje.
    """
    te_ardhura = rrj["te_ardhura_totale"]
    shpenzim_mujor = rrj["shpenzim_pa_keste"] + det["kestet_mujore"]
    perberesit = []

    # 1) Norma e kursimit (25 pike) — sa nga cdo euro qe hyn, mbetet.
    norma = ((te_ardhura - shpenzim_mujor) / te_ardhura) if te_ardhura > 0 else 0.0
    synimi = _num(c.get("synimi_kursimit"), 20) / 100.0 or 0.2
    p1 = 25 * _kufizo(norma / synimi)
    perberesit.append({
        "emri": "Norma e kursimit", "pike": _rrum(p1, 1), "maks": 25,
        "vlera": f"{norma * 100:.1f}%", "synimi": f"{synimi * 100:.0f}%",
        "shpjegim": "Sa perqind e te ardhurave te mbetet pasi paguan gjithcka."
    })

    # 2) Rezerva / sa muaj rron pa te ardhura (20 pike)
    muaj_mbulimi = (bil["likuiditet"] / shpenzim_mujor) if shpenzim_mujor > 0 else 0.0
    rezerva_synim = _num(c.get("rezerva_muaj"), 3) or 3
    p2 = 20 * _kufizo(muaj_mbulimi / rezerva_synim)
    perberesit.append({
        "emri": "Rezerva e emergjences", "pike": _rrum(p2, 1), "maks": 20,
        "vlera": f"{muaj_mbulimi:.1f} muaj", "synimi": f"{rezerva_synim:.0f} muaj",
        "shpjegim": "Sa muaj mbijeton me likuiditetin aktual pa asnje te ardhur."
    })

    # 3) Barra e borxhit (20 pike) — kestet ndaj te ardhurave.
    dti = (det["kestet_mujore"] / te_ardhura) if te_ardhura > 0 else (
        1.0 if det["kestet_mujore"] > 0 else 0.0)
    p3 = 20 * _kufizo((0.50 - dti) / 0.40)     # <=10% → plot; >=50% → zero
    perberesit.append({
        "emri": "Barra e borxhit", "pike": _rrum(p3, 1), "maks": 20,
        "vlera": f"{dti * 100:.1f}%", "synimi": "< 10%",
        "shpjegim": "Sa perqind e te ardhurave shkon ne keste borxhi (DTI)."
    })

    # 4) Qendrueshmeria e shpenzimeve (15 pike) — sa i parashikueshem je.
    cv = rrj["paqendrueshmeria"]
    p4 = 15 * (1 - _kufizo(cv / 0.6)) if rrj["muaj_te_plote"] >= 3 else 7.5
    perberesit.append({
        "emri": "Qendrueshmeria", "pike": _rrum(p4, 1), "maks": 15,
        "vlera": f"CV {cv:.2f}", "synimi": "< 0.20",
        "shpjegim": ("Sa luhaten shpenzimet muaj pas muaji. Nen 3 muaj historik "
                     "jepet gjysma e pikeve — s'ka ende baze per gjykim.")
    })

    # 5) Disiplina e pagesave (10 pike) — asgje e vonuar.
    te_gjitha = det["borxhe"] + det["arketime"]
    vonuar = [x for x in te_gjitha if x["vonuar"]]
    raporti = (len(vonuar) / len(te_gjitha)) if te_gjitha else 0.0
    p5 = 10 * (1 - _kufizo(raporti * 2))
    perberesit.append({
        "emri": "Disiplina e afateve", "pike": _rrum(p5, 1), "maks": 10,
        "vlera": f"{len(vonuar)} te vonuara nga {len(te_gjitha)}", "synimi": "0",
        "shpjegim": "Detyrime dhe arketime qe e kane kaluar afatin."
    })

    # 6) Struktura e te ardhurave (10 pike) — diversifikim + pjese pasive.
    vleresimet = vleresoj_te_ardhurat(g, c)
    burimet = [v["mujore_baze"] for v in vleresimet.values() if v["mujore_baze"] > 0]
    total_b = sum(burimet)
    if total_b > 0:
        pjesa_me_e_madhe = max(burimet) / total_b
        diversiteti = _kufizo((1 - pjesa_me_e_madhe) / 0.5)      # 2+ burime te barabarta → plot
        pasive = sum(vleresimet.get(int(a["id"]), {}).get("mujore_baze", 0.0)
                     for a in g["te_ardhurat"] if _num(a.get("oret_mujore")) <= 0)
        pjesa_pasive = _kufizo((pasive / total_b) / 0.3)
        p6 = 10 * (0.6 * diversiteti + 0.4 * pjesa_pasive)
        vlera6 = f"{len(burimet)} burime, me i madhi {pjesa_me_e_madhe * 100:.0f}%"
    else:
        p6, vlera6 = 0.0, "asnje burim i deklaruar"
    perberesit.append({
        "emri": "Struktura e te ardhurave", "pike": _rrum(p6, 1), "maks": 10,
        "vlera": vlera6, "synimi": "2+ burime, 30% pasive",
        "shpjegim": "Nje burim i vetem do te thote nje pike e vetme deshtimi."
    })

    total = sum(p["pike"] for p in perberesit)
    if total < 30:
        niveli, ngjyra = "Kritik", "#dc2626"
    elif total < 50:
        niveli, ngjyra = "Brishte", "#ea580c"
    elif total < 70:
        niveli, ngjyra = "Stabil", "#ca8a04"
    elif total < 85:
        niveli, ngjyra = "I forte", "#16a34a"
    else:
        niveli, ngjyra = "Elitar", "#0891b2"

    return {
        "totali": _rrum(total, 1), "niveli": niveli, "ngjyra": ngjyra,
        "perberesit": perberesit,
        "dti": _rrum(dti * 100, 1),
        "norma_kursimit": _rrum(norma * 100, 1),
        "muaj_mbulimi": _rrum(muaj_mbulimi, 1),
        "shpenzim_mujor": _rrum(shpenzim_mujor),
    }


def llogarit_kapacitetin(c: Dict[str, Any], bil: Dict[str, Any], rrj: Dict[str, Any],
                         det: Dict[str, Any], inv: Dict[str, Any],
                         skor: Dict[str, Any]) -> Dict[str, Any]:
    """Sa peshe mban vertet: rezerva, teprica e lire, kesti maksimal i ri."""
    rezerva_muaj = _num(c.get("rezerva_muaj"), 3) or 3
    shpenzim = skor["shpenzim_mujor"]
    rezerva_synim = shpenzim * rezerva_muaj
    mungesa = max(0.0, rezerva_synim - bil["likuiditet"])
    teprica = max(0.0, bil["likuiditet"] - rezerva_synim)
    te_ardhura = rrj["te_ardhura_totale"]
    rrjedha_neto = te_ardhura - shpenzim

    # Kesti i ri maksimal: 60% e rrjedhes neto, dhe njekohesisht DTI total <= 35%.
    kufi_rrjedhe = max(0.0, rrjedha_neto * 0.60)
    kufi_dti = max(0.0, te_ardhura * 0.35 - det["kestet_mujore"])
    kesti_max = min(kufi_rrjedhe, kufi_dti)

    return {
        "likuiditet": bil["likuiditet"],
        "rezerva_synim": _rrum(rezerva_synim),
        "rezerva_mungese": _rrum(mungesa),
        "teprica_e_lire": _rrum(teprica),
        "rrjedha_neto_mujore": _rrum(rrjedha_neto),
        "kesti_i_ri_max": _rrum(kesti_max),
        "kufizuesi": ("rrjedha mujore" if kufi_rrjedhe <= kufi_dti else "DTI 35%"),
        "per_investim_tani": _rrum(teprica if mungesa <= 0 else 0.0),
        "per_kursim_mujor": _rrum(max(0.0, rrjedha_neto * 0.8)),
        "neto_vlera": _rrum(bil["total_baze"] + inv["vlera_baze"]
                            + det["arketime_neto"] - det["total_borxh"]),
        "koha_deri_te_rezerva": (
            None if mungesa <= 0 or rrjedha_neto <= 0
            else _rrum(mungesa / rrjedha_neto, 1)),
    }


def strategji_borxhi(det: Dict[str, Any], kapacitet: Dict[str, Any]) -> Dict[str, Any]:
    """Krahason ortekun (interesi me i larte i pari) me debollen (borxhi me i
    vogel i pari), me te njejten shume shtese mujore. Kthen muajt dhe interesin
    total per te dyja."""
    shtesa = max(0.0, kapacitet["rrjedha_neto_mujore"] * 0.5)

    def _simulo(renditja: List[dict]) -> Dict[str, Any]:
        mbetjet = {b["id"]: b["mbetur_baze"] for b in renditja}
        normat = {b["id"]: b["interesi_vjetor"] / 100.0 / 12.0 for b in renditja}
        kestet = {b["id"]: b["kesti_mujor_baze"] for b in renditja}
        if shtesa <= 0 and all(k <= 0 for k in kestet.values()):
            return {"muaj": None, "interes": None,
                    "shenim": "Asnje kest dhe asnje teprice — borxhi s'levizet."}
        interesi_total, muaji = 0.0, 0
        while any(v > 0.005 for v in mbetjet.values()) and muaji < 600:
            muaji += 1
            lire = shtesa
            for b in renditja:
                i = b["id"]
                if mbetjet[i] <= 0.005:
                    continue
                interes = mbetjet[i] * normat[i]
                interesi_total += interes
                mbetjet[i] += interes
                pagese = min(kestet[i], mbetjet[i])
                mbetjet[i] -= pagese
            for b in renditja:                     # shtesa shkon te i pari i rendit
                i = b["id"]
                if lire <= 0:
                    break
                if mbetjet[i] > 0.005:
                    pagese = min(lire, mbetjet[i])
                    mbetjet[i] -= pagese
                    lire -= pagese
        return {"muaj": muaji if muaji < 600 else None,
                "interes": _rrum(interesi_total),
                "shenim": None if muaji < 600 else "Mbi 50 vjet me kete ritem."}

    borxhe = [b for b in det["borxhe"] if b["mbetur_baze"] > 0]
    if not borxhe:
        return {"ka_borxhe": False}

    orteku = _simulo(sorted(borxhe, key=lambda b: -b["interesi_vjetor"]))
    debolla = _simulo(sorted(borxhe, key=lambda b: b["mbetur_baze"]))
    fitimi = None
    if orteku.get("interes") is not None and debolla.get("interes") is not None:
        fitimi = _rrum(debolla["interes"] - orteku["interes"])

    return {
        "ka_borxhe": True, "shtesa_mujore": _rrum(shtesa),
        "orteku": orteku, "debolla": debolla,
        "kursim_nga_orteku": fitimi,
        "rekomandimi": ("Orteku — te kursen interes"
                        if (fitimi or 0) > 0 else
                        "Te dyja njesoj — zgjidh ate qe te mban te motivuar"),
    }


def gjenero_alarme(c: Dict[str, Any], g: Dict[str, Any], bil: Dict[str, Any],
                   rrj: Dict[str, Any], det: Dict[str, Any], inv: Dict[str, Any],
                   proj: Dict[str, Any], kap: Dict[str, Any],
                   skor: Dict[str, Any]) -> List[dict]:
    """Sinjalet qe duhen pare sot, te renditura sipas ashpersise."""
    sot = date.today()
    dite_par = int(_num(c.get("paralajmerim_dite"), 14))
    a: List[dict] = []

    def shto(niveli: str, titulli: str, detaji: str, veprimi: str = ""):
        a.append({"niveli": niveli, "titulli": titulli,
                  "detaji": detaji, "veprimi": veprimi})

    for b in det["borxhe"]:
        if b["vonuar"]:
            shto("kritik", f"Borxh i vonuar: {b['pala']}",
                 f"{b['mbetur']:.2f} {b['monedha']} — afati skadoi para "
                 f"{abs(b['dite_mbetur'])} ditesh.",
                 "Paguaj ose rinegocio afatin sot.")
        elif b["dite_mbetur"] is not None and 0 <= b["dite_mbetur"] <= dite_par:
            shto("paralajmerim", f"Afat i afert: {b['pala']}",
                 f"{b['mbetur']:.2f} {b['monedha']} skadon per "
                 f"{b['dite_mbetur']} dite.",
                 "Sigurohu qe likuiditeti e mbulon ate dite.")

    for r in det["arketime"]:
        if r["vonuar"]:
            shto("paralajmerim", f"Arketim i vonuar: {r['pala']}",
                 f"{r['mbetur']:.2f} {r['monedha']} duhej marre para "
                 f"{abs(r['dite_mbetur'])} ditesh.",
                 "Kujto palen; ul sigurine nese nuk pergjigjet.")

    if proj["muaji_i_pare_negativ"]:
        m = proj["muajt"][proj["muaji_i_pare_negativ"] - 1]
        shto("kritik", f"Bilanc negativ ne muajin {m['etiketa']}",
             f"Me ritmin aktual bilanci bie ne {m['bilanci']:.2f} "
             f"{c['monedha_baze']}.",
             "Shtyj nje shpenzim te planifikuar ose shto te ardhura para atij muaji.")

    if skor["muaj_mbulimi"] < 1:
        shto("kritik", "Pa rezerve emergjence",
             f"Likuiditeti mbulon vetem {skor['muaj_mbulimi']:.1f} muaj shpenzime.",
             "Prioritet absolut: nje muaj shpenzime ne para te gatshme.")
    elif skor["muaj_mbulimi"] < _num(c.get("rezerva_muaj"), 3):
        shto("paralajmerim", "Rezerve nen synim",
             f"{skor['muaj_mbulimi']:.1f} muaj nga "
             f"{_num(c.get('rezerva_muaj'), 3):.0f} te synuar "
             f"(mungojne {kap['rezerva_mungese']:.2f} {c['monedha_baze']}).",
             "Dergo tepricen mujore te rezerva derisa te mbushet.")

    if skor["dti"] > 40:
        shto("kritik", "Barre borxhi e rende",
             f"{skor['dti']:.0f}% e te ardhurave shkon ne keste.",
             "Rifinancim ose shlyerje e pjesshme — mos merr borxh te ri.")
    elif skor["dti"] > 25:
        shto("paralajmerim", "Barre borxhi ne rritje",
             f"{skor['dti']:.0f}% e te ardhurave shkon ne keste.", "")

    per_interes = [b for b in det["borxhe"] if b["interesi_vjetor"] >= 12]
    if per_interes:
        me_i_keqi = max(per_interes, key=lambda b: b["interesi_vjetor"])
        shto("paralajmerim", "Borxh me interes te larte",
             f"{me_i_keqi['pala']}: {me_i_keqi['interesi_vjetor']:.2f}% ne vit "
             f"mbi {me_i_keqi['mbetur']:.2f} {me_i_keqi['monedha']}.",
             "Kandidati i pare per shlyerje ose rifinancim.")

    if rrj["te_ardhura_mujore"] > 0 and skor["norma_kursimit"] < 0:
        shto("kritik", "Shpenzon me shume se sa fiton",
             f"Rrjedha mujore: {kap['rrjedha_neto_mujore']:.2f} "
             f"{c['monedha_baze']}.",
             "Pri shpenzimet me domosdoshmeri 4-5 ne muajin e ardhshem.")

    if inv["vlera_baze"] > 0 and inv["perqendrimi_max"] > 60:
        shto("info", "Investime te perqendruara",
             f"{inv['perqendrimi_max']:.0f}% e portofolit ne nje lloj te vetem.",
             "Shperndaje pjesen e re ne nje klase tjeter.")

    def _i_vjetruar(inv_rr: dict) -> bool:
        d = _dat(inv_rr.get("perditesuar_me"))
        return d is None or (sot - d).days > 30

    te_vjetra = [i for i in inv["investimet"] if _i_vjetruar(i)]
    if te_vjetra:
        shto("info", "Cmime investimesh te vjetruara",
             f"{len(te_vjetra)} pozicione s'jane perditesuar prej mbi 30 ditesh.",
             "Hap skanimin e opsioneve per te rifreskuar vleresimin.")

    if len(g["te_ardhurat"]) == 1:
        shto("info", "Nje burim i vetem te ardhurash",
             "Humbja e tij i ndal te gjitha hyrjet njeheresh.",
             "Nje burim i dyte, sado i vogel, e ndryshon profilin e rrezikut.")

    monedhat_e_panjohura = set()
    for tabela in ("llogarite", "detyrimet", "planet", "investimet", "te_ardhurat"):
        for rr in g.get(tabela, []):
            m = (rr.get("monedha") or "").strip().upper()
            if m and monedha_kanonike(m) not in c["kurset"]:
                monedhat_e_panjohura.add(m)
    if monedhat_e_panjohura:
        shto("paralajmerim", "Monedha pa kurs kembimi",
             f"{', '.join(sorted(monedhat_e_panjohura))} — jane numeruar 1:1 me "
             f"{c['monedha_baze']}.",
             "Menu → Cilesimet → Kurset e kembimit.")

    rendi = {"kritik": 0, "paralajmerim": 1, "info": 2}
    return sorted(a, key=lambda x: rendi.get(x["niveli"], 3))


def _dita_e_muajit(dita: int, viti: int, muaji: int) -> date:
    """Dita e kerkuar e muajit, e kapur te dita e fundit (31 shkurt -> 28/29)."""
    return date(viti, muaji, min(max(1, dita), calendar.monthrange(viti, muaji)[1]))


def gjenero_njoftimet(g: Dict[str, Any], c: Dict[str, Any]) -> List[dict]:
    """Pagesat e pritshme qe ende s'jane shenuar.

    Nje pagese e perseritshme njihet e kryer kur ekziston nje transaksion i
    lidhur me ate burim (te_ardhura_id / plani_id) brenda asaj periudhe.

    Data mund te jete nje dritare, jo nje dite e vetme: "paguhem mes 18-20"
    shkruhet me dita_pageses=18 dhe dita_pageses_fund=20. Vonesa fillon te
    numerohet nga dita e fundit e dritares, jo nga e para — perndryshe do te
    thoshte "vonuar" per nje pagese qe ende s'ka arritur afatin.
    """
    sot = date.today()
    vleresimet = vleresoj_te_ardhurat(g, c)
    njoftime: List[dict] = []

    periudhat = [(sot.year, sot.month)]
    if sot.month == 1:
        periudhat.append((sot.year - 1, 12))
    else:
        periudhat.append((sot.year, sot.month - 1))

    def u_regjistrua(fusha: str, burimi_id: int, viti: int, muaji: int) -> bool:
        for t in g["transaksionet"]:
            vlera = t.get(fusha)
            if vlera is None:
                continue
            try:
                if int(vlera) != int(burimi_id):
                    continue
            except (TypeError, ValueError):
                continue
            d = _dat(t.get("data"))
            if d and d.year == viti and d.month == muaji:
                return True
        return False

    def shto(burimi: dict, fusha: str, drejtimi: str, viti: int, muaji: int,
             emri: str, monedha: str, shuma: Optional[float], e_ndryshueshme: bool,
             tabela: str, kategoria: str, shtese: str = ""):
        dita = int(_num(burimi.get("dita_pageses"), 0))
        if dita <= 0:
            return
        fillimi_d = _dita_e_muajit(dita, viti, muaji)
        dita_fund = int(_num(burimi.get("dita_pageses_fund"), 0))
        fundi_d = (_dita_e_muajit(dita_fund, viti, muaji)
                   if dita_fund >= dita else fillimi_d)

        # Tre dite perpara mjaftojne: me heret eshte zhurme, jo kujtese.
        if (fillimi_d - sot).days > 3:
            return
        # Mos pyet per nje periudhe kur burimi ende s'ekzistonte.
        krijuar = _dat(burimi.get("krijuar_me"))
        if krijuar and krijuar > fundi_d:
            return
        if u_regjistrua(fusha, burimi["id"], viti, muaji):
            return

        vonesa = (sot - fundi_d).days
        niveli = "vonuar" if vonesa > 1 else "pritet"
        muaji_emer = f"{viti:04d}-{muaji:02d}"
        kur = (f"mes {fillimi_d.day} dhe {fundi_d.day} te {muaji_emer}"
               if fundi_d != fillimi_d else f"me {fillimi_d.isoformat()}")

        shuma_teksti = f"{_num(shuma):,.0f}".replace(",", ".")

        if drejtimi == "hyrje" and e_ndryshueshme:
            titulli = f"{emri} — sa more kete muaj?"
            detaji = (f"Pagesa e {muaji_emer} pritej {kur}. Shuma ndryshon "
                      f"sipas punes, prandaj s'e plotesoj dot une.")
            if shtese:
                detaji += f" {shtese}"
        elif drejtimi == "hyrje":
            detaji = f"Pritej {kur}, zakonisht {shuma_teksti} {monedha}."
            titulli = f"{emri} — konfirmo pagesen"
        else:
            titulli = f"{emri} — pagesa e {muaji_emer}"
            detaji = f"Duhet paguar {kur}: {shuma_teksti} {monedha}."
        if vonesa > 1:
            detaji += f" Kane kaluar {vonesa} dite pa u shenuar."

        njoftime.append({
            "id": f"{tabela}-{burimi['id']}-{muaji_emer}",
            "niveli": niveli,
            "drejtimi": drejtimi,
            "titulli": titulli,
            "detaji": detaji,
            "data_pritur": fillimi_d.isoformat(),
            "data_fundit": fundi_d.isoformat(),
            "dite_vonese": max(0, vonesa),
            "veprimi": {
                "etiketa": ("Shto shumen" if e_ndryshueshme else
                            "Konfirmo" if drejtimi == "hyrje" else "Shenoje pagesen"),
                "lloji": "te_ardhura" if drejtimi == "hyrje" else "plan",
                "burimi_id": burimi["id"],
                "emri": emri,
                "monedha": monedha,
                "shuma": None if e_ndryshueshme else shuma,
                "data": min(sot, fundi_d).isoformat(),
                "llogaria_id": burimi.get("llogaria_id"),
                "kategoria": kategoria,
            },
        })

    # ── Te ardhurat ──────────────────────────────────────────────────────
    for a in g["te_ardhurat"]:
        if not a.get("aktiv", True):
            continue
        e_ndryshueshme = bool(a.get("shuma_e_ndryshueshme"))
        v = vleresimet.get(int(a["id"]), {})
        shuma = _num(a.get("shuma_mujore"))
        shtese = ""
        if e_ndryshueshme and v.get("burimi") == "historik":
            kursi = kursi_i(c, a.get("monedha")) or 1.0
            mesatarja_teksti = f"{v['mujore_baze'] / kursi:,.0f}".replace(",", ".")
            shtese = (f"Mesatarja e {v['pagesa']} pagesave te fundit: "
                      f"{mesatarja_teksti} "
                      f"{(a.get('monedha') or c['monedha_baze']).upper()}.")
        for viti, muaji in periudhat:
            shto(a, "te_ardhura_id", "hyrje", viti, muaji,
                 a.get("emri") or "Te ardhur",
                 (a.get("monedha") or c["monedha_baze"]).upper(),
                 shuma, e_ndryshueshme, "te-ardhurat",
                 a.get("lloji") or "page", shtese)

    # ── Planet: mujore cdo muaj, vjetore vetem ne muajin e vet ───────────
    for pl in g["planet"]:
        frek = (pl.get("frekuenca") or "mujore").lower()
        if frek not in ("mujore", "vjetore"):
            continue
        mbarimi = _dat(pl.get("data_mbarimit"))
        if mbarimi and mbarimi < sot:
            continue
        fillimi = _dat(pl.get("data_fillimit"))
        muaji_i_caktuar = int(_num(pl.get("muaji_pageses"), 0))
        for viti, muaji in periudhat:
            if frek == "vjetore":
                # Pa muaj te caktuar nje shpenzim vjetor s'ka kur te kujtohet.
                if muaji_i_caktuar < 1 or muaji != muaji_i_caktuar:
                    continue
            if fillimi and _dita_e_muajit(31, viti, muaji) < fillimi:
                continue
            shto(pl, "plani_id", (pl.get("drejtimi") or "dalje"), viti, muaji,
                 pl.get("emri") or "Plan",
                 (pl.get("monedha") or c["monedha_baze"]).upper(),
                 _num(pl.get("shuma")), False, "planet",
                 pl.get("kategoria") or "tjeter")

    rendi = {"vonuar": 0, "pritet": 1}
    return sorted(njoftime, key=lambda n: (rendi.get(n["niveli"], 2), n["data_pritur"]))


def ndertoj_panelin(muaj: int = 12) -> Dict[str, Any]:
    """Pika e vetme e vertetes: gjithcka tjeter ndertohet mbi kete."""
    c = lexo_cilesimet()
    g = mbledh_gjendjen()
    bil = llogarit_bilancet(g, c)
    rrj = llogarit_rrjedhen(g, c)
    det = permbledh_detyrimet(g, c)
    inv = vlereso_investimet(g, c)
    proj = projekto(g, c, bil, rrj, det, muaj)
    skor = skor_sjelljeje(c, bil, rrj, det, inv, g)
    kap = llogarit_kapacitetin(c, bil, rrj, det, inv, skor)
    strat = strategji_borxhi(det, kap)
    alarme = gjenero_alarme(c, g, bil, rrj, det, inv, proj, kap, skor)
    njoftime = gjenero_njoftimet(g, c)

    sot = date.today()
    objektiva = []
    for o in g["objektivat"]:
        synim = _num(o.get("shuma_synim"))
        aktuale = _num(o.get("shuma_aktuale"))
        afati = _dat(o.get("afati"))
        muaj_mbetur = max(0, (afati.year - sot.year) * 12 + afati.month - sot.month) \
            if afati else None
        objektiva.append({
            "id": o.get("id"), "emri": o.get("emri"), "lloji": o.get("lloji"),
            "synim": _rrum(synim), "aktuale": _rrum(aktuale),
            "monedha": (o.get("monedha") or c["monedha_baze"]).upper(),
            "perqind": _rrum(min(100.0, aktuale / synim * 100) if synim > 0 else 0, 1),
            "afati": afati.isoformat() if afati else None,
            "muaj_mbetur": muaj_mbetur,
            "kerkon_ne_muaj": _rrum((synim - aktuale) / muaj_mbetur)
                              if muaj_mbetur else None,
            "arritur": bool(o.get("arritur")),
        })

    return {
        "koha": datetime.now(timezone.utc).isoformat(),
        "monedha_baze": c["monedha_baze"],
        "cilesimet": c,
        "bilancet": bil, "rrjedha": rrj, "detyrimet": det, "investimet": inv,
        "projeksioni": proj, "skori": skor, "kapaciteti": kap,
        "strategjia_borxhit": strat, "alarmet": alarme, "njoftimet": njoftime,
        "objektivat": objektiva,
        "planet": g["planet"], "te_ardhurat": g["te_ardhurat"],
        "vleresimi_te_ardhurave": {str(k): v for k, v in
                                   vleresoj_te_ardhurat(g, c).items()},
    }


# ==========================================================================
# KESHILLTARI — Claude + kerkim ne internet
# ==========================================================================
# Ndarja e roleve eshte e rrepte:
#   • Numrat (balanca, skor, projeksion) i nxjerr motori me siper.
#   • Claude merr numrat e GATSHEM dhe sjell ate qe motori s'e di dot:
#     normat e tregut, opsionet, cmimet, alternativat. Nuk i rillogarit.
# Te dhenat financiare i dergohen API-t te Anthropic vetem kur E THERRET vete
# kete endpoint — asgje nuk niset ne sfond.
# ==========================================================================
UDHEZIMI = """Ti je analist financiar personal per nje perdorues shqipfoles.

Te jepet nje FOTOGRAFI e gjendjes financiare, e llogaritur tashme nga nje motor
deterministik. Numrat aty jane te sakte dhe perfundimtare:
  • MOS i rillogarit, mos i korrigjo, mos shpik shifra qe s'jane ne te dhena.
  • Nese nje numer te duket i gabuar, thuaje shkurt pse dhe vazhdo.

Puna jote ka dy pjese:
1. INTERPRETIM — cfare do te thone keta numra ne praktike per kete njeri.
2. BOTA E JASHTME — perdor kerkimin ne internet per ate qe fotografia s'e ka:
   norma interesi aktuale, kushte rifinancimi, instrumente kursimi/investimi te
   disponueshme, cmime tregu, inflacion. Cito gjithmone burimin dhe daten.

Rregulla:
  • Shqip, drejtperdrejt, pa fjale te bukura boshe. Shifrat me monedhen perkatese.
  • Maksimumi 3 veprime konkrete per periudhen e afert — te renditura sipas
    efektit ne para, jo sipas lehtesise.
  • Cdo keshille duhet te jete e realizueshme me kapacitetin e tij real
    (shih 'kapaciteti'), jo me para qe nuk i ka.
  • Nese te dhenat jane te pamjaftueshme per nje pyetje, thuaje qarte cfare
    mungon ne vend qe te hamendesosh.
  • Ti nuk je keshilltar i licencuar investimesh: mbyll me nje rresht qe
    kujton se vendimin perfundimtar e merr ai.

Struktura e pergjigjes (markdown, pa titull te pergjithshem):
### Gjendja me dy fjale
### 3 levizjet e radhes
### Rreziqet qe s'i sheh
### Nga tregu sot   (vetem me burime te cituara; hiqe nese s'ke kerkuar)
"""

UDHEZIMI_SKANIM = """Ti je skaner tregu per nje portofol personal.

Te jepen pozicionet, borxhet dhe burimet e te ardhurave te nje perdoruesi
shqipfoles. Per secilin, kerko ne internet gjendjen e sotme te tregut:
  • Investimet: cmimi aktual, ecuria e fundit, kosto/komisione, alternativa me
    te lira ose me te mira ne te njejten klase.
  • Borxhet: norma aktuale te kredive/rifinancimit qe do t'ia ulnin interesin.
  • Likuiditeti i pashfrytezuar: ku mban vlere sot pa rrezik te madh
    (depozita, obligacione qeveritare, fonde tregu parash).

Shqip, i shkurter, i verifikueshem. Cdo pretendim me burim dhe date.
Cmimet e gjetura NUK i zbato — vetem propozoji.

Mbylle pergjigjen me nje bllok te vetem kodi json me kete forme te sakte:
```json
{"cmimet": [{"id": 12, "simboli": "VWCE.DE", "cmimi": 128.4, "monedha": "EUR", "burimi": "https://..."}]}
```
Perfshi vetem pozicionet per te cilat gjete cmim te besueshem. Nese s'gjete
asnje, ktheje listen bosh.
"""


def _klienti_anthropic():
    if not ANTHROPIC_API_KEY:
        raise HTTPException(503, "ANTHROPIC_API_KEY mungon — keshilltari i fikur.")
    try:
        import anthropic
    except ImportError:
        raise HTTPException(503, "Paketa 'anthropic' nuk eshte instaluar "
                                 "(shto-e ne requirements.txt).")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=600.0)


def _fotografia(panel: Dict[str, Any]) -> Dict[str, Any]:
    """Fotografi e ngjeshur — vetem sa i duhet modelit per te gjykuar."""
    d = panel["detyrimet"]
    return {
        "monedha_baze": panel["monedha_baze"],
        "data": date.today().isoformat(),
        "skori": {
            "totali": panel["skori"]["totali"], "niveli": panel["skori"]["niveli"],
            "perberesit": [{"emri": p["emri"], "pike": p["pike"], "maks": p["maks"],
                            "vlera": p["vlera"]} for p in panel["skori"]["perberesit"]],
        },
        "likuiditet": panel["bilancet"]["likuiditet"],
        "total_llogarite": panel["bilancet"]["total_baze"],
        "rrjedha": {k: panel["rrjedha"][k] for k in
                    ("te_ardhura_mujore", "dalje_mesatare", "dalje_baze_mujore",
                     "paqendrueshmeria", "muaj_te_plote")},
        "kapaciteti": panel["kapaciteti"],
        "borxhet": [{"pala": b["pala"], "mbetur": b["mbetur"], "monedha": b["monedha"],
                     "interes": b["interesi_vjetor"], "kesti": b["kesti_mujor_baze"],
                     "afati": b["afati"], "vonuar": b["vonuar"]} for b in d["borxhe"]],
        "arketimet": [{"pala": a["pala"], "mbetur": a["mbetur"],
                       "monedha": a["monedha"], "afati": a["afati"],
                       "siguria": a["siguria"], "vonuar": a["vonuar"]}
                      for a in d["arketime"]],
        "investimet": [{"id": i["id"], "emri": i["emri"], "lloji": i["lloji"],
                        "simboli": i["simboli"], "sasia": i["sasia"],
                        "vlera": i["vlera_baze"], "fitimi_perqind": i["fitimi_perqind"],
                        "rreziku": i["rreziku"]}
                       for i in panel["investimet"]["investimet"]],
        "perqendrimi_investimeve": panel["investimet"]["perqendrimi_max"],
        "te_ardhurat": [{"emri": a.get("emri"), "lloji": a.get("lloji"),
                         "shuma_mujore": _num(a.get("shuma_mujore")),
                         "monedha": a.get("monedha"), "siguria": a.get("siguria"),
                         "oret_mujore": _num(a.get("oret_mujore"))}
                        for a in panel["te_ardhurat"]],
        "planet": [{"emri": p.get("emri"), "drejtimi": p.get("drejtimi"),
                    "shuma": _num(p.get("shuma")), "monedha": p.get("monedha"),
                    "frekuenca": p.get("frekuenca"), "horizonti": p.get("horizonti"),
                    "domosdoshmeria": p.get("domosdoshmeria"),
                    "probabiliteti": p.get("probabiliteti"),
                    "data_fillimit": p.get("data_fillimit")}
                   for p in panel["planet"]],
        "objektivat": panel["objektivat"],
        "projeksioni_12m": {
            "bilanci_fundor": panel["projeksioni"]["bilanci_fundor"],
            "pika_me_e_ulet": panel["projeksioni"]["pika_me_e_ulet"],
            "muaji_i_pare_negativ": panel["projeksioni"]["muaji_i_pare_negativ"],
            "muajt": [{"etiketa": m["etiketa"], "neto": m["neto"],
                       "bilanci": m["bilanci"]}
                      for m in panel["projeksioni"]["muajt"]],
        },
        "strategjia_borxhit": panel["strategjia_borxhit"],
        "alarmet": panel["alarmet"],
    }


def _thirr_claude(udhezimi: str, mesazhi: str, kerko_ne_internet: bool = True,
                  max_tokens: int = 16000) -> Dict[str, Any]:
    """Nje thirrje e vetme, me streaming (kerkimi ne web e zgjat turnin)."""
    client = _klienti_anthropic()
    argumentet: Dict[str, Any] = {
        "model": FIN_MODELI,
        "max_tokens": max_tokens,
        "system": udhezimi,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "high"},
        "messages": [{"role": "user", "content": mesazhi}],
    }
    if kerko_ne_internet:
        argumentet["tools"] = [{"type": "web_search_20260209",
                                "name": "web_search", "max_uses": 8}]
    try:
        with client.messages.stream(**argumentet) as rrjedha:
            pergjigja = rrjedha.get_final_message()
    except Exception as e:
        raise HTTPException(502, f"Claude nuk u pergjigj: {type(e).__name__}: {e}")

    tekst, burime = [], []
    for bllok in pergjigja.content:
        tipi = getattr(bllok, "type", "")
        if tipi == "text":
            tekst.append(bllok.text)
        elif tipi == "web_search_tool_result":
            # Ne sukses .content eshte liste rezultatesh; ne gabim eshte objekt.
            permbajtja = getattr(bllok, "content", None)
            if isinstance(permbajtja, list):
                for r in permbajtja:
                    u = getattr(r, "url", None)
                    if u:
                        burime.append({"url": u, "titulli": getattr(r, "title", "")})

    perdorimi = getattr(pergjigja, "usage", None)
    # Hiq dublikatat e linqeve, ruaj rendin.
    pare, unike = set(), []
    for b in burime:
        if b["url"] not in pare:
            pare.add(b["url"])
            unike.append(b)

    return {
        "teksti": "\n".join(tekst).strip(),
        "burimet": unike,
        "modeli": getattr(pergjigja, "model", FIN_MODELI),
        "ndalimi": getattr(pergjigja, "stop_reason", None),
        "tokena": {
            "hyrje": getattr(perdorimi, "input_tokens", None),
            "dalje": getattr(perdorimi, "output_tokens", None),
        } if perdorimi else None,
    }


def _ruaj_raportin(lloji: str, pyetja: str, gjendja: dict,
                   dalja: Dict[str, Any]) -> Optional[int]:
    try:
        rr = _sb("fin_raportet", "post", trupi={
            "user_id": USER_ID, "lloji": lloji, "pyetja": pyetja,
            "gjendja": gjendja, "pergjigja": dalja["teksti"],
            "burimet": dalja["burimet"], "modeli": dalja["modeli"],
            "tokena": dalja["tokena"],
        }, prefer="return=representation")
        return rr[0]["id"] if isinstance(rr, list) and rr else None
    except HTTPException:
        return None      # analiza vlen edhe pa u arkivuar


def _nxirr_json(tekst: str) -> Optional[dict]:
    """Merr bllokun e fundit ```json nga pergjigja. Kthen None nese s'ka."""
    pjeset = tekst.split("```")
    for copa in reversed(pjeset):
        copa = copa.strip()
        if copa.startswith("json"):
            copa = copa[4:].strip()
        if copa.startswith("{"):
            try:
                return json.loads(copa)
            except ValueError:
                continue
    return None


# ==========================================================================
# ENDPOINTS — te dhenat (CRUD)
# ==========================================================================
def _tabela(emri: str) -> str:
    if emri not in TABELAT:
        raise HTTPException(404, f"Tabele e panjohur '{emri}'. "
                                 f"Te lejuara: {', '.join(TABELAT)}")
    return TABELAT[emri]


def _pastro(emri: str, trupi: dict) -> dict:
    """Mban vetem fushat e lejuara. id/user_id/krijuar_me nuk vendosen kurre
    nga jashte."""
    lejuar = FUSHAT.get(emri, set())
    if not lejuar:
        raise HTTPException(405, f"Tabela '{emri}' eshte vetem per lexim.")
    e_paster = {k: v for k, v in (trupi or {}).items() if k in lejuar}
    if not e_paster:
        raise HTTPException(400, f"Asnje fushe e vlefshme. Te lejuara: "
                                 f"{', '.join(sorted(lejuar))}")
    return e_paster


@router.get("/te-dhena/{tabela}")
def lexo_tabelen(tabela: str, kufi: int = Query(500, ge=1, le=5000),
                 rendit: Optional[str] = Query(None, pattern=r"^[a-z_]{1,40}\.(asc|desc)$"),
                 frekuenca: Optional[str] = Query(None, pattern=r"^[a-z_]{1,20}$"),
                 drejtimi: Optional[str] = Query(None, pattern=r"^(hyrje|dalje)$"),
                 lloji: Optional[str] = Query(None, pattern=r"^[a-z_]{1,20}$"),
                 _: Optional[str] = Header(None, alias="X-Fin-Token")):
    """Filtrat sherbejne per pamjet e ngushta te se njejtes tabele — p.sh.
    'shpenzimet mujore fikse' jane thjesht planet me frekuence mujore dhe
    drejtim dalje, pa nevojen e nje tabele te dyte."""
    kerko_token(_)
    filtra = {}
    if frekuenca:
        filtra["frekuenca"] = f"eq.{frekuenca}"
    if drejtimi:
        filtra["drejtimi"] = f"eq.{drejtimi}"
    if lloji:
        filtra["lloji"] = f"eq.{lloji}"
    parazgjedhur = {"transaksionet": "data.desc", "raportet": "krijuar_me.desc"}
    return _lexo(_tabela(tabela), filtra or None,
                 rendit or parazgjedhur.get(tabela, "id.desc"), kufi)


@router.post("/te-dhena/{tabela}")
def shto_rresht(tabela: str, trupi: dict = Body(...),
                _: Optional[str] = Header(None, alias="X-Fin-Token")):
    kerko_token(_)
    rresht = _pastro(tabela, trupi)
    rresht["user_id"] = USER_ID
    dalja = _sb(_tabela(tabela), "post", trupi=rresht,
                prefer="return=representation")
    return dalja[0] if isinstance(dalja, list) and dalja else dalja


@router.patch("/te-dhena/{tabela}/{rreshti_id}")
def ndrysho_rresht(tabela: str, rreshti_id: int, trupi: dict = Body(...),
                   _: Optional[str] = Header(None, alias="X-Fin-Token")):
    kerko_token(_)
    rresht = _pastro(tabela, trupi)
    dalja = _sb(_tabela(tabela), "patch",
                params={"id": f"eq.{rreshti_id}", "user_id": f"eq.{USER_ID}"},
                trupi=rresht, prefer="return=representation")
    if not dalja:
        raise HTTPException(404, f"Rreshti {rreshti_id} nuk u gjet ne '{tabela}'.")
    return dalja[0] if isinstance(dalja, list) else dalja


@router.delete("/te-dhena/{tabela}/{rreshti_id}")
def fshi_rresht(tabela: str, rreshti_id: int,
                _: Optional[str] = Header(None, alias="X-Fin-Token")):
    kerko_token(_)
    dalja = _sb(_tabela(tabela), "delete",
                params={"id": f"eq.{rreshti_id}", "user_id": f"eq.{USER_ID}"},
                prefer="return=representation")
    if not dalja:
        raise HTTPException(404, f"Rreshti {rreshti_id} nuk u gjet ne '{tabela}'.")
    return {"fshire": rreshti_id, "tabela": tabela}


@router.post("/llogaria-kesh")
def llogaria_kesh(_: Optional[str] = Header(None, alias="X-Fin-Token")):
    """Kthen llogarine 'para ne dore', duke e krijuar nese s'ekziston.

    Jo cdo pagese bie ne banke. Pa kete, formularet do te detyronin zgjedhjen
    e nje llogarie qe perdoruesi s'e ka hapur kurre.
    """
    kerko_token(_)
    ekzistueset = _lexo("fin_llogarite", {"lloji": "eq.cash", "aktiv": "eq.true"},
                        "id.asc", 1)
    if ekzistueset:
        return ekzistueset[0]
    c = lexo_cilesimet()
    dalja = _sb("fin_llogarite", "post", trupi={
        "user_id": USER_ID, "emri": "Kesh", "lloji": "cash",
        "monedha": c["monedha_baze"], "bilanci_fillestar": 0,
        "likuide": True, "aktiv": True,
        "shenime": "Krijuar automatikisht per pagesat ne dore.",
    }, prefer="return=representation")
    return dalja[0] if isinstance(dalja, list) and dalja else dalja


@router.get("/cilesimet")
def merr_cilesimet(_: Optional[str] = Header(None, alias="X-Fin-Token")):
    kerko_token(_)
    return lexo_cilesimet()


@router.patch("/cilesimet")
def ndrysho_cilesimet(trupi: dict = Body(...),
                      _: Optional[str] = Header(None, alias="X-Fin-Token")):
    kerko_token(_)
    lejuar = set(CILESIMET_PARAZGJEDHUR)
    pa_njohur = set(trupi) - lejuar
    if pa_njohur:
        raise HTTPException(400, f"Celesa te panjohur: {', '.join(sorted(pa_njohur))}")

    trupi = dict(trupi)
    # Kalimi nga EUR ne LEK s'duhet te kerkoje rishkrimin e tabeles se kurseve
    # me dore: kurset e reja dalin duke i pjesetuar te vjetrat me kursin e
    # monedhes se re baze. 1 EUR = 0.0102 -> 1 LEK, pra 1 EUR = 98.04 LEK.
    if "monedha_baze" in trupi and "kurset" not in trupi:
        e_vjetra = lexo_cilesimet()
        e_re = monedha_kanonike(str(trupi["monedha_baze"]))
        kursi_ri = e_vjetra["kurset"].get(e_re)
        if not kursi_ri or kursi_ri <= 0:
            raise HTTPException(400,
                f"Nuk di kursin e '{trupi['monedha_baze']}'. Shtoje me pare te "
                f"kurset, ose dergo 'kurset' bashke me 'monedha_baze'.")
        trupi["kurset"] = {k: round(v / kursi_ri, 8)
                           for k, v in e_vjetra["kurset"].items()}

    for celes, vlera in trupi.items():
        _sb("fin_cilesimet", "post",
            trupi={"celes": celes, "vlera": vlera,
                   "perditesuar_me": datetime.now(timezone.utc).isoformat()},
            prefer="resolution=merge-duplicates")
    return lexo_cilesimet()


# ==========================================================================
# ENDPOINTS — analiza
# ==========================================================================
@router.get("/panel")
def panel(muaj: int = Query(12, ge=1, le=60),
          _: Optional[str] = Header(None, alias="X-Fin-Token")):
    """Gjithcka ne nje thirrje te vetme: balanca, skor, alarme, projeksion."""
    kerko_token(_)
    return ndertoj_panelin(muaj)


@router.get("/skor")
def skori(_: Optional[str] = Header(None, alias="X-Fin-Token")):
    kerko_token(_)
    p = ndertoj_panelin(3)
    return {"skori": p["skori"], "kapaciteti": p["kapaciteti"]}


@router.get("/alarmet")
def alarmet(_: Optional[str] = Header(None, alias="X-Fin-Token")):
    kerko_token(_)
    return {"alarmet": ndertoj_panelin(12)["alarmet"]}


@router.get("/njoftimet")
def njoftimet(_: Optional[str] = Header(None, alias="X-Fin-Token")):
    kerko_token(_)
    c = lexo_cilesimet()
    return {"njoftimet": gjenero_njoftimet(mbledh_gjendjen(), c)}


@router.post("/regjistro-pagese")
def regjistro_pagese(trupi: dict = Body(...),
                     _: Optional[str] = Header(None, alias="X-Fin-Token")):
    """Mbyll nje njoftim duke krijuar transaksionin perkates.

    Trupi: {lloji: "te_ardhura"|"plan", burimi_id, shuma, data,
            monedha, llogaria_id, pershkrimi}

    Transaksioni ruan lidhjen me burimin (te_ardhura_id / plani_id) — pikerisht
    ajo lidhje ben qe njoftimi te mos shfaqet me kete muaj, dhe njekohesisht e
    mban shumen jashte 'bazes' se shpenzimeve qe te mos numerohet dy here.
    """
    kerko_token(_)
    lloji = (trupi.get("lloji") or "").strip()
    if lloji not in ("te_ardhura", "plan"):
        raise HTTPException(400, "lloji duhet 'te_ardhura' ose 'plan'.")
    try:
        burimi_id = int(trupi.get("burimi_id"))
    except (TypeError, ValueError):
        raise HTTPException(400, "burimi_id mungon ose s'eshte numer.")
    shuma = _num(trupi.get("shuma"))
    if shuma <= 0:
        raise HTTPException(400, "Shuma duhet me e madhe se zero.")

    c = lexo_cilesimet()
    tabela = "fin_te_ardhurat" if lloji == "te_ardhura" else "fin_planet"
    burimet = _lexo(tabela, {"id": f"eq.{burimi_id}"})
    if not burimet:
        raise HTTPException(404, f"Burimi {burimi_id} nuk u gjet ne {tabela}.")
    burimi = burimet[0]

    drejtimi = ("hyrje" if lloji == "te_ardhura"
                else (burimi.get("drejtimi") or "dalje"))
    rresht = {
        "user_id": USER_ID,
        "data": trupi.get("data") or date.today().isoformat(),
        "lloji": drejtimi,
        "shuma": shuma,
        "monedha": (trupi.get("monedha") or burimi.get("monedha")
                    or c["monedha_baze"]).strip().upper(),
        "kategoria": (trupi.get("kategoria") or burimi.get("lloji")
                      or burimi.get("kategoria") or "tjeter"),
        "pershkrimi": trupi.get("pershkrimi") or burimi.get("emri"),
        "llogaria_id": trupi.get("llogaria_id") or burimi.get("llogaria_id"),
    }
    rresht["te_ardhura_id" if lloji == "te_ardhura" else "plani_id"] = burimi_id

    dalja = _sb("fin_transaksionet", "post", trupi=rresht,
                prefer="return=representation")
    return {"transaksioni": dalja[0] if isinstance(dalja, list) and dalja else dalja,
            "njoftimet": gjenero_njoftimet(mbledh_gjendjen(), c)}


@router.get("/projeksion")
def projeksioni(muaj: int = Query(12, ge=1, le=60),
                _: Optional[str] = Header(None, alias="X-Fin-Token")):
    kerko_token(_)
    return ndertoj_panelin(muaj)["projeksioni"]


@router.post("/skenar")
def skenar(trupi: dict = Body(...), _: Optional[str] = Header(None, alias="X-Fin-Token")):
    """'Po sikur?' — shton nje shpenzim/te ardhur hipotetike dhe rillogarit
    projeksionin, pa e prekur bazen e te dhenave.

    Trupi: {emri, shuma, monedha, drejtimi, frekuenca, data_fillimit,
            muaj (opsionale)}
    """
    kerko_token(_)
    muaj = int(_num(trupi.get("muaj"), 12))
    muaj = max(1, min(60, muaj))
    c = lexo_cilesimet()
    g = mbledh_gjendjen()
    bil = llogarit_bilancet(g, c)
    rrj = llogarit_rrjedhen(g, c)
    det = permbledh_detyrimet(g, c)

    para = projekto(g, c, bil, rrj, det, muaj)
    g["planet"] = list(g["planet"]) + [{
        "emri": trupi.get("emri") or "Skenar",
        "drejtimi": trupi.get("drejtimi") or "dalje",
        "shuma": _num(trupi.get("shuma")),
        "monedha": trupi.get("monedha") or c["monedha_baze"],
        "frekuenca": trupi.get("frekuenca") or "nje_here",
        "data_fillimit": trupi.get("data_fillimit") or date.today().isoformat(),
        "data_mbarimit": trupi.get("data_mbarimit"),
        "probabiliteti": _num(trupi.get("probabiliteti"), 100),
    }]
    pas = projekto(g, c, bil, rrj, det, muaj)

    return {
        "para": para, "pas": pas,
        "ndryshimi": {
            "bilanci_fundor": _rrum(pas["bilanci_fundor"] - para["bilanci_fundor"]),
            "pika_me_e_ulet": _rrum(pas["pika_me_e_ulet"] - para["pika_me_e_ulet"]),
            "muaji_i_pare_negativ": pas["muaji_i_pare_negativ"],
        },
        "verdikti": (
            "Nuk e perballon: bilanci bie nen zero."
            if pas["muaji_i_pare_negativ"] and not para["muaji_i_pare_negativ"]
            else "E perballon, por pika me e ulet bie ndjeshem."
            if pas["pika_me_e_ulet"] < para["pika_me_e_ulet"] * 0.5
            else "E perballon."
        ),
    }


# ==========================================================================
# ENDPOINTS — keshilltari
# ==========================================================================
@router.post("/keshilltari")
def keshilltari(trupi: dict = Body(default={}),
                _: Optional[str] = Header(None, alias="X-Fin-Token")):
    """Analize e gjendjes nga Claude, me kerkim ne internet.

    Trupi: {pyetja: "...", internet: true}
    """
    kerko_token(_)
    pyetja = (trupi.get("pyetja") or "").strip()
    internet = bool(trupi.get("internet", True))
    p = ndertoj_panelin(12)
    foto = _fotografia(p)

    mesazhi = (
        "FOTOGRAFIA E GJENDJES (JSON, e llogaritur nga motori):\n"
        f"{json.dumps(foto, ensure_ascii=False, indent=1, default=str)}\n\n"
        + (f"PYETJA IME: {pyetja}" if pyetja else
           "Pa pyetje specifike — jepme leximin e pergjithshem te gjendjes dhe "
           "levizjet e radhes.")
    )
    dalja = _thirr_claude(UDHEZIMI, mesazhi, kerko_ne_internet=internet)
    raporti_id = _ruaj_raportin("keshilltar", pyetja, foto, dalja)
    return {"raporti_id": raporti_id, "pergjigja": dalja["teksti"],
            "burimet": dalja["burimet"], "modeli": dalja["modeli"],
            "tokena": dalja["tokena"], "skori": p["skori"]["totali"],
            "niveli": p["skori"]["niveli"]}


@router.post("/skano-opsionet")
def skano_opsionet(trupi: dict = Body(default={}),
                   _: Optional[str] = Header(None, alias="X-Fin-Token")):
    """Skanon tregun per gjerat qe ke shtuar: cmime, alternativa, rifinancim.

    Trupi: {fokusi: "gjithcka"|"investime"|"borxhe"|"likuiditet"}
    Cmimet e gjetura kthehen si PROPOZIME — zbatohen vetem me /apliko-cmimet.
    """
    kerko_token(_)
    fokusi = (trupi.get("fokusi") or "gjithcka").strip()
    p = ndertoj_panelin(12)
    foto = _fotografia(p)
    ngushtuar = {
        "monedha_baze": foto["monedha_baze"], "data": foto["data"],
        "likuiditet": foto["likuiditet"], "kapaciteti": foto["kapaciteti"],
        "investimet": foto["investimet"], "borxhet": foto["borxhet"],
        "te_ardhurat": foto["te_ardhurat"], "objektivat": foto["objektivat"],
    }
    mesazhi = (f"FOKUSI: {fokusi}\n\nPORTOFOLI (JSON):\n"
               f"{json.dumps(ngushtuar, ensure_ascii=False, indent=1, default=str)}")
    dalja = _thirr_claude(UDHEZIMI_SKANIM, mesazhi, kerko_ne_internet=True)
    raporti_id = _ruaj_raportin("skanim_opsionesh", fokusi, ngushtuar, dalja)

    propozime = (_nxirr_json(dalja["teksti"]) or {}).get("cmimet") or []
    njohur = {i["id"] for i in p["investimet"]["investimet"]}
    propozime = [c for c in propozime if isinstance(c, dict)
                 and c.get("id") in njohur and _num(c.get("cmimi")) > 0]

    return {"raporti_id": raporti_id, "pergjigja": dalja["teksti"],
            "burimet": dalja["burimet"], "propozime_cmimesh": propozime,
            "modeli": dalja["modeli"], "tokena": dalja["tokena"]}


@router.post("/apliko-cmimet")
def apliko_cmimet(trupi: dict = Body(...),
                  _: Optional[str] = Header(None, alias="X-Fin-Token")):
    """Zbaton cmimet e propozuara mbi investimet. Hapi eshte i ndare me qellim:
    asnje cmim i ardhur nga interneti nuk hyn ne baze pa nje klik timin.

    Trupi: {cmimet: [{id, cmimi}, ...]}
    """
    kerko_token(_)
    lista = trupi.get("cmimet") or []
    if not isinstance(lista, list) or not lista:
        raise HTTPException(400, "Prit nje liste jo-bosh 'cmimet'.")
    tani = datetime.now(timezone.utc).isoformat()
    perditesuar = []
    for c in lista:
        try:
            cid = int(c.get("id"))
        except (TypeError, ValueError):
            continue
        cmimi = _num(c.get("cmimi"))
        if cmimi <= 0:
            continue
        dalja = _sb("fin_investimet", "patch",
                    params={"id": f"eq.{cid}", "user_id": f"eq.{USER_ID}"},
                    trupi={"cmimi_aktual": cmimi, "perditesuar_me": tani},
                    prefer="return=representation")
        if dalja:
            perditesuar.append(cid)
    return {"perditesuar": perditesuar, "gjithsej": len(perditesuar)}


@router.get("/raportet")
def raportet(kufi: int = Query(20, ge=1, le=100),
             _: Optional[str] = Header(None, alias="X-Fin-Token")):
    kerko_token(_)
    return _lexo("fin_raportet", None, "krijuar_me.desc", kufi)


@router.get("/shendeti")
def shendeti():
    """Pa token: thote vetem nese moduli eshte i konfiguruar, asnje te dhene."""
    return {
        "moduli": "financat",
        "supabase": bool(SUPABASE_SERVICE_KEY),
        "token_i_vendosur": bool(FIN_TOKEN),
        "keshilltari": bool(ANTHROPIC_API_KEY),
        "modeli": FIN_MODELI,
    }


# ==========================================================================
# FAQJA — servohet pa token; te dhenat i merr vete shfletuesi me token.
# ==========================================================================
router_faqe = APIRouter()


@router_faqe.get("/financat", response_class=HTMLResponse, include_in_schema=False)
def faqja():
    rruga = os.path.join(os.path.dirname(__file__), "financat.html")
    if not os.path.exists(rruga):
        raise HTTPException(404, "financat.html mungon.")
    with open(rruga, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())
