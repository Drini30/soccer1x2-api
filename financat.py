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
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from datetime import datetime, date, time, timezone, tzinfo
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import calendar
import csv
import hmac
import json
import io
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
    "bizneset":      "fin_bizneset",
    "zerat-e-biznesit": "fin_biznes_zerat",
    "buxhetet":      "fin_buxhetet",
    "personat":      "fin_personat",
    "veprimet":      "fin_veprimet",
}

# Fushat qe lejohen te shkruhen nga jashte. Cdo gje tjeter ne trup shperfillet
# ne heshtje — nuk duam qe nje POST te vendose id, user_id apo krijuar_me.
FUSHAT = {
    "llogarite": {"emri", "lloji", "monedha", "bilanci_fillestar", "limiti",
                  "likuide", "aktiv", "shenime", "personi_id"},
    "transaksionet": {"data", "kryer_me", "llogaria_id", "lloji", "shuma",
                      "monedha", "kategoria", "pershkrimi", "detyrimi_id",
                      "plani_id", "te_ardhura_id", "biznesi_id", "llogaria_dest_id",
                      "etiketa", "personi_id"},
    "detyrimet": {"lloji", "pala", "pershkrimi", "shuma_totale", "shuma_paguar",
                  "monedha", "interesi_vjetor", "kesti_mujor", "afati",
                  "prioriteti", "statusi", "siguria", "personi_id"},
    "planet": {"emri", "drejtimi", "shuma", "monedha", "kategoria", "frekuenca",
               "data_fillimit", "data_mbarimit", "horizonti", "domosdoshmeria",
               "probabiliteti", "aktiv", "shenime", "dita_pageses",
               "dita_pageses_fund", "muaji_pageses", "llogaria_id"},
    "te-ardhurat": {"emri", "lloji", "shuma_mujore", "monedha", "siguria",
                    "oret_mujore", "aktiv", "dita_pageses",
                    "shuma_e_ndryshueshme", "llogaria_id", "personi_id"},
    "investimet": {"emri", "lloji", "simboli", "sasia", "cmimi_blerje",
                   "cmimi_aktual", "monedha", "data_blerje", "rreziku",
                   "kthimi_pritshem", "aktiv", "shenime", "perditesuar_me"},
    "objektivat": {"emri", "shuma_synim", "shuma_aktuale", "monedha", "afati",
                   "prioriteti", "lloji", "arritur"},
    "bizneset": {"emri", "pershkrimi", "monedha", "data_fillimit",
                 "terheqje_mujore", "llogaria_id", "njesia", "aktiv", "shenime"},
    "zerat-e-biznesit": {"biznesi_id", "emri", "lloji", "monedha", "shuma",
                         "cmimi_njesi", "sasia", "kosto_per_njesi", "perqindja",
                         "frekuenca", "kategoria", "dita_pageses", "aktiv",
                         "shenime"},
    "buxhetet": {"kategoria", "shuma_mujore", "monedha", "pragu_alarmit",
                 "aktiv", "shenime"},
    "personat": {"emri", "ngjyra", "shenime", "aktiv"},
    "raportet": set(),   # vetem lexim; shkruhet nga keshilltari
    "veprimet": set(),   # vetem lexim; ditarin e shkruan vete moduli
}

# Ora ruhet gjithmone si timestamptz (me zonen brenda), por shfaqet ne zonen
# e perdoruesit. Pa kete, nje pagese e bere ne 00:30 do te dilte "dje" — sepse
# serveri i Render-it punon ne UTC, jo ne oren e Tiranes.
ZONA_PARAZGJEDHUR = "Europe/Tirane"

CILESIMET_PARAZGJEDHUR = {
    "monedha_baze": "EUR",
    "zona_kohore": ZONA_PARAZGJEDHUR,
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


# Kategorite qe nuk preken kur kerkohen para per nje objektiv: te presesh
# ushqimin ose baren e femijes nuk eshte kursim, eshte deshtim i planit.
KATEGORI_TE_DOMOSDOSHME = {
    "ushqime", "ushqim", "qera", "qeraja", "qira", "kredi", "kredia",
    "energjia", "drita", "uji", "ngrohje", "farmaci", "shendet", "mjekim",
    "kopshti", "shkolla", "femijet", "transport", "karburant", "sigurime",
    "taksa_toke", "taksa_shtepie", "taksa_makine", "siguracion_makine",
    "siguracion_shendeti", "interneti", "telefoni",
}

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
# Cili migrim e krijon cilen tabele — perdoret ne mesazhin e alarmit.
MIGRIMET = {
    "fin_bizneset": "financat_migrim_4.sql",
    "fin_biznes_zerat": "financat_migrim_4.sql",
    "fin_buxhetet": "financat_migrim_5.sql",
    "fin_personat": "financat_migrim_6.sql",
    "fin_veprimet": "financat_migrim_7.sql",
}


def _lexo_nese_ekziston(tabela: str, filtra: Optional[dict] = None,
                        rendit: Optional[str] = None,
                        mungesat: Optional[List[str]] = None) -> List[dict]:
    """Si _lexo, por nje tabele qe ende s'eshte krijuar kthen liste bosh.

    Nje migrim i paekzekutuar nuk duhet ta rrezoje gjithe panelin: pjesa
    tjeter e te dhenave eshte e vlefshme dhe duhet te shihet. Mungesa
    raportohet si alarm, me emrin e skedarit qe e ndreq.
    """
    try:
        return _lexo(tabela, filtra, rendit)
    except HTTPException as e:
        teksti = str(e.detail)
        if "PGRST205" in teksti or "schema cache" in teksti:
            if mungesat is not None and tabela not in mungesat:
                mungesat.append(tabela)
            return []
        raise


# ==========================================================================
# DITARI I VEPRIMEVE — cdo veprim le daten dhe oren
# ==========================================================================
# Nje shifer qe levizi pa u kuptuar duhet te kete gjithmone nje shpjegim me
# emer, date dhe ore. Prandaj cdo shtim, ndryshim, fshirje dhe pagese shkon
# edhe ne fin_veprimet — jo per statistike, por qe te mund te kthehet mbrapsht.
#
# Shkrimi i ditarit nuk guxon ta rrezoje veprimin qe po dokumenton: nje pagese
# e bere mbetet e bere edhe nese ditari deshton. Por as nuk fshihet: deshtimi
# mbahet ketu dhe del te /shendeti dhe te alarmet e panelit.
PROBLEMET: List[dict] = []


def _shenoj_problem(mesazhi: str) -> None:
    """Mban problemet e heshtura te modulit, qe te mos mbeten te heshtura."""
    rresht = {"mesazhi": mesazhi,
              "kur": datetime.now(timezone.utc).isoformat()}
    PROBLEMET[:] = ([p for p in PROBLEMET if p["mesazhi"] != mesazhi]
                    + [rresht])[-10:]


def shkruaj_veprimin(veprimi: str, titulli: str, tabela: Optional[str] = None,
                     rreshti_id: Any = None, detaje: Any = None,
                     cilesimet: Optional[Dict[str, Any]] = None) -> None:
    """Le nje gjurme te veprimit, me daten dhe oren e sakte."""
    try:
        nr_i = int(rreshti_id) if rreshti_id is not None else None
    except (TypeError, ValueError):
        nr_i = None
    try:
        _sb("fin_veprimet", "post", trupi={
            "user_id": USER_ID,
            "kur": datetime.now(zona_e(cilesimet)).isoformat(),
            "veprimi": veprimi,
            "tabela": tabela,
            "rreshti_id": nr_i,
            "titulli": str(titulli)[:300],
            "detaje": detaje if isinstance(detaje, (dict, list)) else {},
        }, prefer="return=minimal")
    except HTTPException as e:
        teksti = str(e.detail)
        if "PGRST205" in teksti or "schema cache" in teksti:
            _shenoj_problem("Ditari i veprimeve mungon — ekzekuto "
                            "financat_migrim_7.sql ne Supabase.")
        else:
            _shenoj_problem(f"Ditari nuk u shkrua: {teksti[:160]}")
    except Exception as e:                                   # rrjet, JSON, …
        _shenoj_problem(f"Ditari nuk u shkrua: {type(e).__name__}: {e}"[:200])


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


def zona_e(cilesimet: Optional[Dict[str, Any]] = None) -> tzinfo:
    """Zona e perdoruesit nga cilesimet; nese emri s'njihet, UTC me nje shenim.

    Rrezimi i modulit per nje emer zone te shkruar gabim do te ishte i tepert —
    por heshtja do te ishte me e keqe, ndaj problemi mbahet dhe del te alarmet.
    """
    emri = str((cilesimet or {}).get("zona_kohore") or ZONA_PARAZGJEDHUR).strip()
    try:
        return ZoneInfo(emri)
    except (ZoneInfoNotFoundError, ValueError):
        pass
    try:
        return ZoneInfo(ZONA_PARAZGJEDHUR)
    except (ZoneInfoNotFoundError, ValueError):
        # Pa bazen e zonave (pakoja 'tzdata') mbetet vetem UTC.
        _shenoj_problem(f"Zona '{emri}' nuk njihet — orët shfaqen ne UTC.")
        return timezone.utc


def tani(cilesimet: Optional[Dict[str, Any]] = None) -> datetime:
    """Momenti i tanishem ne oren e perdoruesit."""
    return datetime.now(zona_e(cilesimet))


def _koh(x: Any) -> Optional[datetime]:
    """Lexon nje timestamp nga baza ose nga trupi i kerkeses."""
    if not x:
        return None
    if isinstance(x, datetime):
        return x
    teksti = str(x).strip().replace(" ", "T")
    # PostgREST kthen '+00:00' ose '+0000'; Python i do te dyja ndryshe.
    if teksti.endswith("Z"):
        teksti = teksti[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(teksti)
    except ValueError:
        return None


def _ore(x: Any) -> Optional[time]:
    """'14:30' ose '14:30:05' → ora. Cdo gje tjeter → None (pa ore te dhene)."""
    if x is None or isinstance(x, time):
        return x
    teksti = str(x).strip()
    if not teksti:
        return None
    copat = teksti.split(":")
    if not 2 <= len(copat) <= 3:
        return None
    try:
        h, m = int(copat[0]), int(copat[1])
        sek = int(float(copat[2])) if len(copat) == 3 else 0
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= sek <= 59):
        return None
    return time(h, m, sek)


def vula_e_kohes(trupi: dict, cilesimet: Optional[Dict[str, Any]] = None,
                 data_e_gatshme: Any = None) -> str:
    """Momenti i sakte i nje levizjeje, nga {kryer_me} ose nga {data, ora}.

    Rregulli: nese perdoruesi jep vetem daten, ora eshte ajo e momentit qe po
    e shkruan. Keshtu dy pagesa te te njejtes dite ruajne radhen e vertete,
    pa i kerkuar askujt te shtype nje ore.
    """
    z = zona_e(cilesimet)
    e_plote = _koh(trupi.get("kryer_me"))
    if e_plote:
        nese = e_plote if e_plote.tzinfo else e_plote.replace(tzinfo=z)
        return nese.astimezone(z).isoformat()
    tash = datetime.now(z)
    d = _dat(trupi.get("data")) or _dat(data_e_gatshme) or tash.date()
    o = _ore(trupi.get("ora")) or tash.time().replace(microsecond=0)
    return datetime.combine(d, o, tzinfo=z).isoformat()


def _shfaq_kohen(x: Any, cilesimet: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Timestamp → 'YYYY-MM-DD HH:MM' ne oren e perdoruesit."""
    d = _koh(x)
    if not d:
        return None
    if not d.tzinfo:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(zona_e(cilesimet)).strftime("%Y-%m-%d %H:%M")


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
    mungesat: List[str] = []
    return {
        "llogarite":     _lexo("fin_llogarite", {"aktiv": "eq.true"}, "id.asc"),
        "transaksionet": _lexo("fin_transaksionet", None, "data.desc", 2000),
        "detyrimet":     _lexo("fin_detyrimet", None, "afati.asc"),
        "planet":        _lexo("fin_planet", {"aktiv": "eq.true"}, "data_fillimit.asc"),
        "te_ardhurat":   _lexo("fin_te_ardhurat", {"aktiv": "eq.true"}, "id.asc"),
        "investimet":    _lexo("fin_investimet", {"aktiv": "eq.true"}, "id.asc"),
        "objektivat":    _lexo("fin_objektivat", None, "afati.asc"),
        "bizneset":      _lexo_nese_ekziston("fin_bizneset", {"aktiv": "eq.true"},
                                             "id.asc", mungesat),
        "biznes_zerat":  _lexo_nese_ekziston("fin_biznes_zerat", {"aktiv": "eq.true"},
                                             "id.asc", mungesat),
        "buxhetet":      _lexo_nese_ekziston("fin_buxhetet", {"aktiv": "eq.true"},
                                             "id.asc", mungesat),
        "personat":      _lexo_nese_ekziston("fin_personat", {"aktiv": "eq.true"},
                                             "id.asc", mungesat),
        "veprimet":      _lexo_nese_ekziston("fin_veprimet", None,
                                             "kur.desc", mungesat)[:40],
        "_mungojne":     mungesat,
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
        # Paraja e biznesit nuk eshte paraja jote: ajo hyn ne jeten tende
        # vetem si terheqje, e cila shenohet si e ardhur personale.
        if t.get("biznesi_id"):
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

    for tabela in g.get("_mungojne") or []:
        shto("paralajmerim", f"Tabela '{tabela}' mungon ne baze",
             f"Pjesa perkatese e faqes rri bosh derisa te krijohet.",
             f"Ekzekuto {MIGRIMET.get(tabela, 'migrimin perkates')} ne Supabase "
             f"→ SQL Editor.")

    for p in PROBLEMET:
        shto("paralajmerim", "Nje veprim nuk u regjistrua plotesisht",
             p["mesazhi"], "Shih /api/fin/shendeti per detajet.")

    rendi = {"kritik": 0, "paralajmerim": 1, "info": 2}
    return sorted(a, key=lambda x: rendi.get(x["niveli"], 3))


def _dita_e_muajit(dita: int, viti: int, muaji: int) -> date:
    """Dita e kerkuar e muajit, e kapur te dita e fundit (31 shkurt -> 28/29)."""
    return date(viti, muaji, min(max(1, dita), calendar.monthrange(viti, muaji)[1]))


def permbledh_shpenzimet(g: Dict[str, Any], c: Dict[str, Any],
                         rrj: Dict[str, Any], det: Dict[str, Any]) -> Dict[str, Any]:
    """Ku shkojne parat: totalet sipas llojit dhe sipas kategorise.

    Nje shpenzim vjetor nuk krahasohet dot me nje mujor pa u sjelle ne te
    njejten njesi — prandaj jepet edhe ekuivalenti mujor (vjetorja / 12).
    Kategorite nxirren nga transaksionet reale te 3 muajve te fundit te plote,
    jo nga planet: planet thone cfare duhet te ndodhe, transaksionet thone
    cfare ndodhi vertet.
    """
    sot = date.today()
    fikse_mujore = fikse_vjetore = te_tjera_mujore = 0.0
    numri = {"mujore": 0, "vjetore": 0, "te_tjera": 0}

    for p in g["planet"]:
        if not p.get("aktiv", True) or (p.get("drejtimi") or "dalje") != "dalje":
            continue
        mbarimi = _dat(p.get("data_mbarimit"))
        if mbarimi and mbarimi < sot:
            continue
        frek = (p.get("frekuenca") or "mujore").lower()
        shuma = kthe(p.get("shuma"), p.get("monedha"), c)
        prob = min(max(_num(p.get("probabiliteti"), 100), 0.0), 100.0) / 100.0
        if frek == "mujore":
            fikse_mujore += shuma * prob
            numri["mujore"] += 1
        elif frek == "vjetore":
            fikse_vjetore += shuma * prob
            numri["vjetore"] += 1
        elif frek != "nje_here":
            te_tjera_mujore += shuma * HERE_NE_MUAJ.get(frek, 1.0) * prob
            numri["te_tjera"] += 1

    # ── Sipas kategorise: mesatarja mujore e 3 muajve te fundit te plote ──
    kova: Dict[str, Dict[str, float]] = {}
    muajt_e_pare = set()
    for t in g["transaksionet"]:
        if (t.get("lloji") or "dalje").lower() != "dalje":
            continue
        if t.get("biznesi_id"):
            continue                      # shpenzim biznesi, jo personal
        d = _dat(t.get("data"))
        if not d or d > sot:
            continue
        muaji = f"{d.year:04d}-{d.month:02d}"
        if muaji == f"{sot.year:04d}-{sot.month:02d}":
            continue                      # muaji rrjedhes eshte i paplote
        if (sot - d).days > 130:
            continue
        muajt_e_pare.add(muaji)
        kat = (t.get("kategoria") or "tjeter").strip().lower()
        kova.setdefault(kat, {})
        kova[kat][muaji] = (kova[kat].get(muaji, 0.0)
                            + kthe(t.get("shuma"), t.get("monedha"), c))

    nr_muajsh = max(1, len(muajt_e_pare))
    muaji_i_fundit = max(muajt_e_pare) if muajt_e_pare else None
    kategorite = []
    for kat, m in kova.items():
        vlerat = list(m.values())
        # Mediana eshte baza, jo mesatarja: nje muaj i vetem me nje blerje te
        # madhe nuk duhet ta ngreje pragun perballe te cilit matet muaji tjeter.
        mediana = statistics.median(vlerat) if vlerat else 0.0
        e_fundit = m.get(muaji_i_fundit, 0.0)
        kategorite.append({
            "kategoria": kat,
            "mujore_baze": _rrum(sum(vlerat) / nr_muajsh),
            "mediana": _rrum(mediana),
            "muaji_i_fundit": _rrum(e_fundit),
            "teprica": _rrum(max(0.0, e_fundit - mediana)),
            "muaj_me_shpenzim": len(m),
            "e_domosdoshme": kat in KATEGORI_TE_DOMOSDOSHME,
        })
    kategorite.sort(key=lambda x: -x["mujore_baze"])
    totali_kategorive = sum(k["mujore_baze"] for k in kategorite) or 1.0
    for k in kategorite:
        k["pjesa"] = _rrum(k["mujore_baze"] / totali_kategorive * 100, 1)

    vjetore_ne_muaj = fikse_vjetore / 12.0
    totali_mujor = (fikse_mujore + vjetore_ne_muaj + te_tjera_mujore
                    + rrj["dalje_baze_mujore"] + det["kestet_mujore"])

    return {
        "fikse_mujore": _rrum(fikse_mujore), "nr_fikse_mujore": numri["mujore"],
        "fikse_vjetore": _rrum(fikse_vjetore), "nr_fikse_vjetore": numri["vjetore"],
        "vjetore_ne_muaj": _rrum(vjetore_ne_muaj),
        "te_tjera_mujore": _rrum(te_tjera_mujore), "nr_te_tjera": numri["te_tjera"],
        "ditore_baze": rrj["dalje_baze_mujore"],
        "kestet": det["kestet_mujore"],
        "totali_mujor": _rrum(totali_mujor),
        "totali_vjetor": _rrum(totali_mujor * 12),
        "sipas_kategorise": kategorite[:20],
        "muaj_te_analizuar": len(muajt_e_pare),
        "muaji_i_fundit": muaji_i_fundit,
    }


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


def gjej_paret(shpenzimet: Dict[str, Any], g: Dict[str, Any],
               c: Dict[str, Any]) -> List[dict]:
    """Nga mund te dalin para pa i prishur jetes.

    Dy burime, te renditura sipas sigurise:
      1. Teprica — sa e kaloi nje kategori medianen e vet muajin e fundit.
         Kthimi te mesatarja jote nuk eshte sakrifice, eshte korrigjim.
      2. Kategorite e zgjedhura (jo te domosdoshme) — deri ne 30% e tyre.
         Nje limit, jo nje premtim: askush nuk e pret argetimin ne zero.
    Planet me domosdoshmeri 4-5 (deshire, luks) shtohen te dyta, te plota —
    ato i ke shenuar vete si te shtyshme.
    """
    burimet: List[dict] = []
    for k in shpenzimet["sipas_kategorise"]:
        if k["teprica"] > 0 and k["mediana"] > 0:
            burimet.append({
                "burimi": k["kategoria"], "shuma": k["teprica"],
                "lloji": "teprice",
                "shpjegim": (f"muajin e fundit {k['muaji_i_fundit']:.0f} kundrejt "
                             f"{k['mediana']:.0f} qe eshte mesatarja jote"),
                "siguria": "e larte",
            })
        if not k["e_domosdoshme"] and k["mediana"] > 0:
            mundshme = k["mediana"] * 0.30
            if mundshme >= 1:
                burimet.append({
                    "burimi": k["kategoria"], "shuma": _rrum(mundshme),
                    "lloji": "shkurtim",
                    "shpjegim": "30% e nje kategorie qe nuk eshte e domosdoshme",
                    "siguria": "mesatare",
                })

    sot = date.today()
    for p in g["planet"]:
        if not p.get("aktiv", True) or (p.get("drejtimi") or "dalje") != "dalje":
            continue
        if int(_num(p.get("domosdoshmeria"), 3)) < 4:
            continue
        mbarimi = _dat(p.get("data_mbarimit"))
        if mbarimi and mbarimi < sot:
            continue
        frek = (p.get("frekuenca") or "mujore").lower()
        mujore = (kthe(p.get("shuma"), p.get("monedha"), c)
                  * HERE_NE_MUAJ.get(frek, 1.0))
        if mujore >= 1:
            burimet.append({
                "burimi": p.get("emri") or "Plan",
                "shuma": _rrum(mujore), "lloji": "plan_i_shtyshem",
                "shpjegim": f"e ke shenuar vete si domosdoshmeri "
                            f"{int(_num(p.get('domosdoshmeria'), 3))} nga 5",
                "siguria": "e larte",
            })

    rendi = {"teprice": 0, "plan_i_shtyshem": 1, "shkurtim": 2}
    burimet.sort(key=lambda b: (rendi.get(b["lloji"], 3), -b["shuma"]))
    return burimet


def keshillo_objektivin(o: dict, c: Dict[str, Any], arka: Dict[str, Any],
                        det: Dict[str, Any], skor: Dict[str, Any]) -> Dict[str, Any]:
    """Nga nje shifer synimi te nje plan i zbatueshem.

    Rendi qe ndiqet eshte ai standard i planifikimit personal: rezerve
    minimale -> borxh me interes te larte -> objektivat e tjera. Nje objektiv
    qe e shkel ate rend nuk ndalohet — i thuhet cmimi.

    'arka' mbahet e perbashket dhe zbritet: dy objektiva nuk mund te
    premtojne te njejtat para. Ai i pari ne rradhe e merr i pari.
    """
    mbetur = max(0.0, o["synim"] - o["aktuale"])
    mbetur_baze = kthe(mbetur, o.get("monedha"), c)
    muaj = o.get("muaj_mbetur")
    ne_dispozicion = max(0.0, arka["rrjedha"])
    burimet = [b for b in arka["burimet"] if b["mbetur"] > 0.5]
    potenciali = sum(b["mbetur"] for b in burimet)

    if mbetur_baze <= 0:
        return {"verdikti": "arritur", "arsyeja": "Objektivi eshte mbushur.",
                "kerkon_ne_muaj": 0, "ne_dispozicion": _rrum(ne_dispozicion),
                "hapat": [], "konfliktet": []}

    kerkon = mbetur_baze / muaj if muaj else None

    # ── Konfliktet me rendin e prioriteteve ─────────────────────────────
    konfliktet = []
    if skor["muaj_mbulimi"] < 1 and (o.get("lloji") or "") != "rezerve":
        konfliktet.append({
            "niveli": "ndal",
            "teksti": (f"Rezerva mbulon vetem {skor['muaj_mbulimi']:.1f} muaj "
                       f"shpenzime. Nje muaj rezerve vjen para cdo objektivi "
                       f"tjeter — pa te, nje defekt makine e kthen kete plan "
                       f"ne borxh te ri.")})
    borxhe_te_shtrenjta = [b for b in det["borxhe"] if b["interesi_vjetor"] >= 8]
    if borxhe_te_shtrenjta and (o.get("lloji") or "") != "shlyerje_borxhi":
        me_i_keqi = max(borxhe_te_shtrenjta, key=lambda b: b["interesi_vjetor"])
        kosto_vjetore = mbetur_baze * me_i_keqi["interesi_vjetor"] / 100.0
        konfliktet.append({
            "niveli": "kujdes",
            "teksti": (f"Ke {me_i_keqi['mbetur']:.0f} {me_i_keqi['monedha']} borxh "
                       f"me {me_i_keqi['interesi_vjetor']:.2f}% te {me_i_keqi['pala']}. "
                       f"Cdo {mbetur_baze:.0f} {c['monedha_baze']} qe shkojne ketu "
                       f"e jo atje te kushtojne rreth {kosto_vjetore:.0f} "
                       f"{c['monedha_baze']} interes ne vit. Shlyerja e borxhit "
                       f"eshte kthim i garantuar prej {me_i_keqi['interesi_vjetor']:.2f}%.")})

    # ── Hapat ───────────────────────────────────────────────────────────
    hapat = []
    nga_rrjedha = min(ne_dispozicion, kerkon) if kerkon else ne_dispozicion
    if nga_rrjedha > 0:
        arka["rrjedha"] -= nga_rrjedha          # keto para tani jane te zena
        hapat.append({"veprimi": "Nga rrjedha aktuale",
                      "shuma_mujore": _rrum(nga_rrjedha),
                      "shpjegim": "ajo qe te mbetet sot pas gjithe shpenzimeve"})
    nevoja = (kerkon - nga_rrjedha) if kerkon else 0.0
    if nevoja > 0:
        mbledhur = 0.0
        for b in burimet:
            if mbledhur >= nevoja - 0.5:
                break
            merret = min(b["mbetur"], nevoja - mbledhur)
            b["mbetur"] -= merret
            mbledhur += merret
            hapat.append({"veprimi": f"Shkurto: {b['burimi']}",
                          "shuma_mujore": _rrum(merret),
                          "shpjegim": b["shpjegim"]})

    # ── Verdikti ────────────────────────────────────────────────────────
    mundesia = ne_dispozicion + potenciali
    if not muaj:
        muaj_realist = (mbetur_baze / mundesia) if mundesia > 0 else None
        verdikti = "pa afat"
        arsyeja = (f"Pa afat te caktuar. Me {mundesia:.0f} {c['monedha_baze']} "
                   f"ne muaj do te donte rreth {muaj_realist:.0f} muaj."
                   if muaj_realist else
                   "Pa afat dhe pa rrjedhe pozitive — ky objektiv nuk levizet dot.")
    elif kerkon <= ne_dispozicion:
        verdikti = "i arritshem"
        arsyeja = (f"Kerkon {kerkon:.0f} {c['monedha_baze']} ne muaj dhe te "
                   f"mbeten {ne_dispozicion:.0f}. Nuk kerkon asnje ndryshim.")
    elif kerkon <= mundesia:
        verdikti = "me sakrifice"
        arsyeja = (f"Kerkon {kerkon:.0f} {c['monedha_baze']} ne muaj; te mbeten "
                   f"{ne_dispozicion:.0f}. Diferenca prej {nevoja:.0f} duhet gjetur "
                   f"nga shkurtimet me poshte.")
    else:
        muaj_realist = (mbetur_baze / mundesia) if mundesia > 0 else None
        verdikti = "duhet shtyre"
        arsyeja = (f"Kerkon {kerkon:.0f} {c['monedha_baze']} ne muaj, por edhe me "
                   f"te gjitha shkurtimet arrihen {mundesia:.0f}. "
                   + (f"Me kete ritem afati realist eshte rreth "
                      f"{muaj_realist:.0f} muaj, jo {muaj}."
                      if muaj_realist else
                      "Pa te ardhura shtese ky objektiv nuk levizet."))

    # "te mbeten 0" nuk shpjegohet vetvetiu — thuaje kush i mori.
    if arka["te_zena"] > 0.5 and ne_dispozicion < 1:
        arsyeja += (f" Rrjedha mujore eshte zene tashme nga objektivat me "
                    f"prioritet me te larte ({arka['te_zena']:.0f} "
                    f"{c['monedha_baze']}/muaj).")

    data_realiste = None
    if mundesia > 0:
        muaj_r = max(1, round(mbetur_baze / mundesia))
        if muaj_r <= 600:
            data_realiste = _shto_muaj(date.today(), muaj_r).isoformat()

    return {
        "verdikti": verdikti, "arsyeja": arsyeja,
        "kerkon_ne_muaj": _rrum(kerkon) if kerkon else None,
        "ne_dispozicion": _rrum(ne_dispozicion),
        "i_zene_nga_te_tjeret": arka["te_zena"] > 0,
        "potenciali_i_shkurtimeve": _rrum(potenciali),
        "mungesa": _rrum(max(0.0, nevoja)),
        "data_realiste": data_realiste,
        "hapat": hapat, "konfliktet": konfliktet,
    }


def _ne_muaj(shuma: float, frekuenca: Optional[str]) -> float:
    """Cdo shifer sillet ne muaj — perndryshe nje kosto vjetore duket e vogel."""
    f = (frekuenca or "mujore").lower()
    if f == "vjetore":
        return shuma / 12.0
    return shuma * HERE_NE_MUAJ.get(f, 1.0) if f in HERE_NE_MUAJ else shuma


def analizo_bizneset(g: Dict[str, Any], c: Dict[str, Any]) -> List[dict]:
    """Nje pasqyre fitimi per cdo biznes, plus pika e barazimit.

    Pika e barazimit eshte numri qe i mungon shumices se bizneseve te vogla:
    sa njesi duhen shitur qe kostot fikse te mbulohen. Llogaritet mbi marzhin
    e kontributit (te ardhura minus kosto variabile), jo mbi te ardhurat bruto
    — perndryshe del gjithmone me e ulet se sa eshte vertet.

    Fitimi i biznesit NUK hyn te te ardhurat e tua: hyn vetem terheqja, dhe
    vetem pasi ta shenosh si te ardhur personale.
    """
    sot = date.today()
    dalja: List[dict] = []

    for b in g["bizneset"]:
        bid = int(b["id"])
        zerat = [z for z in g["biznes_zerat"]
                 if str(z.get("biznesi_id")) == str(bid) and z.get("aktiv", True)]

        te_ardhura = kosto_fikse = kosto_var = 0.0
        njesite = 0.0
        rreshtat = {"te_ardhur": [], "kosto_fikse": [], "kosto_variabile": []}

        for z in zerat:
            if (z.get("lloji") or "") != "te_ardhur":
                continue
            sasia = _num(z.get("sasia"))
            shuma = (_num(z.get("cmimi_njesi")) * sasia if sasia > 0
                     else _num(z.get("shuma")))
            mujore = _ne_muaj(kthe(shuma, z.get("monedha"), c), z.get("frekuenca"))
            te_ardhura += mujore
            njesite += sasia
            rreshtat["te_ardhur"].append({
                "id": z["id"], "emri": z.get("emri"), "mujore": _rrum(mujore),
                "sasia": sasia, "cmimi_njesi": _num(z.get("cmimi_njesi")),
                "monedha": (z.get("monedha") or c["monedha_baze"]).upper()})

        for z in zerat:
            lloji = z.get("lloji") or ""
            if lloji == "kosto_fikse":
                mujore = _ne_muaj(kthe(z.get("shuma"), z.get("monedha"), c),
                                  z.get("frekuenca"))
                kosto_fikse += mujore
                rreshtat["kosto_fikse"].append({
                    "id": z["id"], "emri": z.get("emri"), "mujore": _rrum(mujore),
                    "frekuenca": z.get("frekuenca"),
                    "kategoria": z.get("kategoria")})
            elif lloji == "kosto_variabile":
                # Kosto per njesi: nese zeri ka sasine e vet, perdoret ajo;
                # perndryshe supozohet se vlen per te gjitha njesite e biznesit.
                sasia = _num(z.get("sasia")) or njesite
                mujore = (kthe(_num(z.get("kosto_per_njesi")) * sasia,
                               z.get("monedha"), c)
                          + te_ardhura * _num(z.get("perqindja")) / 100.0
                          + kthe(z.get("shuma"), z.get("monedha"), c))
                mujore = _ne_muaj(mujore, z.get("frekuenca"))
                kosto_var += mujore
                rreshtat["kosto_variabile"].append({
                    "id": z["id"], "emri": z.get("emri"), "mujore": _rrum(mujore),
                    "kosto_per_njesi": _num(z.get("kosto_per_njesi")),
                    "perqindja": _num(z.get("perqindja"))})

        marzhi = te_ardhura - kosto_var
        marzhi_perq = (marzhi / te_ardhura * 100) if te_ardhura > 0 else 0.0
        fitimi = marzhi - kosto_fikse
        terheqja = kthe(b.get("terheqje_mujore"), b.get("monedha"), c)

        barazimi_te_ardhura = (kosto_fikse / (marzhi_perq / 100)
                               if marzhi_perq > 0 else None)
        cmimi_mesatar = (te_ardhura / njesite) if njesite > 0 else None
        barazimi_njesi = (barazimi_te_ardhura / cmimi_mesatar
                          if barazimi_te_ardhura and cmimi_mesatar else None)
        siguria = ((te_ardhura - barazimi_te_ardhura) / te_ardhura * 100
                   if barazimi_te_ardhura and te_ardhura > 0 else None)

        # ── Sa ndodhi vertet: transaksionet e lidhura me kete biznes ────
        reale_hyrje = reale_dalje = 0.0
        muajt_reale = set()
        for t in g["transaksionet"]:
            if str(t.get("biznesi_id") or "") != str(bid):
                continue
            d = _dat(t.get("data"))
            if not d or d > sot or (sot - d).days > 130:
                continue
            if d.month == sot.month and d.year == sot.year:
                continue
            muajt_reale.add(f"{d.year:04d}-{d.month:02d}")
            vlera = kthe(t.get("shuma"), t.get("monedha"), c)
            if (t.get("lloji") or "dalje").lower() == "hyrje":
                reale_hyrje += vlera
            else:
                reale_dalje += vlera
        nr = max(1, len(muajt_reale))

        alarme = []
        if te_ardhura <= 0:
            alarme.append({"niveli": "paralajmerim",
                           "teksti": "Asnje e ardhur e regjistruar — pa to nuk "
                                     "llogaritet dot as fitimi as pika e barazimit."})
        if fitimi < 0:
            alarme.append({"niveli": "kritik",
                           "teksti": f"Biznesi humbet {abs(fitimi):,.0f} "
                                     f"{c['monedha_baze']} ne muaj.".replace(",", ".")})
        if terheqja > max(0.0, fitimi) and terheqja > 0:
            alarme.append({"niveli": "kritik",
                           "teksti": f"Terheq {terheqja:,.0f} ne muaj por fitimi "
                                     f"eshte {fitimi:,.0f} — diferenca del nga "
                                     f"kapitali, jo nga puna.".replace(",", ".")})
        if siguria is not None and 0 < siguria < 20:
            alarme.append({"niveli": "paralajmerim",
                           "teksti": f"Vetem {siguria:.0f}% mbi piken e barazimit: "
                                     f"nje rene e vogel e shitjeve e kthen ne humbje."})

        dalja.append({
            "id": bid, "emri": b.get("emri"), "njesia": b.get("njesia") or "njesi",
            "monedha": (b.get("monedha") or c["monedha_baze"]).upper(),
            "te_ardhura_mujore": _rrum(te_ardhura),
            "kosto_fikse_mujore": _rrum(kosto_fikse),
            "kosto_variabile_mujore": _rrum(kosto_var),
            "marzhi_kontributit": _rrum(marzhi),
            "marzhi_perqind": _rrum(marzhi_perq, 1),
            "fitimi_mujor": _rrum(fitimi),
            "fitimi_vjetor": _rrum(fitimi * 12),
            "marzhi_neto_perqind": _rrum(fitimi / te_ardhura * 100, 1)
                                   if te_ardhura > 0 else None,
            "njesite": _rrum(njesite, 2),
            "cmimi_mesatar": _rrum(cmimi_mesatar) if cmimi_mesatar else None,
            "barazimi_te_ardhura": _rrum(barazimi_te_ardhura)
                                   if barazimi_te_ardhura else None,
            "barazimi_njesi": _rrum(barazimi_njesi, 1) if barazimi_njesi else None,
            "siguria_perqind": _rrum(siguria, 1) if siguria is not None else None,
            "terheqje_mujore": _rrum(terheqja),
            "mbetet_ne_biznes": _rrum(fitimi - terheqja),
            "reale_hyrje_mujore": _rrum(reale_hyrje / nr),
            "reale_dalje_mujore": _rrum(reale_dalje / nr),
            "muaj_reale": len(muajt_reale),
            "zerat": rreshtat, "alarme": alarme,
        })

    return dalja



def llogarit_buxhetet(g: Dict[str, Any], c: Dict[str, Any],
                      shpenzimet: Dict[str, Any]) -> Dict[str, Any]:
    """Sa ke harxhuar nga cdo buxhet — dhe a je brenda ritmit.

    Nje shirit qe thote vetem "78% e perdorur" genjen ne daten 5 dhe qeteson
    ne daten 28. Prandaj krahasimi behet me ritmin e pritur: me 18 shtator
    duhen harxhuar rreth 60% e muajit. Mbi ate del 'mbi ritem', dhe
    projeksioni tregon ku mbaron muaji me kete ritem.
    """
    sot = date.today()
    ditet_e_muajit = calendar.monthrange(sot.year, sot.month)[1]
    pjesa_e_kaluar = sot.day / ditet_e_muajit

    harxhuar: Dict[str, float] = {}
    for t in g["transaksionet"]:
        if (t.get("lloji") or "dalje").lower() != "dalje" or t.get("biznesi_id"):
            continue
        d = _dat(t.get("data"))
        if not d or d.year != sot.year or d.month != sot.month:
            continue
        kat = (t.get("kategoria") or "tjeter").strip().lower()
        harxhuar[kat] = harxhuar.get(kat, 0.0) + kthe(t.get("shuma"), t.get("monedha"), c)

    rreshtat = []
    for b in g["buxhetet"]:
        kat = (b.get("kategoria") or "").strip().lower()
        buxheti = kthe(b.get("shuma_mujore"), b.get("monedha"), c)
        perdorur = harxhuar.get(kat, 0.0)
        perqind = (perdorur / buxheti * 100) if buxheti > 0 else 0.0
        pritej = buxheti * pjesa_e_kaluar
        projeksioni = (perdorur / pjesa_e_kaluar) if pjesa_e_kaluar > 0 else perdorur
        prag = int(_num(b.get("pragu_alarmit"), 85))

        if perqind > 100.5:
            gjendja = "kaluar"
        elif projeksioni > buxheti * 1.05:
            gjendja = "mbi_ritem"
        elif perqind >= prag:
            gjendja = "afer"
        else:
            gjendja = "brenda"

        rreshtat.append({
            "id": b.get("id"), "kategoria": kat,
            "buxheti": _rrum(buxheti), "perdorur": _rrum(perdorur),
            "mbetur": _rrum(buxheti - perdorur), "perqind": _rrum(perqind, 1),
            "pritej_deri_sot": _rrum(pritej),
            "projeksioni_i_muajit": _rrum(projeksioni),
            "gjendja": gjendja, "pragu": prag,
            "monedha": (b.get("monedha") or c["monedha_baze"]).upper(),
        })

    # Kategorite me shpenzim te ndjeshem qe s'kane buxhet ende — propozohet
    # mediana e tyre, sepse ajo eshte sjellja jote, jo nje shifer e shpikur.
    me_buxhet = {r["kategoria"] for r in rreshtat}
    propozime = [{"kategoria": k["kategoria"], "shuma_mujore": k["mediana"]}
                 for k in shpenzimet["sipas_kategorise"]
                 if k["kategoria"] not in me_buxhet and k["mediana"] >= 1]

    rendi = {"kaluar": 0, "mbi_ritem": 1, "afer": 2, "brenda": 3}
    rreshtat.sort(key=lambda r: (rendi.get(r["gjendja"], 4), -r["perqind"]))
    return {
        "rreshtat": rreshtat,
        "totali_buxheteve": _rrum(sum(r["buxheti"] for r in rreshtat)),
        "totali_perdorur": _rrum(sum(r["perdorur"] for r in rreshtat)),
        "dita": sot.day, "ditet_e_muajit": ditet_e_muajit,
        "pjesa_e_kaluar": _rrum(pjesa_e_kaluar * 100, 1),
        "propozime": propozime[:12],
    }


def levizjet_e_fundit(g: Dict[str, Any], c: Dict[str, Any], sa: int = 25) -> List[dict]:
    """Ditari: cdo levizje e fundit, me emer llogarie, personi dhe burimi.

    Pa kete, nje pagese e bere nga njoftimet zhdukej: shifra levizte diku ne
    total, por nuk dukej ku u shkrua dhe si te ndryshohej.
    """
    emrat_e_llogarive = {int(l["id"]): l.get("emri") for l in g["llogarite"]}
    emrat_e_personave = {int(p["id"]): p.get("emri") for p in g.get("personat") or []}
    emrat_e_planeve = {int(p["id"]): p.get("emri") for p in g["planet"]}
    emrat_e_ardhurave = {int(a["id"]): a.get("emri") for a in g["te_ardhurat"]}
    emrat_e_detyrimeve = {int(d["id"]): d.get("pala") for d in g["detyrimet"]}
    emrat_e_bizneseve = {int(b["id"]): b.get("emri") for b in g.get("bizneset") or []}

    def _emri(harta: dict, vlera: Any) -> Optional[str]:
        try:
            return harta.get(int(vlera)) if vlera is not None else None
        except (TypeError, ValueError):
            return None

    rreshtat = []
    for t in g["transaksionet"][:sa * 3]:
        d = _dat(t.get("data"))
        # Momenti i sakte ekziston vetem pas migrimit 7; para tij mbetet data.
        vula = _shfaq_kohen(t.get("kryer_me"), c)
        lloji = (t.get("lloji") or "dalje").lower()
        burimi = (_emri(emrat_e_ardhurave, t.get("te_ardhura_id"))
                  or _emri(emrat_e_planeve, t.get("plani_id"))
                  or _emri(emrat_e_detyrimeve, t.get("detyrimi_id")))
        rreshtat.append({
            "id": t.get("id"), "data": d.isoformat() if d else None,
            "kryer_me": t.get("kryer_me"),
            "ora": vula[11:] if vula else None,
            "lloji": lloji,
            "shuma": _num(t.get("shuma")),
            "monedha": (t.get("monedha") or c["monedha_baze"]).upper(),
            "ne_baze": _rrum(kthe(t.get("shuma"), t.get("monedha"), c)),
            "kategoria": t.get("kategoria"),
            "pershkrimi": t.get("pershkrimi"),
            "llogaria": _emri(emrat_e_llogarive, t.get("llogaria_id")),
            "personi": _emri(emrat_e_personave, t.get("personi_id")),
            "biznesi": _emri(emrat_e_bizneseve, t.get("biznesi_id")),
            "burimi": burimi,
        })
    # Radha brenda dites tani ka kuptim: ora e vendos, jo id-ja e rastit.
    rreshtat.sort(key=lambda r: (r["data"] or "", r["ora"] or "", r["id"] or 0),
                  reverse=True)
    return rreshtat[:sa]


VEPRIMET_NE_SHQIP = {
    "shtim": "Shtim", "ndryshim": "Ndryshim", "fshirje": "Fshirje",
    "pagese": "Pagese", "shlyerje": "Shlyerje", "cilesime": "Cilesime",
    "buxhete": "Buxhete", "keshillim": "Keshilltari", "skanim": "Skanim tregu",
    "cmime": "Cmime tregu", "eksport": "Eksport",
}


def permbledh_veprimet(g: Dict[str, Any], c: Dict[str, Any],
                       sa: int = 25) -> List[dict]:
    """Ditari: cfare u be, kur sakte, dhe mbi cilin rresht.

    Ndryshe nga levizjet (qe tregojne parane), ketu duket VEPRIMI — perfshire
    ndryshimet dhe fshirjet, qe nuk lene asnje transaksion pas vetes.
    """
    rreshtat = []
    for v in (g.get("veprimet") or [])[:sa]:
        kur = _shfaq_kohen(v.get("kur"), c)
        rreshtat.append({
            "id": v.get("id"),
            "kur": v.get("kur"),
            "data": kur[:10] if kur else None,
            "ora": kur[11:] if kur else None,
            "veprimi": v.get("veprimi"),
            "veprimi_shqip": VEPRIMET_NE_SHQIP.get(v.get("veprimi"),
                                                   v.get("veprimi")),
            "tabela": v.get("tabela"),
            "rreshti_id": v.get("rreshti_id"),
            "titulli": v.get("titulli"),
        })
    return rreshtat


def levizja_e_radhes(g: Dict[str, Any], c: Dict[str, Any],
                     det: Dict[str, Any]) -> Optional[dict]:
    """Cfare pritet te levize me pare — dhe per sa dite.

    Shikohen te ardhurat me date, planet e perseritshme me date, planet nje-here,
    dhe afatet e borxheve. Fitues eshte data me e afert qe s'ka kaluar.
    """
    sot = date.today()
    kandidatet: List[dict] = []

    def _dita_tjeter(dita: int) -> Optional[date]:
        if dita <= 0:
            return None
        e_ketij_muaji = _dita_e_muajit(dita, sot.year, sot.month)
        if e_ketij_muaji >= sot:
            return e_ketij_muaji
        pasardhes = _shto_muaj(sot, 1)
        return _dita_e_muajit(dita, pasardhes.year, pasardhes.month)

    for a in g["te_ardhurat"]:
        d = _dita_tjeter(int(_num(a.get("dita_pageses"), 0)))
        if not d:
            continue
        e_ndryshueshme = bool(a.get("shuma_e_ndryshueshme"))
        kandidatet.append({
            "emri": a.get("emri"), "drejtimi": "hyrje", "data": d,
            "shuma": kthe(a.get("shuma_mujore"), a.get("monedha"), c),
            "monedha": (a.get("monedha") or c["monedha_baze"]).upper(),
            "shuma_vendase": _num(a.get("shuma_mujore")),
            "fikse": not e_ndryshueshme, "burimi": "te ardhur"})

    for p in g["planet"]:
        if not p.get("aktiv", True):
            continue
        frek = (p.get("frekuenca") or "mujore").lower()
        mbarimi = _dat(p.get("data_mbarimit"))
        if mbarimi and mbarimi < sot:
            continue
        if frek == "nje_here":
            d = _dat(p.get("data_fillimit"))
            if not d or d < sot:
                continue
        elif frek == "vjetore":
            muaji = int(_num(p.get("muaji_pageses"), 0))
            dita = int(_num(p.get("dita_pageses"), 0))
            if muaji < 1 or dita < 1:
                continue
            viti = sot.year if (muaji, dita) >= (sot.month, sot.day) else sot.year + 1
            d = _dita_e_muajit(dita, viti, muaji)
        else:
            d = _dita_tjeter(int(_num(p.get("dita_pageses"), 0)))
        if not d:
            continue
        kandidatet.append({
            "emri": p.get("emri"),
            "drejtimi": (p.get("drejtimi") or "dalje"), "data": d,
            "shuma": kthe(p.get("shuma"), p.get("monedha"), c),
            "monedha": (p.get("monedha") or c["monedha_baze"]).upper(),
            "shuma_vendase": _num(p.get("shuma")),
            "fikse": int(_num(p.get("probabiliteti"), 100)) >= 100,
            "burimi": "plan"})

    for b in det["borxhe"] + det["arketime"]:
        d = _dat(b.get("afati"))
        if not d or d < sot:
            continue
        kandidatet.append({
            "emri": b.get("pala"),
            "drejtimi": "dalje" if b in det["borxhe"] else "hyrje", "data": d,
            "shuma": b["mbetur_baze"], "monedha": b["monedha"],
            "shuma_vendase": b["mbetur"], "fikse": True, "burimi": "detyrim"})

    if not kandidatet:
        return None
    i_pari = min(kandidatet, key=lambda x: x["data"])
    dite = (i_pari["data"] - sot).days
    return {
        "emri": i_pari["emri"], "drejtimi": i_pari["drejtimi"],
        "data": i_pari["data"].isoformat(), "dite": dite,
        "shuma": _rrum(i_pari["shuma"]),
        "shuma_vendase": _rrum(i_pari["shuma_vendase"]),
        "monedha": i_pari["monedha"], "fikse": i_pari["fikse"],
        "burimi": i_pari["burimi"],
        "sa_shpejt": ("sot" if dite == 0 else "neser" if dite == 1
                      else f"per {dite} dite"),
    }


def permbledh_personat(g: Dict[str, Any], c: Dict[str, Any],
                       bil: Dict[str, Any]) -> List[dict]:
    """Kush sjell sa dhe kush shpenzon sa. Totali mbetet nje, por ka zberthim."""
    sot = date.today()
    personat = {int(p["id"]): {"id": int(p["id"]), "emri": p.get("emri"),
                               "te_ardhura_mujore": 0.0, "shpenzime_mujore": 0.0,
                               "bilanci": 0.0, "llogari": 0}
                for p in g.get("personat") or []}
    pa_person = {"id": None, "emri": "Pa person", "te_ardhura_mujore": 0.0,
                 "shpenzime_mujore": 0.0, "bilanci": 0.0, "llogari": 0}

    def kutia(vlera):
        try:
            return personat.get(int(vlera), pa_person) if vlera is not None else pa_person
        except (TypeError, ValueError):
            return pa_person

    vleresimet = vleresoj_te_ardhurat(g, c)
    for a in g["te_ardhurat"]:
        k = kutia(a.get("personi_id"))
        k["te_ardhura_mujore"] += vleresimet.get(int(a["id"]), {}).get("mujore_baze", 0.0)

    # Shpenzimet: mesatarja mujore e muajve te plote te fundit
    muajt: Dict[Any, set] = {}
    for t in g["transaksionet"]:
        if (t.get("lloji") or "dalje").lower() != "dalje" or t.get("biznesi_id"):
            continue
        d = _dat(t.get("data"))
        if not d or d > sot or (sot - d).days > 130:
            continue
        if d.year == sot.year and d.month == sot.month:
            continue
        k = kutia(t.get("personi_id"))
        k["shpenzime_mujore"] += kthe(t.get("shuma"), t.get("monedha"), c)
        muajt.setdefault(k["emri"], set()).add(f"{d.year:04d}-{d.month:02d}")

    for l, rr in zip(g["llogarite"], bil["llogarite"]):
        k = kutia(l.get("personi_id"))
        k["bilanci"] += rr["bilanci_baze"]
        k["llogari"] += 1

    dalja = []
    for k in list(personat.values()) + [pa_person]:
        nr = max(1, len(muajt.get(k["emri"], set())))
        k["shpenzime_mujore"] = _rrum(k["shpenzime_mujore"] / nr)
        k["te_ardhura_mujore"] = _rrum(k["te_ardhura_mujore"])
        k["bilanci"] = _rrum(k["bilanci"])
        k["neto_mujore"] = _rrum(k["te_ardhura_mujore"] - k["shpenzime_mujore"])
        if (k["te_ardhura_mujore"] or k["shpenzime_mujore"] or k["bilanci"]
                or k["llogari"]):
            dalja.append(k)
    return sorted(dalja, key=lambda x: -x["te_ardhura_mujore"])


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
    shpenzimet = permbledh_shpenzimet(g, c, rrj, det)
    buxhetet = llogarit_buxhetet(g, c, shpenzimet)
    for b in buxhetet["rreshtat"]:
        if b["gjendja"] == "kaluar":
            alarme.insert(0, {
                "niveli": "paralajmerim",
                "titulli": f"Buxheti i kaluar: {b['kategoria']}",
                "detaji": (f"{b['perdorur']:.0f} nga {b['buxheti']:.0f} "
                           f"{c['monedha_baze']} ({b['perqind']:.0f}%)."),
                "veprimi": "Ndalo ketu deri ne fund te muajit, ose ngrije buxhetin."})
        elif b["gjendja"] == "mbi_ritem":
            alarme.append({
                "niveli": "info",
                "titulli": f"Mbi ritem: {b['kategoria']}",
                "detaji": (f"Deri sot {b['perdorur']:.0f} nga {b['buxheti']:.0f}; "
                           f"me kete ritem muaji mbyllet me "
                           f"{b['projeksioni_i_muajit']:.0f}."),
                "veprimi": ""})


    sot = date.today()
    burimet_e_kursimit = gjej_paret(shpenzimet, g, c)
    # Objektivat konkurrojne per te njejtat para, ndaj shqyrtohen sipas
    # prioritetit (1 i pari) dhe pastaj sipas afatit me te afert.
    rendi_objektivave = sorted(
        g["objektivat"],
        key=lambda x: (int(_num(x.get("prioriteti"), 3)),
                       str(x.get("afati") or "9999-12-31")))
    arka = {"rrjedha": max(0.0, kap["per_kursim_mujor"]),
            "burimet": [dict(b, mbetur=b["shuma"]) for b in burimet_e_kursimit],
            "te_zena": 0.0}
    objektiva = []
    for o in rendi_objektivave:
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
        if not objektiva[-1]["arritur"]:
            para = arka["rrjedha"]
            objektiva[-1]["plani"] = keshillo_objektivin(
                objektiva[-1], c, arka, det, skor)
            arka["te_zena"] += para - arka["rrjedha"]

    tash = tani(c)
    return {
        "koha": tash.isoformat(),
        "koha_lokale": tash.strftime("%Y-%m-%d %H:%M"),
        "zona_kohore": str(c.get("zona_kohore") or ZONA_PARAZGJEDHUR),
        "monedha_baze": c["monedha_baze"],
        "cilesimet": c,
        "bilancet": bil, "rrjedha": rrj, "detyrimet": det, "investimet": inv,
        "projeksioni": proj, "skori": skor, "kapaciteti": kap,
        "shpenzimet": shpenzimet,
        "burimet_e_kursimit": burimet_e_kursimit,
        "levizjet": levizjet_e_fundit(g, c),
        "veprimet": permbledh_veprimet(g, c),
        "levizja_e_radhes": levizja_e_radhes(g, c, det),
        "personat": permbledh_personat(g, c, bil),
        "bizneset": analizo_bizneset(g, c),
        "buxhetet": buxhetet,
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


def _emri_i_rreshtit(rresht: Optional[dict]) -> str:
    """Nje emer i lexueshem per ditarin — jo nje id e thate."""
    for f in ("emri", "pala", "pershkrimi", "kategoria", "celes", "titulli"):
        v = (rresht or {}).get(f)
        if v not in (None, ""):
            return str(v)
    return f"#{(rresht or {}).get('id', '?')}"


def _me_kohen(tabela: str, trupi: dict, cilesimet: Dict[str, Any],
              ekzistues: Optional[dict] = None) -> dict:
    """Per transaksionet: {data, ora} → momenti i sakte 'kryer_me'.

    Ne nje ndryshim qe s'e prek oren, vula e vjeter nuk cenohet: nje korrigjim
    i shumes nuk duhet ta zhvendose pagesen ne oren kur e ndreqe.
    """
    if tabela != "transaksionet":
        return trupi
    t = dict(trupi or {})
    po_ndryshon = ekzistues is not None
    if po_ndryshon and not (t.get("ora") or t.get("kryer_me")):
        t.pop("ora", None)
        return t
    t["kryer_me"] = vula_e_kohes(t, cilesimet, (ekzistues or {}).get("data"))
    t.pop("ora", None)
    return t


def _sb_me_kohe(tabela: str, metoda: str, params: Optional[dict] = None,
                trupi: Optional[dict] = None, prefer: Optional[str] = None):
    """Si _sb, por i duron bazat ku migrimi 7 s'eshte ekzekutuar ende.

    Nje kolone qe mungon nuk duhet ta ndaloje nje pagese; mungesa raportohet
    me emrin e skedarit qe e ndreq dhe rreshti shkruhet pa oren.
    """
    try:
        return _sb(tabela, metoda, params=params, trupi=trupi, prefer=prefer)
    except HTTPException as e:
        teksti = str(e.detail)
        if trupi and "kryer_me" in trupi and "kryer_me" in teksti:
            _shenoj_problem("Kolona 'kryer_me' mungon — ekzekuto "
                            "financat_migrim_7.sql ne Supabase qe levizjet "
                            "te ruajne edhe oren.")
            pa_ore = {k: v for k, v in trupi.items() if k != "kryer_me"}
            return _sb(tabela, metoda, params=params, trupi=pa_ore, prefer=prefer)
        raise


@router.get("/te-dhena/{tabela}")
def lexo_tabelen(tabela: str, kufi: int = Query(500, ge=1, le=5000),
                 rendit: Optional[str] = Query(None, pattern=r"^[a-z_]{1,40}\.(asc|desc)$"),
                 frekuenca: Optional[str] = Query(None, pattern=r"^[a-z_]{1,20}$"),
                 drejtimi: Optional[str] = Query(None, pattern=r"^(hyrje|dalje)$"),
                 lloji: Optional[str] = Query(None, pattern=r"^[a-z_]{1,20}$"),
                 biznesi_id: Optional[int] = Query(None, ge=1),
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
    if biznesi_id:
        filtra["biznesi_id"] = f"eq.{biznesi_id}"
    parazgjedhur = {"transaksionet": "data.desc", "raportet": "krijuar_me.desc"}
    return _lexo(_tabela(tabela), filtra or None,
                 rendit or parazgjedhur.get(tabela, "id.desc"), kufi)


@router.post("/te-dhena/{tabela}")
def shto_rresht(tabela: str, trupi: dict = Body(...),
                _: Optional[str] = Header(None, alias="X-Fin-Token")):
    kerko_token(_)
    c = lexo_cilesimet()
    rresht = _pastro(tabela, _me_kohen(tabela, trupi, c))
    rresht["user_id"] = USER_ID
    dalja = _sb_me_kohe(_tabela(tabela), "post", trupi=rresht,
                        prefer="return=representation")
    e_re = dalja[0] if isinstance(dalja, list) and dalja else dalja
    shkruaj_veprimin("shtim", f"Shtim te {tabela}: {_emri_i_rreshtit(e_re)}",
                     tabela, (e_re or {}).get("id"), rresht, c)
    return e_re


@router.patch("/te-dhena/{tabela}/{rreshti_id}")
def ndrysho_rresht(tabela: str, rreshti_id: int, trupi: dict = Body(...),
                   _: Optional[str] = Header(None, alias="X-Fin-Token")):
    kerko_token(_)
    c = lexo_cilesimet()
    # Rreshti i vjeter lexohet para ndryshimit: ditari mban edhe ate qe u
    # zhduk, jo vetem ate qe zuri vendin e tij.
    i_vjetri = (_lexo(_tabela(tabela), {"id": f"eq.{rreshti_id}"}) or [None])[0]
    rresht = _pastro(tabela, _me_kohen(tabela, trupi, c, i_vjetri or {}))
    dalja = _sb_me_kohe(_tabela(tabela), "patch",
                        params={"id": f"eq.{rreshti_id}", "user_id": f"eq.{USER_ID}"},
                        trupi=rresht, prefer="return=representation")
    if not dalja:
        raise HTTPException(404, f"Rreshti {rreshti_id} nuk u gjet ne '{tabela}'.")
    i_riu = dalja[0] if isinstance(dalja, list) else dalja
    shkruaj_veprimin("ndryshim",
                     f"Ndryshim te {tabela}: {_emri_i_rreshtit(i_riu)}",
                     tabela, rreshti_id,
                     {"i_ri": rresht,
                      "i_vjeter": {k: (i_vjetri or {}).get(k) for k in rresht}}, c)
    return i_riu


@router.delete("/te-dhena/{tabela}/{rreshti_id}")
def fshi_rresht(tabela: str, rreshti_id: int,
                _: Optional[str] = Header(None, alias="X-Fin-Token")):
    kerko_token(_)
    dalja = _sb(_tabela(tabela), "delete",
                params={"id": f"eq.{rreshti_id}", "user_id": f"eq.{USER_ID}"},
                prefer="return=representation")
    if not dalja:
        raise HTTPException(404, f"Rreshti {rreshti_id} nuk u gjet ne '{tabela}'.")
    i_fshiri = dalja[0] if isinstance(dalja, list) else dalja
    # Rreshti i plote ruhet ne ditar: nje fshirje e gabuar duhet te jete e
    # kthyeshme, jo nje humbje pa gjurme.
    shkruaj_veprimin("fshirje", f"Fshirje nga {tabela}: "
                                f"{_emri_i_rreshtit(i_fshiri)}",
                     tabela, rreshti_id, {"rreshti": i_fshiri})
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
    e_re = dalja[0] if isinstance(dalja, list) and dalja else dalja
    shkruaj_veprimin("shtim", "U krijua llogaria 'Kesh' (automatikisht)",
                     "llogarite", (e_re or {}).get("id"), e_re, c)
    return e_re


@router.post("/buxhete-nga-historiku")
def buxhete_nga_historiku(trupi: dict = Body(default={}),
                          _: Optional[str] = Header(None, alias="X-Fin-Token")):
    """Krijon buxhete per kategorite qe s'kane ende nje, me medianen e tyre.

    Mediana e sjelljes tende eshte pikenisja e vetme e ndershme: nje buxhet i
    shpikur nga ajri kalohet muajin e pare dhe braktiset muajin e dyte.
    Trupi opsional: {kategorite: ["ushqime", ...]} per te zgjedhur vetem disa.
    """
    kerko_token(_)
    p = ndertoj_panelin(3)
    propozime = p["buxhetet"]["propozime"]
    kerkuara = trupi.get("kategorite")
    if kerkuara:
        e_kerkuar = {str(k).strip().lower() for k in kerkuara}
        propozime = [x for x in propozime if x["kategoria"] in e_kerkuar]
    if not propozime:
        return {"krijuar": [], "shenim": "Asnje kategori pa buxhet."}

    krijuar = []
    for pr in propozime:
        rr = _sb("fin_buxhetet", "post", trupi={
            "user_id": USER_ID, "kategoria": pr["kategoria"],
            "shuma_mujore": pr["shuma_mujore"],
            "monedha": p["monedha_baze"], "aktiv": True,
        }, prefer="return=representation")
        if rr:
            krijuar.append(rr[0] if isinstance(rr, list) else rr)
    shkruaj_veprimin("buxhete",
                     f"U krijuan {len(krijuar)} buxhete nga historiku",
                     "buxhetet", None,
                     {"kategorite": [b.get("kategoria") for b in krijuar]})
    return {"krijuar": krijuar, "gjithsej": len(krijuar)}


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
    e_reja = lexo_cilesimet()
    shkruaj_veprimin("cilesime",
                     f"Cilesimet: {', '.join(sorted(trupi))}",
                     "cilesimet", None, {"vlerat_e_reja": trupi}, e_reja)
    return e_reja


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
    # Data dhe ora vijne nga i njejti moment — s'kane si te ndahen.
    vula = vula_e_kohes(trupi, c)
    rresht = {
        "user_id": USER_ID,
        "data": vula[:10],
        "kryer_me": vula,
        "lloji": drejtimi,
        "shuma": shuma,
        "monedha": (trupi.get("monedha") or burimi.get("monedha")
                    or c["monedha_baze"]).strip().upper(),
        "kategoria": (trupi.get("kategoria") or burimi.get("lloji")
                      or burimi.get("kategoria") or "tjeter"),
        "pershkrimi": trupi.get("pershkrimi") or burimi.get("emri"),
        "llogaria_id": trupi.get("llogaria_id") or burimi.get("llogaria_id"),
        "personi_id": trupi.get("personi_id") or burimi.get("personi_id"),
    }
    rresht["te_ardhura_id" if lloji == "te_ardhura" else "plani_id"] = burimi_id

    dalja = _sb_me_kohe("fin_transaksionet", "post", trupi=rresht,
                        prefer="return=representation")
    trx = dalja[0] if isinstance(dalja, list) and dalja else dalja
    shkruaj_veprimin(
        "pagese",
        f"{'Hyrje' if drejtimi == 'hyrje' else 'Pagese'} "
        f"{rresht['shuma']} {rresht['monedha']} — {rresht['pershkrimi']}",
        "transaksionet", (trx or {}).get("id"), rresht, c)
    return {"transaksioni": trx,
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
    shkruaj_veprimin("keshillim",
                     f"Keshilltari: {pyetja or 'lexim i pergjithshem'}",
                     "raportet", raporti_id,
                     {"internet": internet, "modeli": dalja["modeli"]})
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

    shkruaj_veprimin("skanim", f"Skanim tregu: {fokusi}", "raportet",
                     raporti_id, {"propozime": len(propozime)})
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
    shkruaj_veprimin("cmime",
                     f"U zbatuan {len(perditesuar)} cmime tregu mbi investimet",
                     "investimet", None,
                     {"cmimet": [c for c in lista if isinstance(c, dict)]})
    return {"perditesuar": perditesuar, "gjithsej": len(perditesuar)}


@router.post("/paguaj-borxh")
def paguaj_borxh(trupi: dict = Body(...),
                 _: Optional[str] = Header(None, alias="X-Fin-Token")):
    """Nje pagese borxhi ne nje hap: transaksioni, mbetja e re, dhe mbyllja.

    Deri tani duhej shenuar transaksioni nga njera ane dhe ndryshuar
    'shuma_paguar' nga tjetra — dy hapa qe harrohen lehte dhe qe, kur
    harrohen, e lene borxhin te dukej i papaguar.

    Trupi: {detyrimi_id, shuma, data, monedha, llogaria_id, personi_id}
    """
    kerko_token(_)
    try:
        detyrimi_id = int(trupi.get("detyrimi_id"))
    except (TypeError, ValueError):
        raise HTTPException(400, "detyrimi_id mungon ose s'eshte numer.")
    shuma = _num(trupi.get("shuma"))
    if shuma <= 0:
        raise HTTPException(400, "Shuma duhet me e madhe se zero.")

    rreshtat = _lexo("fin_detyrimet", {"id": f"eq.{detyrimi_id}"})
    if not rreshtat:
        raise HTTPException(404, f"Detyrimi {detyrimi_id} nuk u gjet.")
    d = rreshtat[0]
    c = lexo_cilesimet()

    # Pagesa mund te behet ne monedhe tjeter nga ajo e borxhit — sillet ne te.
    monedha_pageses = (trupi.get("monedha") or d.get("monedha")
                       or c["monedha_baze"]).strip().upper()
    kursi_borxhit = kursi_i(c, d.get("monedha")) or 1.0
    shuma_ne_borxh = kthe(shuma, monedha_pageses, c) / kursi_borxhit

    mbetur = _num(d.get("shuma_totale")) - _num(d.get("shuma_paguar"))
    if mbetur <= 0.005:
        raise HTTPException(400, "Ky detyrim eshte shlyer tashme.")
    if shuma_ne_borxh > mbetur + 0.005:
        raise HTTPException(400,
            f"Pagesa ({shuma_ne_borxh:.2f}) e kalon mbetjen ({mbetur:.2f} "
            f"{(d.get('monedha') or '').upper()}).")

    eshte_borxh = (d.get("lloji") or "borxh") == "borxh"
    vula = vula_e_kohes(trupi, c)
    trx = {
        "user_id": USER_ID,
        "data": vula[:10],
        "kryer_me": vula,
        "lloji": "dalje" if eshte_borxh else "hyrje",
        "shuma": shuma, "monedha": monedha_pageses,
        "kategoria": "shlyerje_borxhi" if eshte_borxh else "arketim",
        "pershkrimi": f"{'Pagese' if eshte_borxh else 'Arketim'}: {d.get('pala')}",
        "llogaria_id": trupi.get("llogaria_id"),
        "personi_id": trupi.get("personi_id") or d.get("personi_id"),
        "detyrimi_id": detyrimi_id,
    }
    dalja_trx = _sb_me_kohe("fin_transaksionet", "post", trupi=trx,
                            prefer="return=representation")

    paguar_e_re = _num(d.get("shuma_paguar")) + shuma_ne_borxh
    e_mbyllur = paguar_e_re >= _num(d.get("shuma_totale")) - 0.005
    perditesimi = {"shuma_paguar": round(paguar_e_re, 2)}
    if e_mbyllur:
        perditesimi["statusi"] = "shlyer"
    _sb("fin_detyrimet", "patch",
        params={"id": f"eq.{detyrimi_id}", "user_id": f"eq.{USER_ID}"},
        trupi=perditesimi, prefer="return=representation")

    rreshti_trx = (dalja_trx[0] if isinstance(dalja_trx, list) and dalja_trx
                   else dalja_trx)
    shkruaj_veprimin(
        "shlyerje",
        f"{'Pagese borxhi' if eshte_borxh else 'Arketim'} {shuma} "
        f"{monedha_pageses} — {d.get('pala')}"
        + (" (u shlye plotesisht)" if e_mbyllur else ""),
        "detyrimet", detyrimi_id,
        {"transaksioni_id": (rreshti_trx or {}).get("id"),
         "kryer_me": vula, "paguar_gjithsej": perditesimi["shuma_paguar"],
         "statusi": perditesimi.get("statusi", d.get("statusi"))}, c)

    return {
        "transaksioni": rreshti_trx,
        "mbetur": _rrum(max(0.0, mbetur - shuma_ne_borxh)),
        "monedha": (d.get("monedha") or c["monedha_baze"]).upper(),
        "shlyer": e_mbyllur,
        "mesazhi": ("Borxhi u shlye dhe doli nga lista."
                    if e_mbyllur else
                    f"Mbeten {mbetur - shuma_ne_borxh:.2f} "
                    f"{(d.get('monedha') or '').upper()}."),
    }


@router.get("/veprimet")
def veprimet(kufi: int = Query(100, ge=1, le=1000),
             _: Optional[str] = Header(None, alias="X-Fin-Token")):
    """Ditari i plote: cdo veprim me daten dhe oren e vet."""
    kerko_token(_)
    c = lexo_cilesimet()
    mungesat: List[str] = []
    rreshtat = _lexo_nese_ekziston("fin_veprimet", None, "kur.desc", mungesat)
    if mungesat:
        return {"veprimet": [], "gjithsej": 0,
                "shenim": "Ditari mungon — ekzekuto financat_migrim_7.sql."}
    g = {"veprimet": rreshtat}
    return {"veprimet": permbledh_veprimet(g, c, kufi), "gjithsej": len(rreshtat)}


@router.get("/raportet")
def raportet(kufi: int = Query(20, ge=1, le=100),
             _: Optional[str] = Header(None, alias="X-Fin-Token")):
    kerko_token(_)
    return _lexo("fin_raportet", None, "krijuar_me.desc", kufi)


# ==========================================================================
# KOPJA E SIGURT — te dhenat dalin nga aty ku hyne
# ==========================================================================
# Nje aplikacion qe mban gjithe jeten tende financiare duhet te te lejoje ta
# marresh ate jashte tij. Pa kete, cdo gabim i imi ose i Supabase-it eshte
# humbje e perhershme.
TABELAT_E_EKSPORTIT = ["llogarite", "transaksionet", "detyrimet", "planet",
                       "te-ardhurat", "investimet", "objektivat", "bizneset",
                       "zerat-e-biznesit", "buxhetet", "personat", "veprimet",
                       "raportet"]


@router.get("/eksport")
def eksport(_: Optional[str] = Header(None, alias="X-Fin-Token")):
    """Gjithcka ne nje skedar te vetem JSON, gati per t'u ruajtur."""
    kerko_token(_)
    tani = datetime.now(timezone.utc)
    dalja: Dict[str, Any] = {
        "_krijuar": tani.isoformat(),
        "_burimi": "financat", "_version": 1,
        "cilesimet": lexo_cilesimet(),
    }
    for emri in TABELAT_E_EKSPORTIT:
        try:
            dalja[emri] = _lexo(TABELAT[emri], None, "id.asc", 5000)
        except HTTPException as e:
            dalja[emri] = {"_gabim": str(e.detail)}
    emri_skedarit = f"financat-{tani.date().isoformat()}.json"
    shkruaj_veprimin("eksport", "Kopje e plote (JSON) u shkarkua", None, None,
                     {"skedari": emri_skedarit})
    return JSONResponse(dalja, headers={
        "Content-Disposition": f'attachment; filename="{emri_skedarit}"'})


@router.get("/eksport/{tabela}.csv")
def eksport_csv(tabela: str, _: Optional[str] = Header(None, alias="X-Fin-Token")):
    """Nje tabele e vetme si CSV — per Excel ose Sheets."""
    kerko_token(_)
    rreshtat = _lexo(_tabela(tabela), None, "id.asc", 5000)
    shkruaj_veprimin("eksport", f"CSV i '{tabela}' u shkarkua", tabela, None,
                     {"rreshta": len(rreshtat)})
    if not rreshtat:
        return PlainTextResponse("", headers={
            "Content-Disposition": f'attachment; filename="{tabela}.csv"'})
    # Kolonat mblidhen nga te gjithe rreshtat: nje rresht i vetem mund te mos
    # i kete te gjitha fushat opsionale.
    kolonat: List[str] = []
    for rr in rreshtat:
        for k in rr:
            if k not in kolonat:
                kolonat.append(k)
    buf = io.StringIO()
    shkruesi = csv.DictWriter(buf, fieldnames=kolonat, extrasaction="ignore")
    shkruesi.writeheader()
    for rr in rreshtat:
        shkruesi.writerow({k: ("" if rr.get(k) is None else rr.get(k))
                           for k in kolonat})
    return PlainTextResponse(buf.getvalue(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition":
                                      f'attachment; filename="{tabela}.csv"'})


@router.get("/shendeti")
def shendeti():
    """Pa token: thote vetem nese moduli eshte i konfiguruar, asnje te dhene."""
    return {
        "moduli": "financat",
        "supabase": bool(SUPABASE_SERVICE_KEY),
        "token_i_vendosur": bool(FIN_TOKEN),
        "keshilltari": bool(ANTHROPIC_API_KEY),
        "modeli": FIN_MODELI,
        "problemet": list(PROBLEMET),
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
