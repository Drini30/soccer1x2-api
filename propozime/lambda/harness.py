#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HARNESS i pavarur i hallkave 9-12 te soccer_api.py (lexim vetem, asnje ndryshim ne repo).

  9  blendi i totalit te tregut (XG_NORM + MKT_TOTAL_W)        soccer_api.py:6610-6628
 10  Monte Carlo (normal-perturbim i lambda + Poisson)          soccer_api.py:6112-6131
 11  Dixon-Coles mbi matricen H                                 soccer_api.py:6133-6140
 12  top-5 + AFF -> moduli i fituesit -> draw->LEAN (-> CS_LEAN) soccer_api.py:6176-6227
 +   fallback "loje e hapur" (pas simulimit)                    soccer_api.py:6746-6772

Kopjet VERBATIM jane te shenuara "VERBATIM <rreshtat>". Versioni "trace" perserit
te njejtat rreshta duke regjistruar hapat e ndermjetem, dhe ne fund ASSERT-ohet qe
jep saktesisht te njejtin output si kopja verbatim, per cdo rast.

Ekzekutimi:
    ./venv/bin/python harness.py               # shembujt + rrjeta + forma e mbyllur
    ./venv/bin/python harness.py --kaos 1.05   # faktor kaosi tjeter (parazgjedhje 1.10)
    ./venv/bin/python harness.py --seed 7
"""
import os
import sys
import math
import json
import argparse
import numpy as np

# ══════════════════════════════════════════════════════════════════════════
# KONSTANTET (me rreshtin ku lexohen ne soccer_api.py)
# ══════════════════════════════════════════════════════════════════════════
RHO_DC = -0.12                 # :5570  (konstante moduli, JO _konf)
MC_ITERACIONE = 50_000         # :5573  (konstante moduli)
FALLBACK_HAPUR = 3.20          # :5577-5580 (lexohet me _konf te :6746)
XG_FLOOR = 0.10                # :5663-5667 (konstante moduli)
TOTAL_CALIB = 0.0              # :5739-5742 (konstante moduli; 0 -> dega e O/U e fikur)
AFF_FIKS = 0.15                # :5770-5773 (lexohet me _konf te :6630)
CS_LEAN_XG = 99.0              # :5801-5804 (konstante moduli; 99 -> rregulli i FIKUR)
PRAG_LEAN = 0.30               # :5805-5808 (konstante moduli, JO _konf)
XG_NORM_A_HOME = 0.08          # :5835-5838 (lexohet me _konf te :6610)
XG_NORM_B_HOME = 0.87          # :5839-5842
XG_NORM_A_AWAY = -0.02         # :5843-5846
XG_NORM_B_AWAY = 0.97          # :5847-5850
MKT_TOTAL_W = 0.50             # :5857-5860 (konstante moduli, JO _konf!)
WINNER_BURIMI_MC = 0           # :5938
WINNER_BURIMI_TREG = 1         # :5939
WINNER_BURIMI_KORR = 2         # :5940
WINNER_PRAG = 0.15             # :5942-5945 (vlen vetem kur s'ka treg 1X2)
WINNER_PRAG_TREG = 0.12        # :5949-5952
WINNER_FLB_75 = 0.060          # :5957
WINNER_FLB_65 = 0.036          # :5958
WINNER_FLB_40 = 0.035          # :5959
W_MKT_FINAL = 0.35             # :5615-5618 (lexohet me _konf te :6658)

# Vlerat LIVE te model_config (auto-kalibrim 19/09/2026) — perdoren VETEM kur
# kerkohet shprehimisht (demo e hallkes 9). _konf() parazgjedhje = default i kodit.
XG_NORM_LIVE = {"XG_NORM_A_HOME": -0.1438, "XG_NORM_B_HOME": 1.1505,
                "XG_NORM_A_AWAY": 0.2989, "XG_NORM_B_AWAY": 0.8666}

_KONF_OVERRIDE = {}            # bosh = kthe default-in e kodit (si Supabase i palidhur)


def _konf(emri: str, parazgjedhje: float) -> float:
    """STUB i soccer_api.py:552-566 — model_config -> (ketu: override lokal) -> default."""
    v = _KONF_OVERRIDE.get(emri)
    if v is not None:
        return float(v)
    return float(parazgjedhje)


# ══════════════════════════════════════════════════════════════════════════
# VERBATIM soccer_api.py:5962-5974
# ══════════════════════════════════════════════════════════════════════════
def _korrigjo_flb(p1: float, px: float, p2: float) -> tuple:
    """Korrigjimi favorit-autsajder mbi 1X2 te devigosur. Kthen trioshen e rinormalizuar."""
    _pmax = max(p1, p2)
    if   _pmax >= 0.75: _d = WINNER_FLB_75
    elif _pmax >= 0.65: _d = WINNER_FLB_65
    elif 0.35 <= _pmax <= 0.45: _d = WINNER_FLB_40
    else: return (p1, px, p2)
    if p1 >= p2:
        p1 += _d
    else:
        p2 += _d
    _s = p1 + px + p2
    return (p1 / _s, px / _s, p2 / _s) if _s > 0 else (p1, px, p2)


# ══════════════════════════════════════════════════════════════════════════
# VERBATIM soccer_api.py:5977-6008
# ══════════════════════════════════════════════════════════════════════════
def _moduli_i_fituesit(prob_mc: dict, mkt_1x2=None) -> tuple:
    """
    Vendos drejtimin qe duhet te respektoje skori i publikuar.
    Kthen (drejtimi, burimi_perdorur) ku drejtimi eshte "1", "2" ose None (e ngushte).
    """
    _burimi = int(_konf("WINNER_BURIMI", WINNER_BURIMI_TREG))
    _p1 = float(prob_mc.get("p1") or 0.0)
    _px = float(prob_mc.get("px") or 0.0)
    _p2 = float(prob_mc.get("p2") or 0.0)
    _prag = _konf("WINNER_PRAG", WINNER_PRAG)
    _emri = "mc"

    if _burimi in (WINNER_BURIMI_TREG, WINNER_BURIMI_KORR) and mkt_1x2:
        try:
            _m1, _mx, _m2 = (float(x) for x in mkt_1x2)
            _sm = _m1 + _mx + _m2
            if _sm > 0 and min(_m1, _mx, _m2) > 0:
                _m1, _mx, _m2 = _m1 / _sm, _mx / _sm, _m2 / _sm   # devigosje
                _emri = "treg"
                if _burimi == WINNER_BURIMI_KORR:
                    _m1, _mx, _m2 = _korrigjo_flb(_m1, _mx, _m2)
                    _emri = "treg_korr"
                _p1, _px, _p2 = _m1, _mx, _m2
                _prag = _konf("WINNER_PRAG_TREG", WINNER_PRAG_TREG)
        except Exception:
            pass   # kuota te prishura -> mbetemi te MC-ja

    if _p1 >= _p2 and (_p1 - _px) > _prag:
        return ("1", _emri)
    if _p2 > _p1 and (_p2 - _px) > _prag:
        return ("2", _emri)
    return (None, _emri)


# ══════════════════════════════════════════════════════════════════════════
# VERBATIM soccer_api.py:6421-6434
# ══════════════════════════════════════════════════════════════════════════
def _lambda_nga_p_over(p_over):
    """Gjej lambda (totali i pritur i golave) qe jep kete P(mbi 2.5) sipas Poisson. Bisection."""
    import math
    def _p_mbi(lam):
        return 1.0 - math.exp(-lam) * (1.0 + lam + lam * lam / 2.0)
    lo, hi = 0.4, 6.0
    p_over = min(0.98, max(0.02, float(p_over)))
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if _p_mbi(mid) < p_over:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2.0, 3)


# ══════════════════════════════════════════════════════════════════════════
# HALLKA 9 — VERBATIM soccer_api.py:6610-6628 (mbeshtjell ne funksion)
#   hyrja xg_1/xg_2 = ato qe ruhen te training_data.xg_1/xg_2 (:6973)
#   dalja _xg1_norm/_xg2_norm = lambda QE SIMULOHET (:6646-6647)
# (BOOST_MYSAFIR :6639-6645 eshte 0.0 -> s'ben asgje; nuk kopjohet.)
# ══════════════════════════════════════════════════════════════════════════
def hallka9_blendi_totalit(xg_1, xg_2, _ou_o=None, _ou_u=None, trace=None):
    _xg1_norm = float(np.clip(_konf("XG_NORM_A_HOME", XG_NORM_A_HOME)
                              + _konf("XG_NORM_B_HOME", XG_NORM_B_HOME) * xg_1, XG_FLOOR, 5.00))
    _xg2_norm = float(np.clip(_konf("XG_NORM_A_AWAY", XG_NORM_A_AWAY)
                              + _konf("XG_NORM_B_AWAY", XG_NORM_B_AWAY) * xg_2, XG_FLOOR, 5.00))
    if trace is not None:
        trace["pas_XG_NORM"] = (_xg1_norm, _xg2_norm)
    if MKT_TOTAL_W > 0.0 and _ou_o and _ou_u:
        try:
            _p_ov_sk = (1.0 / float(_ou_o)) / (1.0 / float(_ou_o) + 1.0 / float(_ou_u))
            _tot_mkt = _lambda_nga_p_over(_p_ov_sk)          # totali qe pret tregu
            _tot_mod = _xg1_norm + _xg2_norm                 # totali i modelit (i normalizuar)
            if _tot_mod > 0.10:
                _tot_tgt = (1.0 - MKT_TOTAL_W) * _tot_mod + MKT_TOTAL_W * _tot_mkt
                _shk_mkt = float(np.clip(_tot_tgt / _tot_mod, 0.50, 2.00))   # fre sigurie
                _xg1_norm = float(np.clip(_xg1_norm * _shk_mkt, XG_FLOOR, 5.00))
                _xg2_norm = float(np.clip(_xg2_norm * _shk_mkt, XG_FLOOR, 5.00))
                if trace is not None:
                    trace.update(p_over=_p_ov_sk, tot_mkt=_tot_mkt, tot_mod=_tot_mod,
                                 tot_tgt=_tot_tgt, shk_mkt=_shk_mkt)
        except Exception:
            pass
    return _xg1_norm, _xg2_norm


# ══════════════════════════════════════════════════════════════════════════
# HALLKAT 10-12 — VERBATIM soccer_api.py:6097-6257 (simulim_monte_carlo_v2)
# ══════════════════════════════════════════════════════════════════════════
def simulim_monte_carlo_v2(
    xg_1: float, xg_2: float,
    kaos_factor: float = 1.0,
    is_derbi: bool = False,
    iteracione: int = MC_ITERACIONE,
    rho: float = RHO_DC,
    seed: int = None,
    aff: float = 0.5,
    mkt_1x2=None
) -> tuple:
    """
    Monte Carlo vectorized me numpy — 50,000 simulime në ~60ms.
    Zëvendëson: loop Python me 10,000 iteracione (~800ms).
    Kthen: (rezultati_sakt, prob_max, rezultatet_freq, prob_1x2)
    """
    if is_derbi:
        kaos_factor *= 1.15

    sigma_1 = xg_1 * 0.18 * kaos_factor
    sigma_2 = xg_2 * 0.18 * kaos_factor

    rng = np.random.default_rng(seed)
    xg1_virtual = np.clip(rng.normal(xg_1, sigma_1, iteracione), 0.05, 6.0)
    xg2_virtual = np.clip(rng.normal(xg_2, sigma_2, iteracione), 0.05, 6.0)

    gola_1 = rng.poisson(xg1_virtual)
    gola_2 = rng.poisson(xg2_virtual)

    # ── Matrica e perbashket nga simulimet (per Dixon-Coles) ──
    GMAX = 10
    _g1 = np.clip(gola_1, 0, GMAX)
    _g2 = np.clip(gola_2, 0, GMAX)
    H = np.zeros((GMAX + 1, GMAX + 1), dtype=float)
    np.add.at(H, (_g1, _g2), 1.0)
    H = H / H.sum()

    # ── DIXON-COLES: korrigjim korrelacioni per skoret e uleta (0-0,0-1,1-0,1-1) ──
    _l = max(float(xg_1), 0.05)
    _m = max(float(xg_2), 0.05)
    H[0, 0] *= max(1.0 - _l * _m * rho, 1e-6)
    H[0, 1] *= max(1.0 + _l * rho, 1e-6)
    H[1, 0] *= max(1.0 + _m * rho, 1e-6)
    H[1, 1] *= max(1.0 - rho, 1e-6)
    H = H / H.sum()

    _ii, _jj = np.indices(H.shape)
    prob_1x2 = {
        "p1": round(float(H[_ii > _jj].sum()), 4),
        "px": round(float(H[_ii == _jj].sum()), 4),
        "p2": round(float(H[_ii < _jj].sum()), 4),
    }

    try:
        _n_ruaj = int(os.environ.get("DIST_TOP_N", "40").strip())
    except Exception:
        _n_ruaj = 40
    _n_ruaj = max(5, min(_n_ruaj, int(H.size)))

    _flat = H.flatten()
    _order = np.argsort(_flat)[::-1]
    rezultatet_freq = {}
    for _idx in _order[:_n_ruaj]:
        _i = int(_idx // H.shape[1]); _j = int(_idx % H.shape[1])
        _c = int(round(float(_flat[_idx]) * iteracione))
        if _c > 0:
            rezultatet_freq[f"{_i}-{_j}"] = _c

    # ── ZGJEDHJA E REZULTATIT: midis top-5, me afer totalit te pritur (metoda 27/06) ──
    total_pritur = xg_1 + xg_2
    kandidatet = []
    for _idx in _order[:5]:
        _i = int(_idx // H.shape[1]); _j = int(_idx % H.shape[1])
        _freq = float(_flat[_idx])
        _difft = abs((_i + _j) - total_pritur)
        _score = _freq * (1.0 / (1.0 + _difft * aff))
        kandidatet.append((_i, _j, _freq, _score))
    kandidatet.sort(key=lambda x: x[3], reverse=True)
    _drejtimi, _ = _moduli_i_fituesit(prob_1x2, mkt_1x2)
    if _drejtimi == "1":
        _fkand = [_k for _k in kandidatet if _k[0] > _k[1]]   # favorit vendas -> vetem fitore vendase
    elif _drejtimi == "2":
        _fkand = [_k for _k in kandidatet if _k[1] > _k[0]]   # favorit mysafir -> vetem fitore mysafiri
    else:
        _fkand = kandidatet                                    # ngushte -> lejo barazim
    if _fkand:
        kandidatet = _fkand                                    # mbrojtje: mos zbraz listen
    rez_g1, rez_g2, freq_zgjedhur, _ = kandidatet[0]
    if (rez_g1 == rez_g2 and abs(xg_1 - xg_2) >= PRAG_LEAN):
        _rhu = lambda _x: int(_x + 0.5)   # round half-up
        _a1 = _rhu(xg_1); _a2 = _rhu(xg_2)
        if _a1 == _a2:                     # rrumbullakosja prapë barazim -> favoritit +1
            if xg_1 >= xg_2:
                _a1 += 1
            else:
                _a2 += 1
        rez_g1, rez_g2 = min(_a1, 10), min(_a2, 10)
        freq_zgjedhur = float(H[rez_g1, rez_g2])
    if CS_LEAN_XG < 90.0:
        if rez_g2 == 0 and rez_g1 >= 2 and xg_2 >= CS_LEAN_XG:
            rez_g2 = 1                                   # X-0 → X-1 (mysafiri shënon)
            freq_zgjedhur = float(H[rez_g1, rez_g2])
        elif rez_g1 == 0 and rez_g2 >= 2 and xg_1 >= CS_LEAN_XG:
            rez_g1 = 1                                   # 0-X → 1-X (vendasi shënon)
            freq_zgjedhur = float(H[rez_g1, rez_g2])
    rez_str  = f"{rez_g1}-{rez_g2}"
    prob_max = float(freq_zgjedhur)

    # ── TREGJET nga matrica (Dixon-Coles e perfshire) ──
    _tot = _ii + _jj
    def _pf(mask):
        return round(float(H[mask].sum()), 4)
    tregjet = {
        "1": prob_1x2["p1"], "X": prob_1x2["px"], "2": prob_1x2["p2"],
        "1X": round(prob_1x2["p1"] + prob_1x2["px"], 4),
        "X2": round(prob_1x2["px"] + prob_1x2["p2"], 4),
        "12": round(prob_1x2["p1"] + prob_1x2["p2"], 4),
        "Over 1.5": _pf(_tot >= 2), "Under 1.5": _pf(_tot <= 1),
        "Over 2.5": _pf(_tot >= 3), "Under 2.5": _pf(_tot <= 2),
        "Over 3.5": _pf(_tot >= 4), "Under 3.5": _pf(_tot <= 3),
        "GG": _pf((_ii > 0) & (_jj > 0)),
        "NG": _pf((_ii == 0) | (_jj == 0)),
    }

    if TOTAL_CALIB != 0.0:
        import math as _m
        _lam_ou = max(0.30, (xg_1 + xg_2) - TOTAL_CALIB)
        def _pcdf(_k, _lam):
            return sum(_m.exp(-_lam) * _lam ** _i / _m.factorial(_i) for _i in range(_k + 1))
        for _kk, _lbl in [(1, "1.5"), (2, "2.5"), (3, "3.5")]:
            _u = round(_pcdf(_kk, _lam_ou), 4)
            tregjet["Under " + _lbl] = _u
            tregjet["Over " + _lbl] = round(1.0 - _u, 4)

    return rez_str, round(prob_max, 4), rezultatet_freq, prob_1x2, tregjet


# ══════════════════════════════════════════════════════════════════════════
# VERSIONI "TRACE": te njejtat rreshta 6112-6227, ndare ne (a) ndertimi i H dhe
# (b) zgjedhja nga H, qe te regjistrohen hapat. (b) pranon edhe H analitike.
# ══════════════════════════════════════════════════════════════════════════
def ndertimi_H_mc(xg_1, xg_2, kaos_factor=1.0, is_derbi=False, iteracione=MC_ITERACIONE,
                rho=RHO_DC, seed=None):
    """soccer_api.py:6112-6140 — identike me kopjen verbatim (i njejti rend thirrjesh RNG)."""
    if is_derbi:
        kaos_factor *= 1.15
    sigma_1 = xg_1 * 0.18 * kaos_factor
    sigma_2 = xg_2 * 0.18 * kaos_factor
    rng = np.random.default_rng(seed)
    xg1_virtual = np.clip(rng.normal(xg_1, sigma_1, iteracione), 0.05, 6.0)
    xg2_virtual = np.clip(rng.normal(xg_2, sigma_2, iteracione), 0.05, 6.0)
    gola_1 = rng.poisson(xg1_virtual)
    gola_2 = rng.poisson(xg2_virtual)
    GMAX = 10
    _g1 = np.clip(gola_1, 0, GMAX)
    _g2 = np.clip(gola_2, 0, GMAX)
    H = np.zeros((GMAX + 1, GMAX + 1), dtype=float)
    np.add.at(H, (_g1, _g2), 1.0)
    H = H / H.sum()
    H_para_dc = H.copy()
    _apliko_dc(H, xg_1, xg_2, rho)
    H = H / H.sum()
    return H, H_para_dc


def _apliko_dc(H, xg_1, xg_2, rho):
    """soccer_api.py:6134-6139 (ne vend)."""
    _l = max(float(xg_1), 0.05)
    _m = max(float(xg_2), 0.05)
    H[0, 0] *= max(1.0 - _l * _m * rho, 1e-6)
    H[0, 1] *= max(1.0 + _l * rho, 1e-6)
    H[1, 0] *= max(1.0 + _m * rho, 1e-6)
    H[1, 1] *= max(1.0 - rho, 1e-6)


def ndertimi_H_analitike(xg_1, xg_2, kaos_factor=1.0, is_derbi=False, rho=RHO_DC, nz=4001):
    """
    E njejta shperndarje qe MC-ja ve ne kampion, por me iteracione -> pafundesi:
    lambda ~ clip(N(xg, 0.18*kaos*xg), 0.05, 6.0), gola ~ Poisson(lambda), clip ne 10, pastaj DC.
    Integrim numerik mbi z ne [-8, 8]. Pa zhurme kampionimi — per te pare nese vendimi i
    MC-se eshte 'i qendrueshem' apo varet nga seed-i.
    """
    if is_derbi:
        kaos_factor *= 1.15
    z = np.linspace(-8.0, 8.0, nz)
    w = np.exp(-0.5 * z * z); w /= w.sum()
    GMAX = 10
    k = np.arange(GMAX + 1)

    def _marg(mu):
        lam = np.clip(mu + mu * 0.18 * kaos_factor * z, 0.05, 6.0)
        # pmf Poisson per k=0..9, dhe bishti >=10 i grumbulluar te 10 (si np.clip(.., 0, 10))
        logp = -lam[:, None] + k[None, :] * np.log(lam[:, None]) - np.array(
            [math.lgamma(x + 1) for x in k])[None, :]
        p = np.exp(logp)
        p[:, GMAX] = np.clip(1.0 - p[:, :GMAX].sum(axis=1), 0.0, 1.0)
        return (w[:, None] * p).sum(axis=0)

    H = np.outer(_marg(xg_1), _marg(xg_2))
    H = H / H.sum()
    _apliko_dc(H, xg_1, xg_2, rho)
    H = H / H.sum()
    return H


def zgjidh_nga_H(H, xg_1, xg_2, aff, mkt_1x2, iteracione=MC_ITERACIONE):
    """soccer_api.py:6142-6227 me regjistrim te cdo hapi. Kthen (dalja, trace)."""
    T = {}
    _ii, _jj = np.indices(H.shape)
    prob_1x2 = {
        "p1": round(float(H[_ii > _jj].sum()), 4),
        "px": round(float(H[_ii == _jj].sum()), 4),
        "p2": round(float(H[_ii < _jj].sum()), 4),
    }
    try:
        _n_ruaj = int(os.environ.get("DIST_TOP_N", "40").strip())
    except Exception:
        _n_ruaj = 40
    _n_ruaj = max(5, min(_n_ruaj, int(H.size)))
    _flat = H.flatten()
    _order = np.argsort(_flat)[::-1]
    rezultatet_freq = {}
    for _idx in _order[:_n_ruaj]:
        _i = int(_idx // H.shape[1]); _j = int(_idx % H.shape[1])
        _c = int(round(float(_flat[_idx]) * iteracione))
        if _c > 0:
            rezultatet_freq[f"{_i}-{_j}"] = _c

    total_pritur = xg_1 + xg_2
    kandidatet = []
    T["top5"] = []
    for _idx in _order[:5]:
        _i = int(_idx // H.shape[1]); _j = int(_idx % H.shape[1])
        _freq = float(_flat[_idx])
        _difft = abs((_i + _j) - total_pritur)
        _score = _freq * (1.0 / (1.0 + _difft * aff))
        kandidatet.append((_i, _j, _freq, _score))
        T["top5"].append({"skor": f"{_i}-{_j}", "freq": _freq, "difft": _difft,
                          "aff_faktor": 1.0 / (1.0 + _difft * aff), "aff_score": _score})
    T["moda"] = T["top5"][0]["skor"]
    kandidatet.sort(key=lambda x: x[3], reverse=True)
    T["renditja_aff"] = [f"{k[0]}-{k[1]}" for k in kandidatet]
    T["pas_aff"] = T["renditja_aff"][0]
    _drejtimi, _burimi = _moduli_i_fituesit(prob_1x2, mkt_1x2)
    T["drejtimi"] = _drejtimi
    T["burimi_drejtimit"] = _burimi
    if _drejtimi == "1":
        _fkand = [_k for _k in kandidatet if _k[0] > _k[1]]
    elif _drejtimi == "2":
        _fkand = [_k for _k in kandidatet if _k[1] > _k[0]]
    else:
        _fkand = kandidatet
    T["filtri_zbrazi"] = not bool(_fkand)
    if _fkand:
        kandidatet = _fkand
    T["kandidatet_pas_filtrit"] = [f"{k[0]}-{k[1]}" for k in kandidatet]
    rez_g1, rez_g2, freq_zgjedhur, _ = kandidatet[0]
    T["pas_fituesit"] = f"{rez_g1}-{rez_g2}"
    T["lean"] = False
    if (rez_g1 == rez_g2 and abs(xg_1 - xg_2) >= PRAG_LEAN):
        _rhu = lambda _x: int(_x + 0.5)
        _a1 = _rhu(xg_1); _a2 = _rhu(xg_2)
        if _a1 == _a2:
            if xg_1 >= xg_2:
                _a1 += 1
            else:
                _a2 += 1
        rez_g1, rez_g2 = min(_a1, 10), min(_a2, 10)
        freq_zgjedhur = float(H[rez_g1, rez_g2])
        T["lean"] = True
    T["pas_lean"] = f"{rez_g1}-{rez_g2}"
    T["cs_lean"] = False
    if CS_LEAN_XG < 90.0:
        if rez_g2 == 0 and rez_g1 >= 2 and xg_2 >= CS_LEAN_XG:
            rez_g2 = 1; freq_zgjedhur = float(H[rez_g1, rez_g2]); T["cs_lean"] = True
        elif rez_g1 == 0 and rez_g2 >= 2 and xg_1 >= CS_LEAN_XG:
            rez_g1 = 1; freq_zgjedhur = float(H[rez_g1, rez_g2]); T["cs_lean"] = True
    rez_str = f"{rez_g1}-{rez_g2}"
    prob_max = float(freq_zgjedhur)
    _tot = _ii + _jj

    def _pf(mask):
        return round(float(H[mask].sum()), 4)
    tregjet = {
        "1": prob_1x2["p1"], "X": prob_1x2["px"], "2": prob_1x2["p2"],
        "1X": round(prob_1x2["p1"] + prob_1x2["px"], 4),
        "X2": round(prob_1x2["px"] + prob_1x2["p2"], 4),
        "12": round(prob_1x2["p1"] + prob_1x2["p2"], 4),
        "Over 1.5": _pf(_tot >= 2), "Under 1.5": _pf(_tot <= 1),
        "Over 2.5": _pf(_tot >= 3), "Under 2.5": _pf(_tot <= 2),
        "Over 3.5": _pf(_tot >= 4), "Under 3.5": _pf(_tot <= 3),
        "GG": _pf((_ii > 0) & (_jj > 0)),
        "NG": _pf((_ii == 0) | (_jj == 0)),
    }
    T["p_tot_ge4_pa_rrumbullakim"] = float(H[_tot >= 4].sum())
    return (rez_str, round(prob_max, 4), rezultatet_freq, prob_1x2, tregjet), T


# ══════════════════════════════════════════════════════════════════════════
# PAS SIMULIMIT — VERBATIM soccer_api.py:6658-6677 (blendi final 1X2, i nevojshem
# sepse fallback-u i jep prob_1x2_mc TE BLENDUAR modulit) dhe :6730-6772 (fallback).
# ══════════════════════════════════════════════════════════════════════════
def pas_simulimit(rez_sakt, prob_rez_sakt, rezultatet_freq, prob_1x2_mc,
                  _xg1_norm, _xg2_norm, p1_real, px_real, p2_real):
    prob_1x2_mc = dict(prob_1x2_mc)
    _w_mkt_f = _konf("W_MKT_FINAL", W_MKT_FINAL)
    if _w_mkt_f > 0.0 and None not in (p1_real, px_real, p2_real):
        try:
            _sm = float(p1_real) + float(px_real) + float(p2_real)
            if _sm > 0:
                _b1 = (1.0 - _w_mkt_f) * prob_1x2_mc["p1"] + _w_mkt_f * (float(p1_real) / _sm)
                _bx = (1.0 - _w_mkt_f) * prob_1x2_mc["px"] + _w_mkt_f * (float(px_real) / _sm)
                _b2 = (1.0 - _w_mkt_f) * prob_1x2_mc["p2"] + _w_mkt_f * (float(p2_real) / _sm)
                _bs = _b1 + _bx + _b2
                if _bs > 0:
                    _b1, _bx, _b2 = _b1 / _bs, _bx / _bs, _b2 / _bs
                    prob_1x2_mc = {"p1": round(_b1, 4), "px": round(_bx, 4), "p2": round(_b2, 4)}
        except Exception:
            pass
    try:
        g1, g2 = map(int, rez_sakt.split("-"))
    except:
        g1, g2 = 1, 0
    fallback = False
    _prag_hapur = _konf("FALLBACK_HAPUR", FALLBACK_HAPUR)
    if (g1 + g2 <= 1) and (_xg1_norm + _xg2_norm > _prag_hapur):
        _drejtimi_fb, _ = _moduli_i_fituesit(
            prob_1x2_mc,
            ((p1_real, px_real, p2_real) if None not in (p1_real, px_real, p2_real) else None)
        )
        _forco_1 = (_drejtimi_fb == "1")
        _forco_2 = (_drejtimi_fb == "2")
        for r, freq in sorted(rezultatet_freq.items(), key=lambda x: x[1], reverse=True):
            try:
                rg1, rg2 = map(int, r.split("-"))
                if rg1 + rg2 <= 1:
                    continue
                if _forco_1 and rg1 <= rg2:
                    continue
                if _forco_2 and rg2 <= rg1:
                    continue
                rez_sakt       = r
                g1, g2         = rg1, rg2
                prob_rez_sakt  = freq / float(MC_ITERACIONE)
                fallback = True
                break
            except:
                continue
    return rez_sakt, prob_rez_sakt, prob_1x2_mc, fallback


# ══════════════════════════════════════════════════════════════════════════
# TUBACIONI 10-12 + fallback, me gjurme te plote
# ══════════════════════════════════════════════════════════════════════════
def ekzekuto(lam1, lam2, mkt, kaos=1.10, seed=42, aff=None, analitike=False, kontrollo=True):
    """lam1/lam2 = lambda QE SIMULOHET (_xg1_norm/_xg2_norm). mkt = (p1, px, p2) ose None."""
    if aff is None:
        aff = _konf("AFF_FIKS", AFF_FIKS)
    if analitike:
        H = ndertimi_H_analitike(lam1, lam2, kaos, False)
    else:
        H, _ = ndertimi_H_mc(lam1, lam2, kaos, False, MC_ITERACIONE, RHO_DC, seed)
    dalja, T = zgjidh_nga_H(H, lam1, lam2, aff, mkt)
    if kontrollo and not analitike:
        ref = simulim_monte_carlo_v2(lam1, lam2, kaos, False, iteracione=MC_ITERACIONE,
                                     seed=seed, aff=aff, mkt_1x2=mkt)
        assert ref[0] == dalja[0] and ref[1] == dalja[1] and ref[2] == dalja[2] \
            and ref[3] == dalja[3] and ref[4] == dalja[4], ("MOSPERPUTHJE me verbatim", ref[:2], dalja[:2])
        T["verbatim_ok"] = True
    p1r, pxr, p2r = (mkt if mkt else (None, None, None))
    rez, prob, p1x2_bl, fb = pas_simulimit(dalja[0], dalja[1], dalja[2], dalja[3],
                                           lam1, lam2, p1r, pxr, p2r)
    T["fallback"] = fb
    T["publikuar"] = rez
    T["p_publikuar"] = float(prob)
    T["prob_1x2_mc"] = dalja[3]
    T["over35"] = dalja[4]["Over 3.5"]
    T["H"] = H
    return T


def _tabela_top5(T, lamT):
    rr = ["| rank | skor | freq% | \\|tot-λT\\| | AFF faktor | AFF score |",
          "|---|---|---|---|---|---|"]
    for n, c in enumerate(T["top5"], 1):
        rr.append(f"| {n} | {c['skor']} | {c['freq']*100:.2f} | {c['difft']:.2f} | "
                  f"{c['aff_faktor']:.4f} | {c['aff_score']*100:.3f} |")
    return "\n".join(rr)


SHEMBUJT = [
    ("a) balancuar mesatar", 1.45, 1.35, (0.40, 0.29, 0.31)),
    ("b) favorit vendas",    1.85, 1.00, (0.55, 0.25, 0.20)),
    ("c) favorit i forte",   2.40, 0.75, (0.72, 0.17, 0.11)),
    ("d) loje e hapur",      1.90, 1.70, (0.42, 0.24, 0.34)),
    ("e) shume e hapur",     2.30, 2.00, (0.44, 0.22, 0.34)),
    ("f) e ngushte e ulet",  1.05, 0.95, (0.36, 0.33, 0.31)),
    ("g) favorit mysafir",   1.10, 1.75, (0.25, 0.27, 0.48)),
    # ── shtese: per te treguar rregullat qe s'ndizen te a-g ──
    ("h) EXTRA draw->LEAN",  1.55, 1.15, (0.40, 0.30, 0.30)),   # treg i ngushte, |Δλ|=0.40
    ("i) EXTRA treg≠model",  1.10, 1.50, (0.50, 0.27, 0.23)),   # tregu: vendas; λ: mysafir
    ("j) EXTRA LEAN +1 ulet", 0.60, 0.95, (0.30, 0.38, 0.32)),  # 0-0 -> LEAN -> 1-2 (+1)
]


def shembujt(kaos, seed, nseeds=20):
    out = []
    print("=" * 100)
    print(f"SHEMBUJT  (kaos={kaos}, seed={seed}, iteracione={MC_ITERACIONE}, AFF={AFF_FIKS}, "
          f"RHO={RHO_DC}, PRAG_LEAN={PRAG_LEAN}, WINNER_PRAG_TREG={WINNER_PRAG_TREG})")
    print("=" * 100)
    for lbl, l1, l2, mkt in SHEMBUJT:
        T = ekzekuto(l1, l2, mkt, kaos, seed)
        Ta = ekzekuto(l1, l2, mkt, kaos, None, analitike=True)
        # qendrueshmeria mbi seed-e
        pubs = {}
        for s in range(1, nseeds + 1):
            p = ekzekuto(l1, l2, mkt, kaos, s, kontrollo=False)["publikuar"]
            pubs[p] = pubs.get(p, 0) + 1
        lamT = l1 + l2
        # cfare do te ishte training_data.xg_1/xg_2 (inversi i XG_NORM, PA blend O/U)
        inv_live = ((l1 - XG_NORM_LIVE["XG_NORM_A_HOME"]) / XG_NORM_LIVE["XG_NORM_B_HOME"],
                    (l2 - XG_NORM_LIVE["XG_NORM_A_AWAY"]) / XG_NORM_LIVE["XG_NORM_B_AWAY"])
        inv_def = ((l1 - XG_NORM_A_HOME) / XG_NORM_B_HOME, (l2 - XG_NORM_A_AWAY) / XG_NORM_B_AWAY)
        print(f"\n### {lbl}:  λ = {l1:.2f} / {l2:.2f}  (λT = {lamT:.2f})   treg 1X2 = {mkt}")
        print(f"MC 1X2 = {T['prob_1x2_mc']}   verbatim_ok = {T.get('verbatim_ok')}")
        print(_tabela_top5(T, lamT))
        print(f"moda = {T['moda']} | pas AFF = {T['pas_aff']} (renditja {T['renditja_aff']})")
        print(f"moduli i fituesit = {T['drejtimi']} [{T['burimi_drejtimit']}]"
              f" | kandidatet pas filtrit = {T['kandidatet_pas_filtrit']}"
              f"{' (FILTRI U ZBRAZ -> lista e plote)' if T['filtri_zbrazi'] else ''}")
        print(f"pas fituesit = {T['pas_fituesit']} | draw->LEAN = {T['lean']} -> {T['pas_lean']}"
              f" | fallback = {T['fallback']}")
        print(f"PUBLIKUAR = {T['publikuar']}  P(skor) = {T['p_publikuar']*100:.2f}%  "
              f"P(tot>=4) = {T['p_tot_ge4_pa_rrumbullakim']*100:.2f}%")
        print(f"analitike (iter->inf): top5 = {[c['skor'] for c in Ta['top5']]} "
              f"-> publikuar {Ta['publikuar']} | qendrueshmeria {nseeds} seed-e: {pubs}")
        print(f"training_data.xg_1/xg_2 qe do ta jepnin kete λ pa blend O/U: "
              f"LIVE {inv_live[0]:.3f}/{inv_live[1]:.3f} | default {inv_def[0]:.3f}/{inv_def[1]:.3f}")
        out.append({
            "label": lbl, "lam_1": l1, "lam_2": l2, "market_1x2": mkt,
            "mc_1x2": T["prob_1x2_mc"], "top5": T["top5"], "mode": T["moda"],
            "after_aff": T["pas_aff"], "aff_order": T["renditja_aff"],
            "winner_direction": T["drejtimi"], "winner_source": T["burimi_drejtimit"],
            "after_winner": T["kandidatet_pas_filtrit"], "filter_emptied": T["filtri_zbrazi"],
            "pick_before_lean": T["pas_fituesit"], "lean": T["lean"], "after_lean": T["pas_lean"],
            "fallback": T["fallback"], "published": T["publikuar"], "p_published": T["p_publikuar"],
            "p_tot_ge4": T["p_tot_ge4_pa_rrumbullakim"], "analytic_published": Ta["publikuar"],
            "analytic_top5": [(c["skor"], c["freq"]) for c in Ta["top5"]],
            "seed_stability": pubs, "inv_live": inv_live, "inv_default": inv_def,
            "table": _tabela_top5(T, lamT),
        })
    return out


def rrjeta(kaos, seed, hap=0.2, lo=0.6, hi=3.0, analitike=False, mkt_mode="mc", aff=None):
    """mkt_mode='mc': tregu = 1X2 e vete matrices (burimi 'treg', prag 0.12).
       mkt_mode='none': pa treg (burimi 'mc', prag 0.15)."""
    if aff is None:
        aff = _konf("AFF_FIKS", AFF_FIKS)
    vals = np.round(np.arange(lo, hi + 1e-9, hap), 4)
    totet_pub = {}
    min_hyn = None; min_pub = None
    rreshta = []
    for l1 in vals:
        for l2 in vals:
            l1f, l2f = float(l1), float(l2)
            if analitike:
                H = ndertimi_H_analitike(l1f, l2f, kaos, False)
            else:
                H, _ = ndertimi_H_mc(l1f, l2f, kaos, False, MC_ITERACIONE, RHO_DC, seed)
            _ii, _jj = np.indices(H.shape)
            if mkt_mode == "mc":
                mkt = (float(H[_ii > _jj].sum()), float(H[_ii == _jj].sum()), float(H[_ii < _jj].sum()))
            else:
                mkt = None
            dalja, T = zgjidh_nga_H(H, l1f, l2f, aff, mkt)
            p1r, pxr, p2r = (mkt if mkt else (None, None, None))
            rez, prob, _, fb = pas_simulimit(dalja[0], dalja[1], dalja[2], dalja[3],
                                             l1f, l2f, p1r, pxr, p2r)
            g1, g2 = map(int, rez.split("-"))
            tot = g1 + g2
            totet_pub[tot] = totet_pub.get(tot, 0) + 1
            lamT = round(l1f + l2f, 4)
            ka4 = [c["skor"] for c in T["top5"] if sum(map(int, c["skor"].split("-"))) >= 4]
            if ka4 and (min_hyn is None or lamT < min_hyn[0]):
                min_hyn = (lamT, l1f, l2f, ka4, [c["skor"] for c in T["top5"]])
            if tot >= 4 and (min_pub is None or lamT < min_pub[0]):
                min_pub = (lamT, l1f, l2f, rez)
            rreshta.append({"l1": l1f, "l2": l2f, "lamT": lamT, "pub": rez, "tot": tot,
                            "dir": T["drejtimi"], "lean": T["lean"], "fb": fb,
                            "moda": T["moda"], "pas_aff": T["pas_aff"],
                            "top5": [c["skor"] for c in T["top5"]], "ka4_top5": ka4})
    return {"totet_pub": dict(sorted(totet_pub.items())), "min_hyn": min_hyn,
            "min_pub": min_pub, "rreshta": rreshta, "n": len(rreshta)}


def forma_mbyllur(kaos):
    print("\n" + "=" * 100)
    print("FORMA E MBYLLUR: 2-1 kundrejt 1-1 me AFF = a")
    print("=" * 100)
    a = AFF_FIKS
    print("score(k) = f(k) / (1 + a*|tot(k) - T|)")
    print("2-1 mund 1-1  <=>  f21/(1+a|3-T|) > f11/(1+a|2-T|)  <=>  f21/f11 > (1+a|3-T|)/(1+a|2-T|)")
    print("per 2 <= T <= 3:  r*(T) = (1 + a(3-T)) / (1 + a(T-2)) = (1.45 - 0.15T)/(0.70 + 0.15T)")
    res = {}
    # raporti f21/f11 nga modeli: Poisson+DC: (λ1/2)/(1-rho) = λ1/2.24; me mbi-shperndarje: numerik
    z = np.linspace(-8, 8, 4001); w = np.exp(-0.5 * z * z); w /= w.sum()

    def raport(l1):
        lam = np.clip(l1 + l1 * 0.18 * kaos * z, 0.05, 6.0)
        e2 = (w * lam ** 2 * np.exp(-lam)).sum(); e1 = (w * lam * np.exp(-lam)).sum()
        return e2 / (2.0 * e1) / (1.0 - RHO_DC)

    def zgjidh_l1(rstar):
        lo, hi = 0.2, 5.0
        for _ in range(60):
            m = (lo + hi) / 2
            if raport(m) < rstar:
                lo = m
            else:
                hi = m
        return (lo + hi) / 2

    for Tv in (2.0, 2.2, 2.4, 2.5, 2.6, 2.8, 3.0):
        r = (1 + a * abs(3 - Tv)) / (1 + a * abs(2 - Tv))
        l1_pois = 2.0 * (1.0 - RHO_DC) * r
        l1_mc = zgjidh_l1(r)
        res[Tv] = {"r_star": r, "lam1_min_poisson_dc": l1_pois, "lam1_min_mc_model": l1_mc,
                   "lam2_max": Tv - l1_mc}
        print(f"T={Tv:.1f}: r* = {r:.4f}  -> λ1 > {l1_pois:.3f} (Poisson+DC, λ1/2.24 > r*)"
              f" | λ1 > {l1_mc:.3f} (me mbi-shperndarjen e MC, kaos {kaos}) -> λ2 < {Tv - l1_mc:.3f}")
    # pa AFF (a=0): 2-1 mund 1-1 vetem nese f21 > f11 <=> λ1 > 2.24
    print(f"pa AFF (a=0): λ1 > 2.24 (Poisson+DC) | {zgjidh_l1(1.0):.3f} (modeli MC)")
    return res


def demo_hallka9():
    print("\n" + "=" * 100)
    print("HALLKA 9 — nga training_data.xg_1/xg_2 te λ e simuluar (demo)")
    print("=" * 100)
    rastet = [(1.40, 1.20, 1.85, 2.00), (1.40, 1.20, None, None), (1.80, 0.90, 1.60, 2.40),
              (1.20, 1.10, 2.30, 1.62)]
    out = []
    for nm, ov in (("default_kodi", {}), ("LIVE_19sep", XG_NORM_LIVE)):
        _KONF_OVERRIDE.clear(); _KONF_OVERRIDE.update(ov)
        for x1, x2, o, u in rastet:
            tr = {}
            l1, l2 = hallka9_blendi_totalit(x1, x2, o, u, tr)
            print(f"[{nm}] xg_1/xg_2 = {x1:.2f}/{x2:.2f}  O/U2.5 = {o}/{u}  -> pas XG_NORM "
                  f"{tr['pas_XG_NORM'][0]:.3f}/{tr['pas_XG_NORM'][1]:.3f}"
                  + (f"  p_over={tr['p_over']:.4f} λ_treg={tr['tot_mkt']:.3f} tot_mod={tr['tot_mod']:.3f}"
                     f" tgt={tr['tot_tgt']:.3f} shk={tr['shk_mkt']:.4f}" if "shk_mkt" in tr else "  (pa O/U -> s'ka blend)")
                  + f"  => λ SIMULUAR = {l1:.3f}/{l2:.3f} (λT {l1 + l2:.3f}, kundrejt xg_1+xg_2 {x1 + x2:.2f})")
            out.append({"konf": nm, "xg": (x1, x2), "ou": (o, u), "trace": tr, "lam": (l1, l2)})
    _KONF_OVERRIDE.clear()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kaos", type=float, default=1.10,
                    help="kaosi_liges (soccer_api.py:6396-6415): 1.05/1.10/1.20/1.25 (x1.12 nese vol>20)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--json", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.json"))
    ap.add_argument("--pa-rrjete", action="store_true")
    args = ap.parse_args()

    rez = {"kaos": args.kaos, "seed": args.seed}
    rez["hallka9"] = demo_hallka9()
    rez["shembujt"] = shembujt(args.kaos, args.seed)
    rez["forma_mbyllur"] = forma_mbyllur(args.kaos)

    if not args.pa_rrjete:
        print("\n" + "=" * 100)
        print("RRJETA λ1, λ2 ∈ 0.6..3.0 hap 0.2 (169 cifte)")
        print("=" * 100)
        G = {}
        for emri, kw in (("mc_seed_treg=MC", dict(analitike=False, mkt_mode="mc")),
                         ("analitike_treg=MC", dict(analitike=True, mkt_mode="mc")),
                         ("mc_seed_pa_treg", dict(analitike=False, mkt_mode="none"))):
            g = rrjeta(args.kaos, args.seed, **kw)
            G[emri] = {k: v for k, v in g.items() if k != "rreshta"}
            print(f"[{emri}] totalet e publikuara {g['totet_pub']} (n={g['n']})")
            print(f"   tot>=4 HYN ne top-5 per here te pare: {g['min_hyn']}")
            print(f"   tot>=4 PUBLIKOHET per here te pare:   {g['min_pub']}")
            if emri == "mc_seed_treg=MC":
                G[emri]["rreshta"] = g["rreshta"]
        # rrjete me e imet (0.05) per pragjet, analitike (pa zhurme)
        print("\nRrjete e imet 0.05 (analitike, treg=MC) per pragjet:")
        gf = rrjeta(args.kaos, args.seed, hap=0.05, analitike=True, mkt_mode="mc")
        G["imet_0.05_analitike"] = {k: v for k, v in gf.items() if k != "rreshta"}
        print(f"   totalet {gf['totet_pub']} (n={gf['n']})")
        print(f"   tot>=4 HYN ne top-5: {gf['min_hyn']}")
        print(f"   tot>=4 PUBLIKOHET:   {gf['min_pub']}")
        # te njejtat pragje vetem per cifte TE BALANCUARA (|λ1-λ2| <= 0.20)
        bal = [r for r in gf["rreshta"] if abs(r["l1"] - r["l2"]) <= 0.2001]
        b_hyn = min((r for r in bal if r["ka4_top5"]), key=lambda r: r["lamT"], default=None)
        b_pub = min((r for r in bal if r["tot"] >= 4), key=lambda r: r["lamT"], default=None)
        print(f"   BALANCUAR |Δλ|<=0.2: HYN {b_hyn and (b_hyn['lamT'], b_hyn['l1'], b_hyn['l2'], b_hyn['ka4_top5'])}"
              f" | PUBLIKOHET {b_pub and (b_pub['lamT'], b_pub['l1'], b_pub['l2'], b_pub['pub'])}")
        G["imet_0.05_analitike"]["balancuar_hyn"] = b_hyn and (b_hyn['lamT'], b_hyn['l1'], b_hyn['l2'], b_hyn['ka4_top5'])
        G["imet_0.05_analitike"]["balancuar_pub"] = b_pub and (b_pub['lamT'], b_pub['l1'], b_pub['l2'], b_pub['pub'])
        # sa cifte publikojne tot>=4, dhe tot=0/1
        pub4 = [r for r in gf["rreshta"] if r["tot"] >= 4]
        print(f"   cifte qe publikojne tot>=4: {len(pub4)}; shembuj: "
              f"{[(r['l1'], r['l2'], r['pub']) for r in sorted(pub4, key=lambda r: r['lamT'])[:8]]}")
        # diagnostika per secilin total te publikuar: diapazoni i λT dhe skoret
        diag = {}
        for nm_g, rows in (("0.2_mc", G["mc_seed_treg=MC"]["rreshta"]), ("0.05_analitike", gf["rreshta"])):
            d = {}
            for r in rows:
                e = d.setdefault(r["tot"], {"n": 0, "lamT_min": 9, "lamT_max": 0, "skoret": {}})
                e["n"] += 1; e["lamT_min"] = min(e["lamT_min"], r["lamT"]); e["lamT_max"] = max(e["lamT_max"], r["lamT"])
                e["skoret"][r["pub"]] = e["skoret"].get(r["pub"], 0) + 1
            nl = sum(1 for r in rows if r["lean"]); nf = sum(1 for r in rows if r["fb"])
            print(f"\n[{nm_g}] per total te publikuar (λT min..max, skoret):  LEAN u ndez {nl}x, fallback {nf}x")
            for t in sorted(d):
                print(f"   tot {t}: n={d[t]['n']:4d}  λT {d[t]['lamT_min']:.2f}..{d[t]['lamT_max']:.2f}  {d[t]['skoret']}")
            # λT ku tot>=4 behet shumica
            bins = {}
            for r in rows:
                b = round(math.floor(r["lamT"] / 0.5) * 0.5, 1)
                bb = bins.setdefault(b, [0, 0]); bb[0] += 1; bb[1] += (r["tot"] >= 4)
            print("   pjesa e tot>=4 sipas λT (kova 0.5): "
                  + ", ".join(f"[{b:.1f},{b + 0.5:.1f}): {v[1]}/{v[0]}" for b, v in sorted(bins.items())))
            diag[nm_g] = {"per_total": d, "lean": nl, "fallback": nf,
                          "bins": {str(b): v for b, v in sorted(bins.items())}}
            if nm_g == "0.05_analitike":
                # ku publikohet 0-0 / tot<=1 me λT te larte; ku ndizet LEAN
                lean_rows = [r for r in rows if r["lean"]]
                print(f"   LEAN shembuj: {[(r['l1'], r['l2'], r['pub']) for r in lean_rows[:6]]}")
                fb_rows = [r for r in rows if r["fb"]]
                print(f"   fallback shembuj: {[(r['l1'], r['l2'], r['pub']) for r in fb_rows[:6]]}")
        rez["rrjeta"] = G
        rez["rrjeta_diag"] = diag

        # EFEKTI I AFF: e njejta rrjete e imet me AFF=0 (frekuence e paster) kundrejt 0.15
        g0 = rrjeta(args.kaos, args.seed, hap=0.05, analitike=True, mkt_mode="mc", aff=0.0)
        diffs = [(a, b) for a, b in zip(gf["rreshta"], g0["rreshta"]) if a["pub"] != b["pub"]]
        moda_ndr = sum(1 for r in gf["rreshta"] if r["moda"] != r["pas_aff"])
        kal = {}
        for a, b in diffs:
            k = f"{b['pub']}->{a['pub']}"
            kal[k] = kal.get(k, 0) + 1
        print(f"\nEFEKTI I AFF (rrjeta 0.05, analitike): AFF ndryshon renditjen e pare te top-5 ne {moda_ndr}/{gf['n']};"
              f" ndryshon skorin e PUBLIKUAR ne {len(diffs)}/{gf['n']}")
        print(f"   totalet me AFF=0: {g0['totet_pub']}  | me AFF=0.15: {gf['totet_pub']}")
        print(f"   kalimet me te shpeshta (AFF=0 -> AFF=0.15): {sorted(kal.items(), key=lambda x: -x[1])[:12]}")
        rez["aff_efekti"] = {"moda_ndryshon": moda_ndr, "pub_ndryshon": len(diffs), "n": gf["n"],
                             "totet_aff0": g0["totet_pub"], "totet_aff015": gf["totet_pub"],
                             "kalimet": kal, "min_pub_aff0": g0["min_pub"], "min_hyn_aff0": g0["min_hyn"]}

        # verifikim i formes se mbyllur mbi H analitike (2-1 kundrejt 1-1 ne kufi)
        print("\nVerifikim i formes se mbyllur me H analitike (raporti f21/f11 ne pragun λ1, cfaredo λ2):")
        fm = rez["forma_mbyllur"]
        for Tv in (2.6, 2.8, 3.0):
            l1 = fm[Tv]["lam1_min_mc_model"]
            for l2 in (0.6, 1.0, 1.4):
                H = ndertimi_H_analitike(l1, l2, args.kaos, False)
                print(f"   T={Tv}: λ1={l1:.3f}, λ2={l2}: f21/f11 = {H[2, 1] / H[1, 1]:.4f} (r* = {fm[Tv]['r_star']:.4f})")

    with open(args.json, "w") as f:
        json.dump(rez, f, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print(f"\nJSON -> {args.json}")


if __name__ == "__main__":
    main()
