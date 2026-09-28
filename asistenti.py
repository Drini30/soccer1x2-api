"""
============================================================================
ASISTENTI — te kuptuarit e urdhrave te shkruar shqip
============================================================================
Ky skedar nuk prek kurre bazen e te dhenave dhe nuk therret asnje model
gjuhesor. Puna e tij eshte e vetme dhe e mbyllur: nga nje fjali si

    "shto si te paguar internetin"
    "shto rrogen te Ndricim Plaku 95000 lek"
    "shpenzova 1200 leke per karburant dje"
    "rezervo 50 mije per taksat"

nxjerr nje PROPOZIM te strukturuar: cfare veprimi, sa, ne cilen monedhe, nga
cili burim, ne cilen llogari, per cilin person, me cilen date dhe ore.

Pse deterministik dhe jo model gjuhesor:
  • Nje urdher qe leviz para duhet te jete i shpjegueshem. Kur asistenti
    gabon, duhet te dukret PSE gabon — nje rregull i lexueshem, jo nje peshe.
  • Pa internet, pa cmim, pa vonese. Nje shpenzim shenohet ne dy sekonda.
  • Te dhenat financiare nuk dalin nga serveri per te kuptuar nje fjali.

Propozimi NUK ekzekutohet ketu. Kthehet me nje shkalle sigurie dhe me listen
e asaj qe mungon; kush e therret vendos nese e kryen, e pyet, ose e refuzon.
============================================================================
"""

from datetime import date, datetime, time, timedelta
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
import re
import unicodedata

# ==========================================================================
# NORMALIZIMI
# ==========================================================================
# Shqipja shkruhet edhe me ë/ç edhe pa ato — dhe ne telefon me shpesh pa.
# Krahasimi behet mbi nje forme te vetme, qe "Ndricim" dhe "Ndriçim" te jene
# i njejti emer.
ZEVENDESIMET = {"ë": "e", "ç": "c", "Ë": "e", "Ç": "c"}


def normalizo(teksti: Any) -> str:
    t = str(teksti or "")
    for a, b in ZEVENDESIMET.items():
        t = t.replace(a, b)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.lower()
    t = re.sub(r"[^\w\s:/.,-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def fjalet(teksti: str) -> List[str]:
    return [f for f in re.split(r"[\s,;]+", normalizo(teksti)) if f]


# ==========================================================================
# NUMRAT
# ==========================================================================
SHUMEZUESIT = {
    "mije": 1_000, "mij": 1_000, "mijra": 1_000, "mijë": 1_000,
    "milion": 1_000_000, "milione": 1_000_000, "mln": 1_000_000,
    "k": 1_000,
}
NUMRAT_ME_FJALE = {
    "nje": 1, "dy": 2, "tre": 3, "tri": 3, "kater": 4, "pese": 5, "gjashte": 6,
    "shtate": 7, "tete": 8, "nente": 9, "dhjete": 10, "njezet": 20,
    "tridhjete": 30, "dyzet": 40, "pesedhjete": 50, "gjashtedhjete": 60,
    "shtatedhjete": 70, "tetedhjete": 80, "nentedhjete": 90, "qind": 100,
}


def _sa_numer(copa: str) -> Optional[float]:
    """'95.000' dhe '95,000' jane nientefta e njejta shume; '2.5' eshte 2.5.

    Rregulli: nje ndares me tre shifra pas tij eshte ndares mijesh, jo presje
    dhjetore. Pa kete, "95.000 leke" behet 95 leke — nje gabim i heshtur qe
    do te prishte cdo total.
    """
    c = copa.strip()
    if not c:
        return None
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", c):
        return float(re.sub(r"[.,]", "", c))
    c = c.replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", c):
        return None
    return float(c)


def lexo_shumen(teksti: str) -> Optional[float]:
    """Shuma e pare e gjetur ne fjali, me shumezuesit shqip."""
    t = normalizo(teksti)
    # Hiq datat dhe oret, qe '18/09' ose '14:30' te mos lexohen si shuma.
    t = re.sub(r"\b\d{1,2}[:.]\d{2}\b(?!\d)", " ", t)
    t = re.sub(r"\b\d{1,4}[/-]\d{1,2}([/-]\d{1,4})?\b", " ", t)

    # "95 mije", "95mije", "2.5 milion", "50k"
    m = re.search(r"(\d[\d.,]*)\s*(mije|mij|mijra|milion|milione|mln|k)\b", t)
    if m:
        baza = _sa_numer(m.group(1))
        if baza is not None:
            return baza * SHUMEZUESIT[m.group(2)]

    # "nje mije", "dy mije"
    m = re.search(r"\b(" + "|".join(NUMRAT_ME_FJALE) + r")\s+(mije|mij|milion)\b", t)
    if m:
        return NUMRAT_ME_FJALE[m.group(1)] * SHUMEZUESIT[m.group(2)]

    for copa in re.findall(r"\d[\d.,]*", t):
        v = _sa_numer(copa)
        if v is not None and v > 0:
            return v
    return None


# ==========================================================================
# MONEDHA
# ==========================================================================
EMRAT_E_MONEDHAVE = [
    (r"\b(lek[eëa]?|lek[eë]sh|l)\b", "LEK"),
    (r"\b(euro|eur|eurosh)\b", "EUR"),
    (r"\b(dollar[eë]?|usd)\b", "USD"),
    (r"\b(fr[eë]ng[aë]|chf)\b", "CHF"),
    (r"\b(paund|gbp|sterlin[eë])\b", "GBP"),
]


def lexo_monedhen(teksti: str) -> Optional[str]:
    t = normalizo(teksti)
    for shprehja, kodi in EMRAT_E_MONEDHAVE:
        if re.search(shprehja, t):
            return kodi
    return None


# ==========================================================================
# DATA DHE ORA
# ==========================================================================
MUAJT = {
    "janar": 1, "shkurt": 2, "mars": 3, "prill": 4, "maj": 5, "qershor": 6,
    "korrik": 7, "gusht": 8, "shtator": 9, "tetor": 10, "nentor": 11,
    "dhjetor": 12,
}
DITET_RELATIVE = {"sot": 0, "sonte": 0, "dje": -1, "mbreme": -1, "pardje": -2,
                  "neser": 1, "pasneser": 2}


def lexo_daten(teksti: str, sot: date) -> Optional[date]:
    t = normalizo(teksti)
    for fjala, zhvendosja in DITET_RELATIVE.items():
        if re.search(rf"\b{fjala}\b", t):
            return sot + timedelta(days=zhvendosja)

    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    m = re.search(r"\b(\d{1,2})\s*(?:[/.-])\s*(\d{1,2})(?:\s*[/.-]\s*(\d{2,4}))?\b", t)
    if m:
        dita, muaji = int(m.group(1)), int(m.group(2))
        viti = int(m.group(3)) if m.group(3) else sot.year
        if viti < 100:
            viti += 2000
        try:
            return date(viti, muaji, dita)
        except ValueError:
            return None

    # "me 18 shtator", "18 shtator"
    m = re.search(r"\b(\d{1,2})\s+(" + "|".join(MUAJT) + r")\b", t)
    if m:
        try:
            return date(sot.year, MUAJT[m.group(2)], int(m.group(1)))
        except ValueError:
            return None

    # "me 18" — dita e ketij muaji, ose e muajit te kaluar nese s'ka ardhur.
    m = re.search(r"\bme\s+(\d{1,2})\b", t)
    if m:
        dita = int(m.group(1))
        if 1 <= dita <= 31:
            try:
                kandidat = date(sot.year, sot.month, dita)
            except ValueError:
                return None
            return kandidat
    return None


def lexo_oren(teksti: str) -> Optional[time]:
    t = normalizo(teksti)
    m = re.search(r"\b(?:ne\s+)?or[eë]n?\s+(\d{1,2})(?:[:.](\d{2}))?\b", t)
    if not m:
        m = re.search(r"\b(\d{1,2}):(\d{2})\b", t)
    if not m:
        return None
    ora = int(m.group(1))
    minuta = int(m.group(2) or 0)
    if 0 <= ora <= 23 and 0 <= minuta <= 59:
        return time(ora, minuta)
    return None


# ==========================================================================
# GJETJA E ENTITETIT
# ==========================================================================
# Fjale qe s'ndihmojne ne krahasim: nese mbeten, "paguaj internetin" do te
# ngjante po aq me "paguaj driten".
FJALE_BOSHE = {
    "shto", "shtoje", "shenoj", "shenoje", "shenova", "si", "te", "e", "i",
    "paguar", "paguajta", "pagova", "paguaj", "paguhet", "u", "me", "ne",
    "nga", "per", "dhe", "nje", "lek", "leke", "lekë", "euro", "eur", "sot",
    "dje", "pardje", "mije", "mij", "ora", "oren", "llogarine", "llogaria",
    "kete", "kaq", "eshte", "ka", "kam", "mora", "erdhi", "hyri", "shpenzova",
    "bleva", "dhashe", "harxhova", "rezervo", "ruaj", "menjane", "muaj",
    "muajin", "fatura", "faturen", "e", "te", "ia", "kalo", "transfero",
}


def _celesat(teksti: str) -> List[str]:
    return [f for f in fjalet(teksti) if f not in FJALE_BOSHE and not f.isdigit()
            and len(f) > 2]


def gjej_entitetin(teksti: str, kandidatet: List[dict],
                   fusha: str = "emri") -> Tuple[Optional[dict], float]:
    """Kandidati me i perafert, dhe sa i sigurt eshte perafrimi (0-1).

    Rendi i provave shkon nga me e forta te me e dobeta: emri i plote brenda
    fjalise, pastaj mbivendosja e fjaleve, pastaj ngjashmeria shkronje per
    shkronje. Nje emer i shkruar gjysme ("internet" per "Interneti i shtepise")
    duhet te gjendet; dy emra qe ndajne vetem nje fjale te zakonshme jo.
    """
    t = normalizo(teksti)
    celesat_e_urdhrit = set(_celesat(teksti))
    me_i_miri, pikja_me_e_mire = None, 0.0

    for k in kandidatet or []:
        emri = normalizo(k.get(fusha) or "")
        if not emri:
            continue
        copat = {c for c in emri.split() if len(c) > 2}
        pikja = 0.0

        if emri and emri in t:
            pikja = 1.0
        elif copat:
            # Rrenja e fjales: "internet" ndaj "interneti", "rrog" ndaj "rrogen".
            perputhje = 0
            for c in copat:
                rrenja = c[:max(4, len(c) - 2)]
                if any(f.startswith(rrenja) or c.startswith(f[:max(4, len(f) - 2)])
                       for f in celesat_e_urdhrit):
                    perputhje += 1
            if perputhje:
                pikja = 0.55 + 0.35 * (perputhje / len(copat))

        if pikja < 0.5 and celesat_e_urdhrit:
            ngjashmeria = max(
                (SequenceMatcher(None, emri, f).ratio() for f in celesat_e_urdhrit),
                default=0.0)
            if ngjashmeria >= 0.82:
                pikja = max(pikja, ngjashmeria * 0.8)

        if pikja > pikja_me_e_mire:
            me_i_miri, pikja_me_e_mire = k, pikja

    return (me_i_miri, round(pikja_me_e_mire, 3)) if pikja_me_e_mire >= 0.5 else (None, 0.0)


# ==========================================================================
# KATEGORITE E SHPENZIMEVE
# ==========================================================================
KATEGORITE = {
    "ushqime": ["ushqim", "ushqime", "supermarket", "market", "buke", "shpenzime ushqimore"],
    "karburant": ["karburant", "benzine", "nafte", "gazoil", "pike karburanti"],
    "kafe": ["kafe", "dreke", "darke", "restorant", "lokal", "byrek"],
    "veshje": ["veshje", "rroba", "kepuce", "xhaketa"],
    "farmaci": ["farmaci", "ilac", "ilace", "mjek", "doktor", "spital", "analiza"],
    "transport": ["transport", "taksi", "autobus", "bilete", "furgon"],
    "argetim": ["argetim", "kinema", "dalje", "festë", "feste", "abonim"],
    "higjiene": ["higjiene", "detergjent", "pastrim", "shtepiake"],
    "shtepia": ["shtepia", "mobilje", "riparim", "hidraulik", "elektricist"],
    "dhurata": ["dhurate", "dhurata", "dasme", "dasem"],
    "femijet": ["femije", "femijet", "shkolle", "libra", "cerdhe"],
    "cigare": ["duhan", "cigare", "pije", "birre", "raki"],
}


def lexo_kategorine(teksti: str) -> Optional[str]:
    t = normalizo(teksti)
    for kategoria, fjalet_e_saj in KATEGORITE.items():
        for f in fjalet_e_saj:
            if re.search(rf"\b{re.escape(normalizo(f))}", t):
                return kategoria
    return None


# ==========================================================================
# QELLIMET
# ==========================================================================
# Rendi ka rendesi: kontrollohet nga me specifikja te me e gjeraja, sepse
# "paguaj borxhin e bankes" permban edhe fjalen "paguaj".
SHENJAT = [
    ("pyetje_detyrime", r"\b(cfare|cka|sa)\b.*\b(kam|me)\b.*\b(paguar|paguaj|pret|presin)\b"
                        r"|\bcfare me pret\b|\bdetyrimet\b|\bcfare kam per te paguar\b"),
    ("pyetje_shpenzime", r"\bsa\s+(kam\s+)?shpenz|\bshpenzimet e (ketij )?muajit\b"),
    ("pyetje_gjendje", r"\bsa kam\b|\bsa me ka mbetur\b|\bgjendja\b|\bsa jam\b"
                       r"|\bsa para kam\b|\bsa kam te lire\b|\bbilanci\b"),
    ("rezervim", r"\brezervo|\bmenjane\b|\bvendos menjane\b|\bzer\b|\bmbaj per\b"),
    ("transfer", r"\b(kalo|transfero|zhvendos)\b.*\bnga\b.*\b(te|ne)\b"),
    ("buxhet", r"\b(buxhet|kufi|limit)\b"),
    ("borxh", r"\bborxh|\bkredi(ne|a)?\b|\bkestin?\b|\bshlyej|\bi ktheva\b"),
    ("hyrje", r"\b(rrog[ae]n?|pag[ae]n?|te ardhur|honorar|bonus)\b"
              r"|\b(mora|erdhi|hyri|arketova|me erdhi|fitova)\b"),
    ("pagese_plani", r"\b(paguajta|pagova|paguar|paguaj|shenoje|shto si)\b"),
    ("shpenzim", r"\b(shpenzova|bleva|dhashe|harxhova|shkoi|iken)\b"),
]


def qellimi(teksti: str) -> Optional[str]:
    t = normalizo(teksti)
    for emri, shprehja in SHENJAT:
        if re.search(shprehja, t):
            return emri
    # Nje fjali si "1200 leke ushqime" s'ka folje, por ka shume dhe kategori.
    if lexo_shumen(t) and lexo_kategorine(t):
        return "shpenzim"
    return None


# ==========================================================================
# NDERTIMI I PROPOZIMIT
# ==========================================================================
def _num(x: Any, parazgjedhur: float = 0.0) -> float:
    try:
        return parazgjedhur if x is None else float(x)
    except (TypeError, ValueError):
        return parazgjedhur


def _gjej_llogarine(teksti: str, g: dict) -> Tuple[Optional[dict], float]:
    llogarite = g.get("llogarite") or []
    t = normalizo(teksti)
    # "ne dore", "kesh", "cash" tregojne llogarine e parave ne dore edhe kur
    # ajo quhet ndryshe.
    if re.search(r"\b(kesh|cash|ne dore|dore)\b", t):
        per_dore = [l for l in llogarite if (l.get("lloji") or "") == "cash"]
        if per_dore:
            return per_dore[0], 0.9
    return gjej_entitetin(teksti, llogarite, "emri")


def _pjesa_pas(teksti: str, fjala: str) -> Optional[str]:
    """Teksti pas nje parafjale — 'rezervo 50 mije per taksat' → 'taksat'."""
    m = re.search(rf"\b{fjala}\s+(.+)$", normalizo(teksti))
    return m.group(1).strip() if m else None


def _boshllek(p: dict, emri: str, pyetja: str) -> None:
    p["mungon"].append(emri)
    if not p.get("pyetja"):
        p["pyetja"] = pyetja


def kupto(teksti: str, g: dict, c: dict, sot: Optional[date] = None,
          njoftimet: Optional[List[dict]] = None) -> dict:
    """Nga fjalia te propozimi. Nuk shkruan asgje — vetem kupton.

    Kthen gjithmone nje propozim: edhe kur s'kupton, me veprimin 'pa_kuptuar'
    dhe me nje pyetje konkrete. Heshtja do te ishte pergjigjja me e keqe.
    """
    sot = sot or date.today()
    monedha_baze = str(c.get("monedha_baze") or "EUR").upper()
    q = qellimi(teksti)

    p: dict = {
        "teksti": str(teksti or "").strip(),
        "veprimi": q or "pa_kuptuar",
        "siguria": 0.0,
        "shuma": lexo_shumen(teksti),
        "monedha": lexo_monedhen(teksti) or monedha_baze,
        "data": (lexo_daten(teksti, sot) or sot).isoformat(),
        "ora": (lexo_oren(teksti).strftime("%H:%M")
                if lexo_oren(teksti) else None),
        "burimi": None, "llogaria": None, "personi": None, "kategoria": None,
        "mungon": [], "pyetja": None, "rruga": None, "trupi": {},
    }

    llogaria, pikja_llog = _gjej_llogarine(teksti, g)
    personi, _ = gjej_entitetin(teksti, g.get("personat") or [], "emri")
    if llogaria:
        p["llogaria"] = {"id": llogaria.get("id"), "emri": llogaria.get("emri"),
                         "siguria": pikja_llog}
    if personi:
        p["personi"] = {"id": personi.get("id"), "emri": personi.get("emri")}

    if q in (None, "pa_kuptuar"):
        p["pyetja"] = ("Nuk e kuptova. Provo p.sh.: \"shto si te paguar "
                       "internetin\", \"shto rrogen 95000 lek te Kesh\", "
                       "\"shpenzova 1200 leke per ushqime\", ose \"sa kam?\"")
        return p

    if q.startswith("pyetje"):
        p["siguria"] = 0.95
        return p

    ndertuesit = {
        "pagese_plani": _urdher_plan, "hyrje": _urdher_hyrje,
        "shpenzim": _urdher_shpenzim, "borxh": _urdher_borxh,
        "rezervim": _urdher_rezervim, "transfer": _urdher_transfer,
        "buxhet": _urdher_buxhet,
    }
    ndertuesit[q](p, teksti, g, c)
    if p["mungon"]:
        p["siguria"] = min(p["siguria"], 0.45)
    return p


# ── Pagesa e nje plani (fature, qira, kest i shenuar si plan) ─────────────
def _urdher_plan(p: dict, teksti: str, g: dict, c: dict) -> None:
    planet = [x for x in (g.get("planet") or []) if x.get("aktiv", True)]
    burimi, pikja = gjej_entitetin(teksti, planet, "emri")

    # "shto si te paguar rrogen" eshte hyrje, jo dalje — kush e shkruan e ka
    # fjalen per burimin, jo per drejtimin. Prandaj kontrollohen te dyja.
    burimi_ardhur, pikja_a = gjej_entitetin(teksti, g.get("te_ardhurat") or [], "emri")
    if burimi_ardhur and pikja_a > pikja:
        p["veprimi"] = "hyrje"
        return _urdher_hyrje(p, teksti, g, c)

    if not burimi:
        _boshllek(p, "burimi",
                  "Cilen pagese? Shkruaj emrin ashtu si e ke ne regjistri "
                  "(p.sh. \"Interneti\", \"Qiraja\").")
        return

    p["burimi"] = {"tabela": "planet", "id": burimi.get("id"),
                   "emri": burimi.get("emri"), "siguria": pikja}
    shuma = p["shuma"] if p["shuma"] else _num(burimi.get("shuma"))
    if shuma <= 0:
        _boshllek(p, "shuma", f"Sa pagove per {burimi.get('emri')}?")
        return

    p["shuma"] = shuma
    if not lexo_monedhen(teksti):
        p["monedha"] = (burimi.get("monedha") or p["monedha"]).upper()
    p["kategoria"] = burimi.get("kategoria") or "tjeter"
    p["siguria"] = round(min(0.97, 0.6 + 0.37 * pikja), 3)
    p["rruga"] = "/regjistro-pagese"
    p["trupi"] = {
        "lloji": "plan", "burimi_id": burimi.get("id"),
        "shuma": shuma, "monedha": p["monedha"],
        "data": p["data"], "ora": p["ora"],
        "kategoria": p["kategoria"], "pershkrimi": burimi.get("emri"),
        "llogaria_id": (p["llogaria"] or {}).get("id") or burimi.get("llogaria_id"),
        "personi_id": (p["personi"] or {}).get("id"),
    }


# ── Nje hyrje: rroga, honorar, arketim i planifikuar ──────────────────────
def _urdher_hyrje(p: dict, teksti: str, g: dict, c: dict) -> None:
    burimet = [x for x in (g.get("te_ardhurat") or []) if x.get("aktiv", True)]
    burimi, pikja = gjej_entitetin(teksti, burimet, "emri")

    # "mora rrogen" pa emer te sakte: nese ka vetem nje page, ajo eshte.
    if not burimi and re.search(r"\brrog|\bpag[ae]n?\b", normalizo(teksti)):
        pagat = [x for x in burimet if (x.get("lloji") or "") == "page"]
        if len(pagat) == 1:
            burimi, pikja = pagat[0], 0.8
    if not burimi and len(burimet) == 1:
        burimi, pikja = burimet[0], 0.7

    if not burimi:
        _boshllek(p, "burimi",
                  "Cila te ardhur? Shkruaj emrin si e ke te regjistri "
                  "(p.sh. \"Rroga\").")
        return

    p["burimi"] = {"tabela": "te-ardhurat", "id": burimi.get("id"),
                   "emri": burimi.get("emri"), "siguria": pikja}
    shuma = p["shuma"] if p["shuma"] else _num(burimi.get("shuma_mujore"))
    if shuma <= 0:
        _boshllek(p, "shuma", f"Sa more nga {burimi.get('emri')}?")
        return

    p["shuma"] = shuma
    if not lexo_monedhen(teksti):
        p["monedha"] = (burimi.get("monedha") or p["monedha"]).upper()
    p["kategoria"] = burimi.get("lloji") or "page"
    p["siguria"] = round(min(0.97, 0.6 + 0.37 * pikja), 3)
    p["rruga"] = "/regjistro-pagese"
    p["trupi"] = {
        "lloji": "te_ardhura", "burimi_id": burimi.get("id"),
        "shuma": shuma, "monedha": p["monedha"],
        "data": p["data"], "ora": p["ora"],
        "kategoria": p["kategoria"], "pershkrimi": burimi.get("emri"),
        "llogaria_id": (p["llogaria"] or {}).get("id") or burimi.get("llogaria_id"),
        "personi_id": (p["personi"] or {}).get("id") or burimi.get("personi_id"),
    }


# ── Nje shpenzim i lire, pa burim te regjistruar ──────────────────────────
def _urdher_shpenzim(p: dict, teksti: str, g: dict, c: dict) -> None:
    if not p["shuma"]:
        _boshllek(p, "shuma", "Sa ishte shuma?")
        return
    kategoria = lexo_kategorine(teksti) or "tjeter"
    p["kategoria"] = kategoria
    # Pa llogari te permendur, paraja e dores eshte hamendesimi me i vertete
    # per nje shpenzim te perditshem — por thuhet qarte ne permbledhje.
    llogaria = p["llogaria"]
    if not llogaria:
        per_dore = [l for l in (g.get("llogarite") or [])
                    if (l.get("lloji") or "") == "cash"]
        if per_dore:
            llogaria = {"id": per_dore[0].get("id"),
                        "emri": per_dore[0].get("emri"), "siguria": 0.5}
            p["llogaria"] = llogaria
    p["siguria"] = 0.85 if kategoria != "tjeter" else 0.7
    p["rruga"] = "/te-dhena/transaksionet"
    p["trupi"] = {
        "lloji": "dalje", "shuma": p["shuma"], "monedha": p["monedha"],
        "kategoria": kategoria, "data": p["data"], "ora": p["ora"],
        "pershkrimi": p["teksti"][:120],
        "llogaria_id": (llogaria or {}).get("id"),
        "personi_id": (p["personi"] or {}).get("id"),
    }


# ── Pagesa e nje borxhi ose arketimi ──────────────────────────────────────
def _urdher_borxh(p: dict, teksti: str, g: dict, c: dict) -> None:
    te_hapura = [d for d in (g.get("detyrimet") or [])
                 if (d.get("statusi") or "aktiv") != "shlyer"]
    burimi, pikja = gjej_entitetin(teksti, te_hapura, "pala")
    if not burimi and len(te_hapura) == 1:
        burimi, pikja = te_hapura[0], 0.7
    if not burimi:
        _boshllek(p, "burimi", "Cili borxh? Shkruaj palen (p.sh. \"Banka\").")
        return

    mbetur = _num(burimi.get("shuma_totale")) - _num(burimi.get("shuma_paguar"))
    shuma = p["shuma"] or _num(burimi.get("kesti_mujor")) or mbetur
    if shuma <= 0:
        _boshllek(p, "shuma", f"Sa i pagove {burimi.get('pala')}?")
        return
    shuma = min(shuma, mbetur)

    p["burimi"] = {"tabela": "detyrimet", "id": burimi.get("id"),
                   "emri": burimi.get("pala"), "siguria": pikja,
                   "mbetur": round(mbetur, 2)}
    p["shuma"] = shuma
    if not lexo_monedhen(teksti):
        p["monedha"] = (burimi.get("monedha") or p["monedha"]).upper()
    p["siguria"] = round(min(0.95, 0.55 + 0.4 * pikja), 3)
    p["rruga"] = "/paguaj-borxh"
    p["trupi"] = {
        "detyrimi_id": burimi.get("id"), "shuma": shuma,
        "monedha": p["monedha"], "data": p["data"], "ora": p["ora"],
        "llogaria_id": (p["llogaria"] or {}).get("id"),
        "personi_id": (p["personi"] or {}).get("id"),
    }


# ── Rezervimi i nje fondi ─────────────────────────────────────────────────
def _urdher_rezervim(p: dict, teksti: str, g: dict, c: dict) -> None:
    if not p["shuma"]:
        _boshllek(p, "shuma", "Sa te rezervoj?")
        return
    arsyeja = _pjesa_pas(teksti, "per") or _pjesa_pas(teksti, "si")
    emri = (arsyeja or "Rezerve").strip().capitalize()[:60]
    lloji = ("taksa" if re.search(r"taks|tatim", normalizo(teksti))
             else "emergjence" if re.search(r"emergjenc|rezerv[ea] emergjence",
                                            normalizo(teksti))
             else "tjeter")
    p["kategoria"] = lloji
    p["siguria"] = 0.9 if arsyeja else 0.75
    p["rruga"] = "/te-dhena/rezervat"
    p["trupi"] = {
        "emri": emri, "shuma": p["shuma"], "monedha": p["monedha"],
        "lloji": lloji, "arsyeja": p["teksti"][:200],
        "llogaria_id": (p["llogaria"] or {}).get("id"), "aktiv": True,
    }


# ── Transferim mes dy llogarive ───────────────────────────────────────────
def _urdher_transfer(p: dict, teksti: str, g: dict, c: dict) -> None:
    t = normalizo(teksti)
    m = re.search(r"\bnga\s+(.+?)\s+\b(?:te|ne)\s+(.+)$", t)
    if not m:
        _boshllek(p, "llogarite", "Nga cila llogari, ne cilen? "
                                  "P.sh. \"kalo 10000 nga Kesh te Banka\".")
        return
    nga, _ = _gjej_llogarine(m.group(1), g)
    tek, _ = _gjej_llogarine(m.group(2), g)
    if not nga or not tek or nga.get("id") == tek.get("id"):
        _boshllek(p, "llogarite", "Nuk i gjeta te dyja llogarite. "
                                  "Shkruaji ashtu si i ke ne regjistri.")
        return
    if not p["shuma"]:
        _boshllek(p, "shuma", "Sa te kaloj?")
        return
    p["llogaria"] = {"id": nga.get("id"), "emri": nga.get("emri"), "siguria": 0.9}
    p["destinacioni"] = {"id": tek.get("id"), "emri": tek.get("emri")}
    p["siguria"] = 0.9
    p["rruga"] = "/te-dhena/transaksionet"
    p["trupi"] = {
        "lloji": "transfer", "shuma": p["shuma"], "monedha": p["monedha"],
        "kategoria": "transfer", "data": p["data"], "ora": p["ora"],
        "pershkrimi": f"{nga.get('emri')} → {tek.get('emri')}",
        "llogaria_id": nga.get("id"), "llogaria_dest_id": tek.get("id"),
    }


# ── Vendosja e nje buxheti ────────────────────────────────────────────────
def _urdher_buxhet(p: dict, teksti: str, g: dict, c: dict) -> None:
    if not p["shuma"]:
        _boshllek(p, "shuma", "Sa kufi mujor te vendos?")
        return
    kategoria = lexo_kategorine(teksti) or _pjesa_pas(teksti, "per")
    if not kategoria:
        _boshllek(p, "kategoria", "Per cilen kategori? (ushqime, karburant…)")
        return
    p["kategoria"] = str(kategoria).strip().lower()[:40]
    p["siguria"] = 0.9
    p["rruga"] = "/te-dhena/buxhetet"
    p["trupi"] = {"kategoria": p["kategoria"], "shuma_mujore": p["shuma"],
                  "monedha": p["monedha"], "aktiv": True}


# ==========================================================================
# PERMBLEDHJA — cfare do te beje, me fjale
# ==========================================================================
# Perdoruesi konfirmon nje fjali, jo nje JSON. Nese fjalia s'e thote sakte
# cfare do te ndodhe, konfirmimi nuk vlen asgje.
def _para(x: Any, monedha: str) -> str:
    return f"{_num(x):,.0f}".replace(",", ".") + f" {monedha}"


def permbledh(p: dict, c: dict) -> str:
    # Nje propozim i paplote nuk permblidhet, pyetet. Pa kete, asistenti do
    # te "konfirmonte" nje shpenzim prej 0 me kategori te panjohur.
    if p.get("mungon"):
        return p.get("pyetja") or "Me mungon dicka per ta kryer kete."
    v = p.get("veprimi")
    mon = p.get("monedha") or str(c.get("monedha_baze") or "EUR")
    kur = p.get("data") or ""
    if p.get("ora"):
        kur += f" ne {p['ora']}"
    llog = (p.get("llogaria") or {}).get("emri")
    pers = (p.get("personi") or {}).get("emri")
    fund = ""
    if llog:
        fund += f" nga llogaria {llog}" if v != "hyrje" else f" ne llogarine {llog}"
    if pers:
        fund += f", per {pers}"

    if v == "pagese_plani":
        return (f"Do te shenoj si te paguar \"{p['burimi']['emri']}\": "
                f"{_para(p['shuma'], mon)}, me {kur}{fund}.")
    if v == "hyrje":
        return (f"Do te shenoj hyrjen \"{p['burimi']['emri']}\": "
                f"{_para(p['shuma'], mon)}, me {kur}{fund}.")
    if v == "shpenzim":
        return (f"Do te shenoj nje shpenzim {p.get('kategoria')}: "
                f"{_para(p['shuma'], mon)}, me {kur}{fund}.")
    if v == "borxh":
        mbetur = (p.get("burimi") or {}).get("mbetur")
        shtese = (f" Pas kesaj mbeten {_para(_num(mbetur) - _num(p['shuma']), mon)}."
                  if mbetur is not None else "")
        return (f"Do te paguaj {_para(p['shuma'], mon)} te "
                f"\"{p['burimi']['emri']}\", me {kur}{fund}.{shtese}")
    if v == "rezervim":
        return (f"Do te rezervoj {_para(p['shuma'], mon)} si "
                f"\"{p['trupi'].get('emri')}\". Kjo shume del nga "
                f"\"e lira per te shpenzuar\", por mbetet ne llogari.")
    if v == "transfer":
        return (f"Do te kaloj {_para(p['shuma'], mon)} nga "
                f"{p['llogaria']['emri']} te {p['destinacioni']['emri']}, me {kur}.")
    if v == "buxhet":
        return (f"Do te vendos nje kufi mujor prej {_para(p['shuma'], mon)} "
                f"per \"{p.get('kategoria')}\".")
    if v and v.startswith("pyetje"):
        return "Po e shikoj gjendjen…"
    return p.get("pyetja") or "Nuk e kuptova."


# Nje veprim i kryer duhet te lexohet si i kryer. "U krye: Do te shenoj…"
# eshte gjysma e nje fjalie; keto pese zevendesime e bejne te plote.
E_KRYER = {
    "Do te shenoj si te paguar": "U shenua si e paguar",
    "Do te shenoj hyrjen": "U shenua hyrja",
    "Do te shenoj nje shpenzim": "U shenua nje shpenzim",
    "Do te paguaj": "U pagua",
    "Do te rezervoj": "U rezervua",
    "Do te kaloj": "U kaluan",
    "Do te vendos": "U vendos",
}


def si_e_kryer(permbledhje: str) -> str:
    teksti = str(permbledhje or "")
    for e_ardhme, e_shkuar in E_KRYER.items():
        if teksti.startswith(e_ardhme):
            return e_shkuar + teksti[len(e_ardhme):]
    return teksti
