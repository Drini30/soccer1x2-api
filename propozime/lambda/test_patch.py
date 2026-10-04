#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEST i patch-it lambda.patch (lexim vetem; asgje ne repo s'preket, asnje rrjet).

Ekzekutimi (numpy kerkohet; venv-i i scratchpad-it e ka):
    ./venv/bin/python test_patch.py

Cfare provohet:
  T0  py_compile i te dy skedareve.
  T1  simulim_monte_carlo_v2: ORIGJINALI == PATCH-i pa gjurma == PATCH-i me gjurma,
      tuple-i i kthimit identik (barazi e thelle + json me radhen e celesave) mbi nje
      rrjete lambda x seed x kaos x derbi x treg x aff, plus variantet WINNER_BURIMI 0/1/2,
      CS_LEAN_XG aktiv, TOTAL_CALIB != 0. Gjurma: json.dumps(allow_nan=False) OK,
      vetem tipa te paster Python, dhe perputhet me skorin e kthyer.
  T2  analizo_ndeshjen_premium_master I PLOTE (te dy versionet, me burimet e te dhenave
      te zevendesuara me stub deterministe): te 5 outputet identike (extradb pa
      `gjurma_db`), mbi raste te rastesishme + raste te detyruara (pa O/U, boost,
      fallback, burim MC). gjurma_db: json i paster, lam_1/lam_2 == λ qe iu dha
      simulimit, rez == skori i publikuar, celesat s'perplasen me training_data,
      zinxhiri xg_1 -> A/B -> shk_treg rindertohet.
  T3  task_ruaj_skedinen_ne_db: payload-i identik me origjinalin; me gjurmet vetem
      training_data i DB-se merr celesat e rinj, ndersa dict-i qe shkon te cache-i
      (nd["training_data"]) mbetet objekti i njejte me te njejtat vlera.
  T4  sa mire e riprodhon simulimin λ e rrumbullakuar ne 4 shifra (informative).
  T5  dy gjenerime te se njejtes ndeshje me task_ruaj te VERTETE (ngrirja + upsert ne
      memorie): gjenerimi 1 ngrin rezultati_sakt/dist_gola/koef, gjenerimi 2 (kuota te
      levizura ose identike) rishkruan training_data. Shenja (rez + dist_gola ⊇ dist_shenja)
      duhet ta dalloje pa asnje gabim gjurmen e gjenerimit te publikuar; prova e vjeter
      (vetem rez) duhet te deshtoje — kjo e provon problemin. Shkruan fixture_2gjen.sql
      per kontrolli_lambda.sql dhe sql/filtri/2,3 ne PostgreSQL.
  T6  AFF NaN ne model_config: output identik, gjurma json e paster (piket AFF -> null) dhe
      rreshti ruhet; gjurme e prishur qellimisht (NaN / numpy.float32) -> rreshti ruhet me
      payload IDENTIK me origjinalin (humbet vetem gjurma, jo ndeshja).
"""
import ast
import copy
import hashlib
import json
import math
import os
import py_compile
import random
import sys
import types

import numpy as np

KETU = os.path.dirname(os.path.abspath(__file__))
ORIG = "/home/user/soccer1x2-api/soccer_api.py"
PAT = os.path.join(KETU, "soccer_api.patched.py")

DESHTIME = []


def kontrollo(kushti, mesazhi):
    if not kushti:
        DESHTIME.append(mesazhi)
        print("  DESHTIM:", mesazhi)


# ──────────────────────────────────────────────────────────────────────────
# Moduli i rremë per varesite qe s'jane te instaluara + rrjeti i bllokuar
# ──────────────────────────────────────────────────────────────────────────
class _Bllokuar(Exception):
    pass


def _rrjet(*a, **k):
    raise _Bllokuar("RRJETI I BLLOKUAR NE TEST")


def _instalo_modulet_e_rreme():
    class _App:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, emri):
            def _dek(*a, **k):
                if a and callable(a[0]) and not k and len(a) == 1:
                    return a[0]
                return lambda f: f
            return _dek

    class _Bosh:
        def __init__(self, *a, **k):
            pass

    fa = types.ModuleType("fastapi")
    fa.FastAPI = _App
    fa.BackgroundTasks = _Bosh
    fa.Request = _Bosh
    fa.Header = lambda *a, **k: None
    fa.HTTPException = type("HTTPException", (Exception,), {})
    fa.Query = lambda *a, **k: None
    fa.Body = lambda *a, **k: None
    fr = types.ModuleType("fastapi.responses")
    fr.HTMLResponse = _Bosh
    fr.JSONResponse = _Bosh
    fr.RedirectResponse = _Bosh
    fr.StreamingResponse = _Bosh
    fr.PlainTextResponse = _Bosh
    fr.FileResponse = _Bosh
    fm = types.ModuleType("fastapi.middleware")
    fc = types.ModuleType("fastapi.middleware.cors")
    fc.CORSMiddleware = _Bosh
    pd = types.ModuleType("pydantic")
    pd.BaseModel = type("BaseModel", (), {})
    rq = types.ModuleType("requests")
    for m in ("get", "post", "patch", "put", "delete", "head", "request"):
        setattr(rq, m, _rrjet)
    rq.utils = types.SimpleNamespace(quote=lambda s, safe="": s)
    rq.exceptions = types.SimpleNamespace(RequestException=Exception, Timeout=Exception)
    rq.RequestException = Exception
    rq.Session = lambda *a, **k: types.SimpleNamespace(get=_rrjet, post=_rrjet)
    for emri, mod in (("fastapi", fa), ("fastapi.responses", fr), ("fastapi.middleware", fm),
                      ("fastapi.middleware.cors", fc), ("pydantic", pd), ("requests", rq)):
        sys.modules[emri] = mod


_LLOJET_E_SIGURTA = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.AugAssign,
                     ast.Try, ast.If, ast.FunctionDef, ast.ClassDef)


def ngarko(shteg):
    """Ekzekuton vetem perkufizimet e nivelit te modulit (funksione/konstante/importe),
    JO thirrjet e nivelit te larte (Expr), qe asgje te mos nise (thread-e, rrjet)."""
    burimi = open(shteg, encoding="utf-8").read()
    pema = ast.parse(burimi, shteg)
    ns = {"__name__": "soccer_api_test", "__file__": shteg, "__builtins__": __builtins__}
    deshtuan = []
    for nyja in pema.body:
        if not isinstance(nyja, _LLOJET_E_SIGURTA):
            continue
        mod = ast.Module(body=[nyja], type_ignores=[])
        try:
            exec(compile(mod, shteg, "exec"), ns)
        except Exception as e:  # p.sh. importe opsionale (xgboost) -> te njejtat ne te dy
            deshtuan.append((getattr(nyja, "lineno", "?"), type(e).__name__))
    return ns, deshtuan


# ──────────────────────────────────────────────────────────────────────────
# _konf i kontrolluar nga testi (model_config i simuluar)
# ──────────────────────────────────────────────────────────────────────────
KONF = {}


def _konf_stub(emri, parazgjedhje):
    v = KONF.get(emri)
    return float(v) if v is not None else float(parazgjedhje)


KONF_LIVE = {"XG_NORM_A_HOME": -0.1438, "XG_NORM_B_HOME": 1.1505,
             "XG_NORM_A_AWAY": 0.2989, "XG_NORM_B_AWAY": 0.8666}


def lloj_i_paster(x, shteg="$"):
    """Kthen listen e shkeljeve: vetem dict/list/str/int/float/bool/None te Python-it."""
    gab = []
    t = type(x)
    if t is dict:
        for k, v in x.items():
            if type(k) is not str:
                gab.append(f"{shteg}: celes jo-str {k!r} ({type(k).__name__})")
            gab += lloj_i_paster(v, f"{shteg}.{k}")
    elif t is list:
        for i, v in enumerate(x):
            gab += lloj_i_paster(v, f"{shteg}[{i}]")
    elif t in (str, int, bool, type(None)):
        pass
    elif t is float:
        if not math.isfinite(x):
            gab.append(f"{shteg}: float jo i fundem {x}")
    else:
        gab.append(f"{shteg}: tip i ndaluar {t.__module__}.{t.__name__}")
    return gab


def js(x):
    return json.dumps(x, ensure_ascii=False, default=repr)


# ──────────────────────────────────────────────────────────────────────────
# T5: PostgREST ne memorie (predictions) — upsert merge-duplicates + GET i ngrirjes
# ──────────────────────────────────────────────────────────────────────────
class _Pergjigje:
    def __init__(self, kodi, trupi=None):
        self.status_code = kodi; self._t = trupi if trupi is not None else []; self.text = ""

    def json(self):
        return self._t


class _DbRreme:
    """Sa i duhet task_ruaj: GET ?id=in.(..)&select=a,b,..  dhe POST upsert (kolonat e
    payload-it mbishkruhen, te tjerat mbeten — si resolution=merge-duplicates)."""

    def __init__(self):
        self.rreshta = {}

    def get(self, url, headers=None, timeout=None, **k):
        import re
        import urllib.parse
        q = urllib.parse.urlparse(url).query
        m = re.search(r"id=in\.\(([^)]*)\)", q)
        ids = m.group(1).split(",") if m else []
        sel = re.search(r"select=([^&]*)", q).group(1).split(",")
        out = [{c: self.rreshta[i].get(c) for c in sel} for i in ids if i in self.rreshta]
        return _Pergjigje(200, json.loads(json.dumps(out)))

    def post(self, url, headers=None, json=None, timeout=None):
        import json as _j
        pako = _j.loads(_j.dumps(json, allow_nan=False))           # si requests -> jsonb
        self.rreshta.setdefault(str(pako["id"]), {}).update(pako)
        return _Pergjigje(201)


def shenja_perputhet(rresht):
    """E njejta prove si kontrolli_lambda.sql:
    zgjedhja.rez = rezultati_sakt  DHE  dist_gola @> zgjedhja.dist_shenja (jo bosh)."""
    td = rresht.get("training_data") or {}
    z = td.get("zgjedhja") or {}
    sh = z.get("dist_shenja")
    dg = rresht.get("dist_gola")
    rez_ok = z.get("rez") == (rresht.get("rezultati_sakt") or "").replace(" ", "")
    if not (isinstance(sh, dict) and sh and isinstance(dg, dict)):
        return False, rez_ok
    return rez_ok and all(k in dg and dg[k] == v for k, v in sh.items()), rez_ok


def t5_prejardhja(ns_o, ns_p, rast, ekzekuto):
    print("=" * 78)
    print("T5  dy gjenerime me task_ruaj te VERTETE: gjenerimi 1 ngrin skorin/dist_gola/koef,")
    print("    gjenerimi 2 (kuota te levizura ose identike) rishkruan training_data")
    db = _DbRreme()
    ns_p["requests"] = types.SimpleNamespace(get=db.get, post=db.post, patch=db.post)
    ns_p["SUPABASE_URL_PREDS"] = "https://x.supabase.co/rest/v1/predictions"
    ns_p["SUPABASE_SERVICE_HEADERS"] = {"apikey": "x"}
    rng = random.Random(51003)
    N = 160
    st = {"ndeshje": N, "inpute_identike": 0, "gjurme_e_publikimit_e_vertete": 0, "shenja_pranon": 0,
          "shenja_pranim_i_gabuar": 0, "shenja_refuzim_i_gabuar": 0, "skori_pranon": 0,
          "skori_pranim_i_gabuar": 0, "skori_ndryshoi_ne_gjen2": 0, "ngrirja_e_shkelur": 0}
    dl = []
    rreshta = []

    def _pa_kohe(g):
        g = copy.deepcopy(g); g.pop("gjeneruar_ne", None); return g

    for i in range(N):
        r1 = rast(5000 + i, rng)
        konf = dict(KONF_LIVE)

        def ruaj(out, r=r1):
            _, _, rez, koef, ex = out
            nd = {"id": r["id"], "ndeshja": f"{r['e1']} vs {r['e2']}", "data": "2026-10-04", "statusi": "NS",
                  "rezultati_sakt": rez, "koef_rez_sakt": koef, "dist_gola": ex["dist_gola"],
                  "training_data": ex["training_data"], "is_premium": False}
            ns_p["task_ruaj_skedinen_ne_db"]([nd], gjurmet={str(r["id"]): ex["gjurma_db"]})

        g1 = ekzekuto(ns_p, r1, konf); ruaj(g1)
        r2 = copy.deepcopy(r1)
        identike = (i % 4 == 0)
        if not identike:     # levizje tipike e kuotave mes mbremjes dhe dites se ndeshjes
            r2["k"] = tuple("%.2f" % (float(x) * (1 + rng.uniform(-0.04, 0.04))) for x in r1["k"])
            if "Over 2.5" in r2["odds"]:
                d = rng.uniform(-0.06, 0.06)
                r2["odds"]["Over 2.5"] = "%.2f" % max(1.02, float(r1["odds"]["Over 2.5"]) + d)
                r2["odds"]["Under 2.5"] = "%.2f" % max(1.02, float(r1["odds"]["Under 2.5"]) - d)
        g2 = ekzekuto(ns_p, r2, konf); ruaj(g2)
        st["inpute_identike"] += int(identike)
        rr = db.rreshta[str(r1["id"])]
        # harness-i: ngrirja punoi (skori/dist/koef nga gjen. 1), training_data nga gjen. 2
        ngrirja_ok = (rr["rezultati_sakt"] == g1[2] and rr["dist_gola"] == g1[4]["dist_gola"]
                      and rr["koef_rez_sakt"] == g1[3]
                      and rr["training_data"]["gjeneruar_ne"] == g2[4]["gjurma_db"]["gjeneruar_ne"]
                      and rr["training_data"]["lam_1"] == g2[4]["gjurma_db"]["lam_1"])
        st["ngrirja_e_shkelur"] += int(not ngrirja_ok)
        e_vertete = _pa_kohe(g1[4]["gjurma_db"]) == _pa_kohe(g2[4]["gjurma_db"])
        shenja, rez_ok = shenja_perputhet(rr)
        st["gjurme_e_publikimit_e_vertete"] += int(e_vertete)
        st["shenja_pranon"] += int(shenja)
        st["shenja_pranim_i_gabuar"] += int(shenja and not e_vertete)
        st["shenja_refuzim_i_gabuar"] += int(e_vertete and not shenja)
        st["skori_pranon"] += int(rez_ok)
        st["skori_pranim_i_gabuar"] += int(rez_ok and not e_vertete)
        st["skori_ndryshoi_ne_gjen2"] += int(g2[2] != g1[2])
        if rez_ok and not e_vertete:
            dl.append(abs(g2[4]["gjurma_db"]["lam_1"] - g1[4]["gjurma_db"]["lam_1"])
                      + abs(g2[4]["gjurma_db"]["lam_2"] - g1[4]["gjurma_db"]["lam_2"]))
        if identike:
            kontrollo(e_vertete, f"T5 inpute identike por gjurme tjeter ({r1['id']})")
        rreshta.append({"id": r1["id"], "rresht": copy.deepcopy(rr), "e_vertete": e_vertete})
    kontrollo(st["ngrirja_e_shkelur"] == 0, "T5 harness-i: ngrirja s'u emulua si ne prodhim")
    kontrollo(st["shenja_pranim_i_gabuar"] == 0, "T5 shenja pranoi gjurme te nje gjenerimi tjeter")
    kontrollo(st["shenja_refuzim_i_gabuar"] == 0, "T5 shenja refuzoi gjurmen e vete gjenerimit te publikuar")
    kontrollo(st["skori_pranim_i_gabuar"] > 0, "T5 pritej qe prova e skorit te gabonte (kjo e provon problemin)")
    print("  ", json.dumps(st, ensure_ascii=False))
    if dl:
        dl.sort()
        print(f"   prova e vjeter (vetem skori) do t'i pranonte gabimisht {len(dl)} rreshta; "
              f"|Δλ1|+|Δλ2| mes tyre: mesorja {dl[len(dl) // 2]:.4f}, max {dl[-1]:.4f}")
    return rreshta


def shkruaj_fixture(t5_rreshta, ns_o, rast, ekzekuto, BUILD_RI):
    """fixture_2gjen.sql: rreshtat e T5 (vula e re, gjurma nga gjen. 2, kolonat e ngrira nga gjen. 1)
    + rreshta te kodit origjinal + raste kufitare. Tabela `pritjet` mban pergjigjet e sakta."""
    rng = random.Random(777)
    rreshta = []      # (id, data, ndeshja, statusi, is_premium, rezultati, rezultati_sakt, dist, koef, td, e_vertete)

    def ft():
        return f"{rng.randint(0, 4)} - {rng.randint(0, 3)}"
    for x in t5_rreshta:
        rr = x["rresht"]
        rreshta.append([x["id"], "2026-10-04", rr["ndeshja"], "FT", rng.random() < 0.3, ft(),
                        rr["rezultati_sakt"], rr["dist_gola"], rr["koef_rez_sakt"], rr["training_data"], x["e_vertete"]])
    # kufitare mbi rreshtat e rinj (a, b nisin nga gjurme TE VERTETA te publikimit: rojat duhet t'i refuzojne)
    a = copy.deepcopy(rreshta[0]); a[0] = 9_000_001; a[9]["zgjedhja"]["dist_shenja"] = {}; a[10] = False
    b = copy.deepcopy(rreshta[4]); b[0] = 9_000_002; b[7] = None; b[10] = False
    c = copy.deepcopy(rreshta[3]); c[0] = 9_000_003; c[9]["build"] = "2026-10-10-a"; c[10] = None   # vule e ardhshme
    d = copy.deepcopy(rreshta[5]); d[0] = 9_000_004; d[3] = "NS"; d[5] = None; d[10] = None         # pa mbaruar
    rreshta += [a, b, c, d]
    # kodi ORIGJINAL: dita e deploy-it (para tij) dhe me pare
    for j, (data, n) in enumerate((("2026-10-03", 5), ("2026-10-01", 3))):
        for k in range(n):
            r = rast(7000 + 10 * j + k, rng)
            _, _, rez, koef, ex = ekzekuto(ns_o, r, dict(KONF_LIVE))
            rreshta.append([r["id"], data, f"{r['e1']} vs {r['e2']}", "FT", rng.random() < 0.3, ft(),
                            rez, ex["dist_gola"], koef, ex["training_data"], None])
    e = copy.deepcopy(rreshta[-1]); e[0] = 9_000_005; e[1] = "2026-09-20"; e[9].pop("build", None)   # pa vule
    rreshta.append(e)

    def q(s):
        return "NULL" if s is None else "'" + str(s).replace("'", "''") + "'"

    def jb(v):
        return "NULL" if v is None else q(json.dumps(v, allow_nan=False)) + "::jsonb"
    out = ["DROP TABLE IF EXISTS predictions; DROP TABLE IF EXISTS pritjet;",
           "CREATE TABLE predictions (id bigint primary key, data date, ndeshja text, statusi text, "
           "is_premium boolean, rezultati text, rezultati_sakt text, dist_gola jsonb, koef_rez_sakt text, "
           "training_data jsonb);",
           "CREATE TABLE pritjet (id bigint primary key, gjurma_e_publikimit boolean);"]
    for r in rreshta:
        out.append("INSERT INTO predictions VALUES (%d, %s, %s, %s, %s, %s, %s, %s, %s, %s);" % (
            r[0], q(r[1]), q(r[2]), q(r[3]), "true" if r[4] else "false", q(r[5]), q(r[6]), jb(r[7]),
            q(r[8]), jb(r[9])))
        if r[10] is not None:
            out.append("INSERT INTO pritjet VALUES (%d, %s);" % (r[0], "true" if r[10] else "false"))
    shteg = os.path.join(KETU, "fixture_2gjen.sql")
    with open(shteg, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    # pergjigjet e pritura per SQL-in (llogaritur ketu ne Python)
    pas = [r for r in rreshta if r[1] >= "2026-10-03" and r[9] is not None]
    ka_lam = [r for r in pas if "lam_1" in r[9]]
    pub = [r for r in ka_lam if shenja_perputhet({"training_data": r[9], "dist_gola": r[7],
                                                   "rezultati_sakt": r[6]})[0]]

    def filtri(r, vulat_shtese):
        b = (r[9] or {}).get("build", "") or ""
        return (r[1] >= "2026-09-18" and r[3] in ("FT", "AET", "PEN", "AWD", "WO") and r[5] is not None
                and (b.startswith("2026-09-1") or b in vulat_shtese))
    print(f"  fixture_2gjen.sql: {len(rreshta)} rreshta. PRITET nga kontrolli_lambda.sql: "
          f"rreshta_pas_deploy={len(pas)}, me_lam={len(ka_lam)}, gjurma_e_publikimit={len(pub)}, "
          f"gjurma_e_mevonshme={len(ka_lam) - len(pub)}")
    print(f"  PRITET nga sql/filtri/3 ndeshje_gjithsej: origjinali={sum(filtri(r, ()) for r in rreshta)}, "
          f"me filtri_build.patch={sum(filtri(r, (BUILD_RI,)) for r in rreshta)}")


# ══════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 78)
    print("T0  py_compile")
    for s in (ORIG, PAT):
        py_compile.compile(s, doraise=True)
        print("  OK", s)

    _instalo_modulet_e_rreme()
    ns_o, f_o = ngarko(ORIG)
    ns_p, f_p = ngarko(PAT)
    print(f"  nyje te pa-ekzekutueshme (te njejtat ne te dy?): {len(f_o)} / {len(f_p)}",
          "PO" if [x[1] for x in f_o] == [x[1] for x in f_p] else "JO")
    for ns in (ns_o, ns_p):
        ns["_konf"] = _konf_stub
        ns["_api_sports_get"] = _rrjet
    print("  BUILD orig:", ns_o.get("BUILD"), "| patch:", ns_p.get("BUILD"))

    # ── T1: simulim_monte_carlo_v2 ─────────────────────────────────────────
    print("=" * 78)
    print("T1  simulim_monte_carlo_v2: origjinali vs patch (pa/me gjurma)")
    sim_o = ns_o["simulim_monte_carlo_v2"]
    sim_p = ns_p["simulim_monte_carlo_v2"]
    lam_cifte = [(0.25, 0.20), (0.55, 0.90), (0.90, 0.55), (1.10, 1.10), (1.30, 1.25),
                 (1.279, 1.348), (1.45, 0.95), (1.62, 1.18), (2.10, 0.70), (0.70, 2.30),
                 (2.30, 1.95), (3.10, 1.40), (0.40, 0.10), (4.80, 0.30)]
    tregje = [None, (0.62, 0.23, 0.15), (0.38, 0.30, 0.32), (0.18, 0.24, 0.58), (0.45, 0.27, 0.28)]
    variante = [
        ("baza", {}, {}),
        ("burimi_MC", {"WINNER_BURIMI": 0}, {}),
        ("burimi_FLB", {"WINNER_BURIMI": 2}, {}),
        ("CS_aktiv", {}, {"CS_LEAN_XG": 0.8}),
        ("TOTAL_CALIB", {}, {"TOTAL_CALIB": 0.25}),
        ("PRAG_LEAN_0.10", {}, {"PRAG_LEAN": 0.10}),
    ]
    n_rasteve = 0
    mbulimi = {"lean": 0, "lean_plus1": 0, "mbrojtja": 0, "cs": 0, "drejtimi_None": 0,
               "drejtimi_1": 0, "drejtimi_2": 0, "burimi_mc": 0, "burimi_treg": 0, "burimi_treg_korr": 0}
    if os.environ.get("KAPERCE_T1"):          # vetem per iterim te shpejte; ekzekutimi zyrtar e ka T1
        print("  (T1 U KAPERCYE nga KAPERCE_T1 — ky s'eshte ekzekutim i plote)")
        DESHTIME.append("T1 u kapercye (KAPERCE_T1)")
        variante = []
    for emri_v, konf_v, konst_v in variante:
        KONF.clear(); KONF.update(konf_v)
        ruaj = {}
        for k, v in konst_v.items():
            ruaj[k] = (ns_o[k], ns_p[k]); ns_o[k] = v; ns_p[k] = v
        try:
            for (l1, l2) in lam_cifte:
                for seed in (1, 7, 2026, 3141592653):
                    for kaos, derbi in ((1.05, False), (1.10, True), (1.25, False)):
                        for mkt in tregje:
                            for aff in (0.15, 0.5):
                                kw = dict(iteracione=50_000, seed=seed, aff=aff, mkt_1x2=mkt)
                                r_o = sim_o(l1, l2, kaos, derbi, **kw)
                                r_p0 = sim_p(l1, l2, kaos, derbi, **kw)
                                gj = {}
                                r_p1 = sim_p(l1, l2, kaos, derbi, gjurma=gj, **kw)
                                n_rasteve += 1
                                kontrollo(r_o == r_p0 and js(r_o) == js(r_p0),
                                          f"T1 {emri_v} {l1}/{l2} s={seed}: patch pa gjurma != origjinali")
                                kontrollo(r_o == r_p1 and js(r_o) == js(r_p1),
                                          f"T1 {emri_v} {l1}/{l2} s={seed}: patch me gjurma != origjinali")
                                kontrollo(not lloj_i_paster(gj), f"T1 tipa: {lloj_i_paster(gj)[:3]}")
                                try:
                                    json.dumps(gj, allow_nan=False)
                                except Exception as e:
                                    kontrollo(False, f"T1 json: {e}")
                                rez, prob, freq, p1x2, treg = r_o
                                kontrollo(gj["rez_sim"] == rez, "T1 rez_sim != skori i kthyer")
                                kontrollo(gj["p_mc"] == [p1x2["p1"], p1x2["px"], p1x2["p2"]], "T1 p_mc")
                                # rez_fit rindertohet nga top5 + drejtimi (logjika e filtrit)
                                t5 = [x[0] for x in gj["top5"]]
                                d = gj["drejtimi"]
                                def _ok(s):
                                    a, b = map(int, s.split("-"))
                                    return (d == "1" and a > b) or (d == "2" and b > a) or d is None
                                fil = [s for s in t5 if _ok(s)]
                                pritet = fil[0] if fil else t5[0]
                                kontrollo(gj["rez_fit"] == pritet, f"T1 rez_fit {gj['rez_fit']} != {pritet}")
                                kontrollo(gj["mbrojtja"] == (not fil), "T1 mbrojtja")
                                if not gj["lean"] and not gj["cs"]:
                                    kontrollo(gj["rez_fit"] == rez, "T1 pa LEAN/CS por rez_fit != rez")
                                    pf = dict((x[0], x[1]) for x in gj["top5"])[rez]
                                    kontrollo(abs(pf - prob) < 1.01e-4, f"T1 prob {pf} vs {prob}")
                                if gj["lean"]:
                                    a, b = map(int, gj["rez_fit"].split("-"))
                                    kontrollo(a == b, "T1 LEAN pa barazim")
                                for k in ("lean", "lean_plus1", "mbrojtja", "cs"):
                                    mbulimi[k] += int(bool(gj[k]))
                                mbulimi["drejtimi_" + str(d)] += 1
                                mbulimi["burimi_" + gj["burimi"]] += 1
        finally:
            for k, (vo, vp) in ruaj.items():
                ns_o[k] = vo; ns_p[k] = vp
    KONF.clear()
    print(f"  {n_rasteve} raste x 3 thirrje; deshtime deri tani: {len(DESHTIME)}")
    print("  mbulimi i degeve:", mbulimi)
    shembull = {}
    sim_p(1.279, 1.348, 1.10, False, iteracione=50_000, seed=12345, aff=0.15,
          mkt_1x2=(0.40, 0.29, 0.31), gjurma=shembull)
    print("  shembull gjurme:", json.dumps(shembull, ensure_ascii=False))

    # ── T2: analizo_ndeshjen_premium_master i plote ───────────────────────
    print("=" * 78)
    print("T2  analizo_ndeshjen_premium_master: origjinali vs patch")
    regjistri = {}

    def _mbeshtjell(fn):
        def _w(*a, **k):
            rez = fn(*a, **k)
            regjistri["args"] = (a, {kk: vv for kk, vv in k.items() if kk != "gjurma"})
            regjistri["kthimi"] = rez
            return rez
        return _w

    ns_p["simulim_monte_carlo_v2"] = _mbeshtjell(sim_p)

    def forma_e_rastit(rng):
        return {
            "win_rate": round(rng.uniform(0.1, 0.8), 3), "k_wins_rresht": rng.randint(0, 7),
            "lodhja_factor": round(rng.uniform(0.9, 1.0), 3),
            "avg_gola_shenuar": round(rng.uniform(0.5, 2.6), 3), "avg_gola_prane": round(rng.uniform(0.4, 2.2), 3),
            "avg_shenuar_home": round(rng.uniform(0.5, 2.8), 3), "avg_prane_home": round(rng.uniform(0.4, 2.0), 3),
            "avg_shenuar_away": round(rng.uniform(0.4, 2.4), 3), "avg_prane_away": round(rng.uniform(0.5, 2.4), 3),
            "piket_forma": float(rng.randint(0, 15)), "ndeshje_14d": rng.randint(1, 6),
            "volatility": round(rng.uniform(0.8, 2.0), 3), "xg_shenuar": round(rng.uniform(0.6, 2.2), 3),
            "xg_prane": round(rng.uniform(0.6, 2.0), 3), "total_ndeshje": 8, "h_ndeshje": 4, "a_ndeshje": 4,
            "data_fundit": "2026-09-2%dT18:00:00+00:00" % rng.randint(0, 8),
        }

    LIGAT = ["Premier League", "Serie A", "Championship", "UEFA Europa League", "Superliga",
             "World Cup - Qualification Europe", "Eredivisie", "La Liga"]

    def rast(i, rng, detyro=None):
        detyro = detyro or {}
        fav = rng.choice(["1", "2", "X"])
        if fav == "1":
            k1, kx, k2 = rng.uniform(1.2, 2.0), rng.uniform(3.2, 6.5), rng.uniform(3.5, 12.0)
        elif fav == "2":
            k1, kx, k2 = rng.uniform(3.5, 11.0), rng.uniform(3.2, 6.0), rng.uniform(1.25, 2.1)
        else:
            k1, kx, k2 = rng.uniform(2.3, 3.2), rng.uniform(2.9, 3.6), rng.uniform(2.3, 3.4)
        odds = {}
        if not detyro.get("pa_ou") and rng.random() < 0.85:
            p_ov = rng.uniform(0.30, 0.72)
            m = rng.uniform(1.04, 1.08)
            odds["Over 2.5"] = "%.2f" % (1.0 / (p_ov * m))
            odds["Under 2.5"] = "%.2f" % (1.0 / ((1 - p_ov) * m))
        if rng.random() < 0.5:
            odds["AH"] = {"-0.5": {"home": "%.2f" % rng.uniform(1.7, 2.2), "away": "%.2f" % rng.uniform(1.7, 2.2)}}
        dna1 = dna2 = None
        if detyro.get("derbi") or rng.random() < 0.6:
            hp = rng.uniform(600, 900)
            dna1 = {"historical_power": hp, "clutch_factor": rng.uniform(0.95, 1.05),
                    "volatility_index": rng.uniform(10, 25), "draw_affinity": rng.uniform(25, 40)}
            dna2 = {"historical_power": hp + (rng.uniform(-20, 20) if detyro.get("derbi") else rng.uniform(-250, 250)),
                    "clutch_factor": rng.uniform(0.95, 1.05),
                    "volatility_index": rng.uniform(10, 25), "draw_affinity": rng.uniform(25, 40)}
        f1, f2 = forma_e_rastit(rng), forma_e_rastit(rng)
        if detyro.get("boost"):
            f1["piket_forma"], f2["piket_forma"] = 4.0, 12.0
        return {
            "id": 1_400_000 + i, "e1": f"Vendas {i}", "e2": f"Mysafir {i}", "id1": 10_000 + 2 * i, "id2": 10_001 + 2 * i,
            "k": ("%.2f" % k1, "%.2f" % kx, "%.2f" % k2), "liga": rng.choice(LIGAT), "odds": odds,
            "dna1": dna1, "dna2": dna2, "forma": {10_000 + 2 * i: f1, 10_001 + 2 * i: f2},
            "lend": {10_000 + 2 * i: rng.randint(0, 3), 10_001 + 2 * i: rng.randint(0, 2)},
            "hyb": (rng.uniform(0.92, 1.08), rng.uniform(0.92, 1.08),
                    None if rng.random() < 0.3 else rng.uniform(0.38, 0.48),
                    None if rng.random() < 0.3 else rng.uniform(0.38, 0.48)),
            "data": "2026-10-0%dT19:00:00+00:00" % rng.randint(3, 9),
        }

    def ekzekuto(ns, r, konf):
        KONF.clear(); KONF.update(konf)
        ns["merr_formen_reale"] = lambda tid, liga=None, *a, **k: copy.deepcopy(r["forma"][tid])
        ns["_merr_lendimet"] = lambda fid: dict(r["lend"])
        h1, h2, fr1, fr2 = r["hyb"]
        ns["llogarit_xg_hybrid"] = (lambda f1, f2, p1, p2, k1, kx, k2, liga, x1, x2, **kw:
                                    (x1 * h1, x2 * h2, "hybrid" if fr1 else "math", fr1, fr2))
        random.seed(42); np.random.seed(42)
        return ns["analizo_ndeshjen_premium_master"](
            r["id"], r["e1"], r["e2"], r["id1"], r["id2"], r["k"][0], r["k"][1], r["k"][2],
            r["liga"], [], dna_1=copy.deepcopy(r["dna1"]), dna_2=copy.deepcopy(r["dna2"]),
            odds_full=copy.deepcopy(r["odds"]), data_ndeshjes=r["data"])

    rng = random.Random(20261003)
    rastet = []
    for i in range(160):
        rastet.append((rast(i, rng), dict(KONF_LIVE), "live"))
    for i in range(160, 200):
        rastet.append((rast(i, rng), {}, "kodi"))
    for i in range(200, 215):
        rastet.append((rast(i, rng, {"pa_ou": True}), dict(KONF_LIVE), "pa_O/U"))
    for i in range(215, 230):
        rastet.append((rast(i, rng, {"boost": True}), {**KONF_LIVE, "BOOST_MYSAFIR": 0.30}, "boost"))
    for i in range(230, 260):
        rastet.append((rast(i, rng), {**KONF_LIVE, "FALLBACK_HAPUR": 1.6}, "fallback"))
    for i in range(260, 280):
        rastet.append((rast(i, rng), {**KONF_LIVE, "WINNER_BURIMI": 0}, "burimi_MC"))
    for i in range(280, 290):
        rastet.append((rast(i, rng, {"derbi": True}), dict(KONF_LIVE), "derbi"))

    TD_CELESAT = None
    numer = {"ok": 0, "fb": 0, "lean": 0, "plus1": 0, "boost": 0, "pa_treg": 0, "mbrojtja": 0, "derbi": 0,
             "replay_dist": 0, "replay_rez": 0, "replay_top5": 0}

    def sim_top5(_rp, rr_td, _seed):
        g = {}
        sim_p(rr_td["lam_1"], rr_td["lam_2"], rr_td["kaos_liges"], rr_td["is_derbi"], iteracione=50_000,
              seed=_seed, aff=rr_td["aff"], mkt_1x2=(rr_td["p_market_1"], rr_td["p_market_x"], rr_td["p_market_2"]),
              gjurma=g)
        return g["top5"]
    max_dev_rindertim = 0.0
    shembull_gj = None
    for r, konf, etiketa in rastet:
        try:
            out_o = ekzekuto(ns_o, r, konf)
        except Exception as e:
            kontrollo(False, f"T2 origjinali deshtoi ne rastin {r['id']} ({etiketa}): {type(e).__name__}: {e}")
            continue
        regjistri.clear()
        try:
            out_p = ekzekuto(ns_p, r, konf)
        except Exception as e:
            kontrollo(False, f"T2 PATCH-i deshtoi ne rastin {r['id']} ({etiketa}): {type(e).__name__}: {e}")
            continue
        anal_o, bes_o, rez_o, koef_o, ex_o = out_o
        anal_p, bes_p, rez_p, koef_p, ex_p = out_p
        ex_p = dict(ex_p)
        gj = ex_p.pop("gjurma_db", None)
        # `build` ndryshon ME QELLIM (vula e deploy-it); verifikohet vec, pastaj normalizohet
        kontrollo(ex_o["training_data"]["build"] == ns_o["BUILD"] and ex_p["training_data"]["build"] == ns_p["BUILD"],
                  "T2 build")
        ex_o = dict(ex_o); ex_o["training_data"] = {**ex_o["training_data"], "build": "<BUILD>"}
        ex_p["training_data"] = {**ex_p["training_data"], "build": "<BUILD>"}
        kontrollo(gj is not None, "T2 gjurma_db mungon")
        kontrollo("gjurma_db" not in ex_o, "T2 origjinali s'duhet ta kete gjurma_db")
        identik = (anal_o == anal_p and bes_o == bes_p and rez_o == rez_p and koef_o == koef_p
                   and ex_o == ex_p and js(out_o[:4]) == js(out_p[:4]) and js(ex_o) == js(ex_p))
        kontrollo(identik, f"T2 OUTPUT I NDRYSHEM ne rastin {r['id']} ({etiketa})")
        if not identik or gj is None:
            continue
        numer["ok"] += 1
        td = ex_p["training_data"]
        if TD_CELESAT is None:
            TD_CELESAT = list(td.keys())
        kontrollo(not (set(gj) & set(td)), f"T2 perplasje celesash: {set(gj) & set(td)}")
        kontrollo(not lloj_i_paster(gj), f"T2 tipa: {lloj_i_paster(gj)[:3]}")
        try:
            json.dumps({**gj, **td}, allow_nan=False)
        except Exception as e:
            kontrollo(False, f"T2 json i training_data te bashkuar: {e}")
        (a_sim, k_sim) = regjistri["args"]
        kontrollo(type(gj["lam_1"]) is float and gj["lam_1"] == float(a_sim[0]) and gj["lam_2"] == float(a_sim[1]),
                  "T2 lam_1/lam_2 != λ qe iu dha simulimit (saktesisht)")
        # RE-SIMULIMI NDESHJE PER NDESHJE nga rreshti i ruajtur (pas round-trip JSON, si nga DB)
        rr_td = json.loads(json.dumps({**gj, **td}, allow_nan=False))
        _seed = int(hashlib.sha256(str(r["id"]).encode()).hexdigest()[:8], 16)
        rp = sim_o(rr_td["lam_1"], rr_td["lam_2"], rr_td["kaos_liges"], rr_td["is_derbi"],
                   iteracione=50_000, seed=_seed, aff=rr_td["aff"],
                   mkt_1x2=(rr_td["p_market_1"], rr_td["p_market_x"], rr_td["p_market_2"]))
        numer["replay_dist"] += int(rp[2] == regjistri["kthimi"][2])
        numer["replay_rez"] += int(rp[0] == regjistri["kthimi"][0])
        numer["replay_top5"] += int(sim_top5(rp, rr_td, _seed) == rr_td["zgjedhja"]["top5"])
        kontrollo(gj["aff"] == round(float(k_sim["aff"]), 4), "T2 aff")
        z = gj["zgjedhja"]
        kontrollo(z["rez"] == rez_p, "T2 zgjedhja.rez != skori i publikuar")
        kontrollo(z["rez_sim"] == regjistri["kthimi"][0], "T2 rez_sim != kthimi i simulimit")
        kontrollo(z["fb"] == (rez_p != regjistri["kthimi"][0]), "T2 fb")
        kontrollo(abs(min(40.0, 0.85 / z["prob"]) - float(koef_p)) < 0.011 if z["prob"] else True, "T2 prob/koef")
        # dist_shenja: nen-dict i SAKTE i dist_gola qe ky gjenerim publikon (int, po ato vlera),
        # me te gjitha qelizat e top5 + skorin e publikuar; jo bosh.
        sh = z.get("dist_shenja")
        dg = ex_p["dist_gola"]
        kontrollo(isinstance(sh, dict) and sh, "T2 dist_shenja mungon/bosh")
        kontrollo(all(type(v) is int and dg.get(k) == v for k, v in sh.items()),
                  "T2 dist_shenja s'eshte nen-dict i dist_gola")
        kontrollo(set(sh) == ({x[0] for x in z["top5"]} | {rez_p}) & set(dg),
                  f"T2 qelizat e dist_shenja {sorted(sh)}")
        kontrollo(rez_p in sh, "T2 skori i publikuar s'eshte ne dist_shenja")
        # P ne top5 ruhet me 5 shifra -> gabim <= 0.25 numra
        kontrollo(all(abs(sh[x[0]] - x[1] * 50_000) <= 0.2501 + 0.5 for x in z["top5"] if x[0] in sh),
                  "T2 dist_shenja != P_top5 * 50000")
        numer["shenja_ok"] = numer.get("shenja_ok", 0) + 1
        # xg_1/xg_2 te training_data: te paprekura dhe PARA normalizimit
        kontrollo(td["xg_1"] == ex_o["training_data"]["xg_1"], "T2 xg_1 ndryshoi")
        # rindertimi i zinxhirit nga celesat e ruajtur
        xn = gj["xg_norm"]
        fl = ns_p["XG_FLOOR"]
        n1 = min(max(xn["a_1"] + xn["b_1"] * td["xg_1"], fl), 5.0)
        n2 = min(max(xn["a_2"] + xn["b_2"] * td["xg_2"], fl), 5.0)
        kontrollo(abs(n1 - gj["lam_n_1"]) < 2e-3 and abs(n2 - gj["lam_n_2"]) < 2e-3, "T2 lam_n nga xg+A/B")
        if gj["shk_treg"] is not None:
            n1 = min(max(gj["lam_n_1"] * gj["shk_treg"], fl), 5.0)
            n2 = min(max(gj["lam_n_2"] * gj["shk_treg"], fl), 5.0)
        else:
            n1, n2 = gj["lam_n_1"], gj["lam_n_2"]
            numer["pa_treg"] += 1
        if gj["boost"]:
            numer["boost"] += 1
            n2 = min(max(n2 + gj["boost"] / 2, fl), 5.0); n1 = min(max(n1 - gj["boost"] / 2, fl), 5.0)
        dev = max(abs(n1 - gj["lam_1"]), abs(n2 - gj["lam_2"]))
        max_dev_rindertim = max(max_dev_rindertim, dev)
        kontrollo(dev < 1e-3, f"T2 zinxhiri s'rindertohet ({dev})")
        numer["fb"] += int(z["fb"]); numer["lean"] += int(z["lean"]); numer["plus1"] += int(z["lean_plus1"])
        numer["mbrojtja"] += int(z["mbrojtja"]); numer["derbi"] += int(bool(td.get("is_derbi")))
        if shembull_gj is None and gj["shk_treg"] is not None:
            shembull_gj = (td["xg_1"], td["xg_2"], gj)
    print(f"  raste: {len(rastet)}, identike + gjurme e rregullt: {numer['ok']}")
    print("  mbulimi:", numer)
    print(f"  devijimi max i rindertimit lam nga xg_1(3 shifra)+A/B+shk_treg: {max_dev_rindertim:.6f}")
    if shembull_gj:
        print(f"  shembull: xg_1/xg_2 = {shembull_gj[0]}/{shembull_gj[1]}  ->  gjurma_db =")
        print("   ", json.dumps(shembull_gj[2], ensure_ascii=False))
        print(f"  madhesia e gjurmes ne JSON: ~{len(json.dumps(shembull_gj[2], ensure_ascii=False))} bajte")

    # Rasti i komentit: xg 1.30/1.30, P(O2.5)=0.45, A/B live -> λ e simuluar
    lnp = ns_p["_lambda_nga_p_over"]
    n1 = -0.1438 + 1.1505 * 1.30; n2 = 0.2989 + 0.8666 * 1.30
    T = n1 + n2; Tm = lnp(0.45); f = min(max((0.5 * T + 0.5 * Tm) / T, 0.5), 2.0)
    print(f"  shembulli i komentit: xg 1.30/1.30, P(O2.5)=0.45 -> λ {n1 * f:.3f}/{n2 * f:.3f} (lam_treg={Tm})")
    kontrollo(abs(n1 * f - 1.279) < 1.5e-3 and abs(n2 * f - 1.348) < 1.5e-3, "shembulli i komentit")

    # ── T3: task_ruaj_skedinen_ne_db ──────────────────────────────────────
    print("=" * 78)
    print("T3  task_ruaj_skedinen_ne_db: payload-i i DB-se dhe cache-i")
    postimet = []

    class _Pergj:
        def __init__(self, kodi, trupi=None):
            self.status_code = kodi; self._t = trupi if trupi is not None else []; self.text = ""

        def json(self):
            return self._t

    def ndez_requests(ns, ekzistuese):
        def _get(url, **k):
            return _Pergj(200, ekzistuese)

        def _post(url, headers=None, json=None, timeout=None):
            json_str = __import__("json").dumps(json, allow_nan=False)  # si requests
            postimet.append((url, json, json_str))
            return _Pergj(201)
        ns["requests"] = types.SimpleNamespace(get=_get, post=_post, patch=_post)
        ns["SUPABASE_URL_PREDS"] = "https://x.supabase.co/rest/v1/predictions"
        ns["SUPABASE_SERVICE_HEADERS"] = {"apikey": "x"}

    r, konf, _ = rastet[0]
    _, _, rez0, koef0, ex0 = ekzekuto(ns_p, r, konf)
    td0 = ex0["training_data"]
    nd = {"id": r["id"], "ndeshja": "A vs B", "data": "2026-10-04", "rezultati_sakt": rez0,
          "koef_rez_sakt": koef0, "tregjet": ex0["tregjet"], "dist_gola": ex0["dist_gola"],
          "training_data": td0, "is_motd": False, "liga_emri": "X", "statusi": "NS"}
    kopja_td = copy.deepcopy(td0)
    id_td = id(nd["training_data"])
    for ekzistuese, emri in (([], "rresht i ri"),
                             ([{"id": r["id"], "rezultati_sakt": "1-0", "dist_gola": {"1-0": 1},
                                "koef_rez_sakt": "6.00", "parashikimi_origjinal_ai": "1-0"}], "rresht i ngrire")):
        postimet.clear()
        ndez_requests(ns_o, ekzistuese); ns_o["task_ruaj_skedinen_ne_db"]([copy.deepcopy(nd)])
        ndez_requests(ns_p, ekzistuese); ns_p["task_ruaj_skedinen_ne_db"]([copy.deepcopy(nd)])
        ns_p["task_ruaj_skedinen_ne_db"]([nd], gjurmet={str(r["id"]): ex0["gjurma_db"]})
        p_o, p_p0, p_p1 = postimet[0][1], postimet[1][1], postimet[2][1]
        kontrollo(postimet[0][2] == postimet[1][2], f"T3 {emri}: patch pa gjurmet != origjinali")
        pa_td = lambda p: {k: v for k, v in p.items() if k != "training_data"}
        kontrollo(js(pa_td(p_o)) == js(pa_td(p_p1)), f"T3 {emri}: kolonat e tjera ndryshuan")
        tdp = p_p1["training_data"]
        kontrollo(all(tdp[k] == v for k, v in kopja_td.items()), f"T3 {emri}: celesat ekzistues ndryshuan")
        kontrollo(set(tdp) - set(kopja_td) == set(ex0["gjurma_db"]), f"T3 {emri}: celesat e shtuar")
        kontrollo(id(nd["training_data"]) == id_td and nd["training_data"] == kopja_td
                  and set(nd["training_data"]) == set(kopja_td), f"T3 {emri}: cache-i u prek")
        kontrollo(("rezultati_sakt" in p_o) == ("rezultati_sakt" in p_p1), f"T3 {emri}: ngrirja")
        print(f"  {emri}: payload identik pervec training_data (+{len(set(tdp) - set(kopja_td))} celesa); "
              f"rezultati_sakt ne payload: {'rezultati_sakt' in p_p1}; cache i paprekur: PO")
    # mbrojtja e perparesise: nje celes i perbashket s'mund ta mbishkruaje xg_1
    postimet.clear()
    ndez_requests(ns_p, [])
    ns_p["task_ruaj_skedinen_ne_db"]([copy.deepcopy(nd)], gjurmet={str(r["id"]): {"xg_1": -999.0, "lam_1": 1.0}})
    kontrollo(postimet[0][1]["training_data"]["xg_1"] == td0["xg_1"], "T3 xg_1 u mbishkrua nga gjurma")
    print("  perparesia: nje gjurme me 'xg_1' s'e mbishkruan xg_1 e training_data: PO")

    # ── T4: riprodhimi me λ te rrumbullakuar (informative) ────────────────
    print("=" * 78)
    print("T4  re-simulim me lam_1/lam_2 te ruajtura (4 shifra) kundrejt λ te plote")
    rr = random.Random(5)
    njejte_rez = njejte_dist = 0; N = 300; max_d = 0
    for _ in range(N):
        l1, l2 = rr.uniform(0.3, 3.0), rr.uniform(0.3, 2.6)
        seed = rr.randrange(2 ** 32)
        mkt = (0.45, 0.28, 0.27)
        a = sim_o(l1, l2, 1.10, False, iteracione=50_000, seed=seed, aff=0.15, mkt_1x2=mkt)
        b = sim_o(round(l1, 4), round(l2, 4), 1.10, False, iteracione=50_000, seed=seed, aff=0.15, mkt_1x2=mkt)
        njejte_rez += int(a[0] == b[0]); njejte_dist += int(a[2] == b[2])
        max_d = max(max_d, max(abs(a[2].get(k, 0) - b[2].get(k, 0)) for k in set(a[2]) | set(b[2])))
    print(f"  λ e rrumbullakuar 4 shifra: skori i njejte {njejte_rez}/{N}; dist_gola identike {njejte_dist}/{N}; "
          f"diferenca max ne nje qelize: {max_d} nga 50000")
    print("  (prandaj lam_1/lam_2 ruhen te plota; riprodhimi i sakte matet te T2: replay_dist/replay_rez)")

    # ── T5: dy gjenerime -> a e dallon shenja gjurmen e skorit te publikuar? ──
    t5_rreshta = t5_prejardhja(ns_o, ns_p, rast, ekzekuto)

    # fixture per PostgreSQL (kontrolli_lambda.sql + sql/filtri/2,3): rreshtat e T5 + te vjeter
    shkruaj_fixture(t5_rreshta, ns_o, rast, ekzekuto, ns_p["BUILD"])

    # ── T6: gjurma s'mund ta humbe rreshtin (AFF NaN nga model_config, gjurme e prishur) ──
    print("=" * 78)
    print("T6  AFF NaN (model_config) + gjurme jo-json: rreshti ruhet gjithmone")
    konf_nan = {**KONF_LIVE, "AFF_FIKS": 0.0, "AFF_LOW": float("nan"), "AFF_HIGH": float("nan")}
    rng6 = random.Random(606)
    db6 = _DbRreme()
    ns_p["requests"] = types.SimpleNamespace(get=db6.get, post=db6.post, patch=db6.post)
    n_ok = n_null = 0
    for i in range(25):
        r = rast(8000 + i, rng6)
        o = ekzekuto(ns_o, r, konf_nan)
        p = ekzekuto(ns_p, r, konf_nan)
        ex_o = dict(o[4]); ex_p = dict(p[4]); gj = ex_p.pop("gjurma_db")
        ex_o["training_data"] = {**ex_o["training_data"], "build": "<B>"}
        ex_p["training_data"] = {**ex_p["training_data"], "build": "<B>"}
        kontrollo(js(o[:4]) == js(p[:4]) and js(ex_o) == js(ex_p), f"T6 output i ndryshem me AFF NaN ({r['id']})")
        try:
            json.dumps(gj, allow_nan=False); n_ok += 1
        except Exception as e:
            kontrollo(False, f"T6 gjurma jo-json me AFF NaN: {e}")
        n_null += int(gj["aff"] is None and all(x[2] is None for x in gj["zgjedhja"]["top5"]))
        nd = {"id": r["id"], "rezultati_sakt": p[2], "koef_rez_sakt": p[3], "dist_gola": p[4]["dist_gola"],
              "training_data": p[4]["training_data"], "statusi": "NS"}
        ns_p["task_ruaj_skedinen_ne_db"]([nd], gjurmet={str(r["id"]): gj})
        rr = db6.rreshta.get(str(r["id"]))
        kontrollo(rr is not None and "lam_1" in rr["training_data"], f"T6 rreshti/gjurma s'u ruajt ({r['id']})")
    print(f"  25 ndeshje me AFF NaN: output identik me origjinalin; gjurme json e paster {n_ok}/25; "
          f"piket AFF -> null {n_null}/25; rreshta te ruajtur {len(db6.rreshta)}/25")
    # gjurme e prishur qellimisht (NaN, tip numpy): payload-i = ai i origjinalit, rreshti ruhet
    postimet6 = []

    def _post6(url, headers=None, json=None, timeout=None):
        import json as _j
        postimet6.append(_j.dumps(json, allow_nan=False))       # si requests: hedh perjashtim per NaN
        return _Pergjigje(201)
    for ns in (ns_o, ns_p):
        ns["requests"] = types.SimpleNamespace(get=lambda *a, **k: _Pergjigje(200, []), post=_post6, patch=_post6)
    r = rast(8100, rng6)
    _, _, rez, koef, ex = ekzekuto(ns_p, r, dict(KONF_LIVE))
    nd = {"id": r["id"], "rezultati_sakt": rez, "koef_rez_sakt": koef, "dist_gola": ex["dist_gola"],
          "training_data": ex["training_data"], "statusi": "NS"}
    for emri, gj_keq in (("NaN", {**ex["gjurma_db"], "lam_1": float("nan")}),
                         ("numpy", {**ex["gjurma_db"], "lam_2": np.float32(1.2)})):
        postimet6.clear()
        ns_o["task_ruaj_skedinen_ne_db"]([copy.deepcopy(nd)])
        ns_p["task_ruaj_skedinen_ne_db"]([copy.deepcopy(nd)], gjurmet={str(r["id"]): gj_keq})
        kontrollo(len(postimet6) == 2 and postimet6[0] == postimet6[1],
                  f"T6 gjurme {emri}: rreshti s'u ruajt ose payload-i ndryshon nga origjinali")
        print(f"  gjurme e prishur ({emri}): rreshti ruhet, payload identik me origjinalin: "
              f"{'PO' if len(postimet6) == 2 and postimet6[0] == postimet6[1] else 'JO'}")

    print("=" * 78)
    if DESHTIME:
        print(f"REZULTATI: {len(DESHTIME)} DESHTIME")
        sys.exit(1)
    print("REZULTATI: TE GJITHA KONTROLLET KALUAN")


if __name__ == "__main__":
    main()
