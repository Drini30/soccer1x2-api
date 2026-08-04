# ==========================================================
# HAPI 4a — EKSPERIMENT MATJEJE (nuk prek prodhimin)
# ==========================================================
# Nuk ruan asnjë model. Vetëm mat nëse veçoritë e reja ndihmojnë.
#
# METODA — holdout kohor me origjinë rrotulluese:
# ══════════════════════════════════════════════════════════════════════════
# REZULTATI I EKZEKUTIMIT — gusht 2026, 55,835 rreshta CSV, 3 prerje
# ══════════════════════════════════════════════════════════════════════════
#   variant            ΔNLL kundrejt bazës      verdikti
#   B (+8 goditje)     +0.0003 ± 0.0009         pa efekt
#   C (+4 h2h)         +0.0005 ± 0.0010         pa efekt
#   D (+1 tier)        +0.0012 ± 0.0010         pa efekt
#
# Të tria POZITIVE (më keq) dhe brenda 1 SE nga zeroja. SE-ja 0.001 do të thotë
# se prova ka fuqi: edhe kufiri i sipërm i besueshëm për goditjet është -0.0015
# NLL mbi bazë 1.72, pra 0.09%. Ky është rezultat negativ i fuqishëm, jo
# "s'u provua dot".
#
# PSE: kuotat i përmbajnë tashmë. Tregu i çmon goditjet dhe formën; një mesatare
# 6-ndeshjesh e zhurmshme s'shton informacion mbi një linjë që mban 73% të gain-it.
#
# PASOJA: hapi 4b (cache i /fixtures/statistics, ~12 thirrje API për ndeshje,
# ruajtje e qëndrueshme) U ANULUA. Mos e ri-provo pa një arsye të re.
#
# KATEGORIA E DYTË: heqja e tyre kurrë s'ndihmoi, dhe në prerjen 2 dëmtoi
# ndjeshëm (+0.0059 ± 0.0027, mbi 2×SE). Mbaji të 16 ligat.
#
# MBULIMI: të 11,734 rreshtat `api` dolën me 0.0% mbulim edhe të veçorive bazë.
# Pra modelet në prodhim janë trajnuar VETËM mbi CSV — rreshtat `api` binin te
# dropna në heshtje. Shpjegon edhe pse tipi_ndeshjes kishte 0 ndarje: kupat dhe
# kombëtaret vijnë vetëm prej andej, ndaj s'hynë kurrë në trajnim.
# ══════════════════════════════════════════════════════════════════════════
#
#   • Prerja bëhet me DATË (jo me përqindje rreshtash).
#   • Modeli trajnohet vetëm mbi ndeshjet PARA prerjes, matet mbi ato PAS saj.
#   • Përsëritet me disa prerje të njëpasnjëshme, sepse një dritare 6-mujore ka
#     ~2-3 mijë ndeshje dhe gabimi standard i MAE-së aty është ~0.02 — pra një
#     prerje e vetme s'i dallon dot ndryshimet e vogla nga rastësia.
#   • Krahasimi është i ÇIFTUAR: të gjitha variantet mbi saktësisht të njëjtat
#     rreshta, dhe diferenca llogaritet për-ndeshje.
#
# PSE ËSHTË I VLEFSHËM: tiparet u llogaritën te importuesi vetëm nga ndeshjet
# PARA secilës (df.iloc[:idx]). Pa këtë, modeli do të kishte parë të ardhmen
# nëpër tiparet dhe holdout-i do të ishte teatër.
#
# ⚠️ dropna VETËM mbi targetin — jo mbi veçoritë. XGBoost i trajton NaN-et
#    vendas (mëson degën e munguar). Po të hiqeshin rreshtat me veçori NULL,
#    do të humbeshin ~9.5 mijë pa SOT, ~8.2 mijë pa h2h dhe të 11.7 mijë `api`.
#
# Ekzekuto te Google Colab:
#   !pip install xgboost pandas requests scikit-learn scipy numpy -q
#   import os; os.environ["SUPABASE_SERVICE_KEY"] = "..."
# ==========================================================

import os
import sys

import numpy as np
import pandas as pd
import requests
import xgboost as xgb
from scipy.stats import poisson

SUPABASE_URL = os.environ.get(
    "SUPABASE_HISTORIK_URL",
    "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/historik_trajnimi",
)
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
if not SUPABASE_KEY:
    sys.exit("❌ Vendos SUPABASE_SERVICE_KEY te environment-i.")
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

# ── KONFIGURIMI I EKSPERIMENTIT ──
MUAJ_HOLDOUT = 6     # gjerësia e dritares së matjes
N_PRERJE     = 3     # sa prerje të njëpasnjëshme (origjinë rrotulluese)

# Vetëm rreshtat e importuesit tonë. `api` shkohen nga backend-i live, me
# përkufizime tiparesh të paverifikuara (p.sh. forma mbi 8 ndeshje, jo 6) dhe
# mbulim kohor 21 muaj më të gjatë. Për një MATJE, pastërtia e provenancës vlen
# më shumë se vëllimi — 55 mijë rreshta janë të bollshëm. Vendose False për t'i
# përfshirë (dhe shiko më parë tabelën e mbulimit që printohet më poshtë).
VETEM_CSV = True

# ── VEÇORITË ──
BAZE_31 = [
    "home_forma_pts", "away_forma_pts",
    "home_avg_scored", "away_avg_scored",
    "home_avg_conceded", "away_avg_conceded",
    "home_avg_scored_home", "home_avg_conceded_home",
    "away_avg_scored_away", "away_avg_conceded_away",
    "home_avg_yellow", "away_avg_yellow",
    "home_avg_red", "away_avg_red",
    "home_attack_strength", "away_attack_strength",
    "home_defense_strength", "away_defense_strength",
    "home_volatility", "away_volatility",
    "home_rest_days", "away_rest_days",
    "odd_home", "odd_draw", "odd_away",
    "tipi_ndeshjes",
    "ah_line", "ah_home_odd", "ah_away_odd",
    "ou25_over", "ou25_under",
]
GODITJE_8 = [
    "home_avg_shots", "away_avg_shots",
    "home_avg_sot", "away_avg_sot",
    "home_avg_sot_against", "away_avg_sot_against",
    "home_avg_corners", "away_avg_corners",
]
H2H_4 = ["h2h_avg_gola", "h2h_home_wins", "h2h_draws", "h2h_away_wins"]
TIER_1 = ["tier"]

VARIANTET = {
    "A_baze_31":     BAZE_31,
    "B_goditje_39":  BAZE_31 + GODITJE_8,
    "C_h2h_43":      BAZE_31 + GODITJE_8 + H2H_4,
    "D_tier_44":     BAZE_31 + GODITJE_8 + H2H_4 + TIER_1,
}

# Kategoria e dytë — për provën "a shtojnë zhurmë ligat e dyta?"
KAT2 = {
    "England - Championship", "Spain - Segunda Division",
    "Italy - Serie B", "Germany - 2. Bundesliga", "France - Ligue 2",
}

PARAMS = dict(
    objective="count:poisson",
    max_depth=5, learning_rate=0.05, n_estimators=400,
    subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
    n_jobs=-1, random_state=42,
)


def merr_te_gjitha():
    rresht, offset, lim = [], 0, 1000
    while True:
        r = requests.get(SUPABASE_URL, headers=HEADERS, params={
            "select": "*", "order": "data_ndeshjes.asc", "limit": lim, "offset": offset
        }, timeout=120)
        d = r.json()
        if not isinstance(d, list) or not d:
            break
        rresht += d
        if len(d) < lim:
            break
        offset += lim
        if offset % 10000 == 0:
            print(f"  ...{len(rresht)} rreshta")
    return pd.DataFrame(rresht)


def nll_poisson(pred, y):
    """Negative log-likelihood e Poisson-it, për-ndeshje (pa konstanten log y!).
    Metrika kryesore: përputhet me objektivin count:poisson."""
    pred = np.clip(pred, 1e-6, None)
    return pred - y * np.log(pred)


def metrikat(ph, pa, yh, ya):
    """Kthen metrikat e nivelit të produktit + NLL-në për-ndeshje."""
    nll = nll_poisson(ph, yh) + nll_poisson(pa, ya)
    mae = (np.abs(ph - yh) + np.abs(pa - ya)) / 2.0

    # 1X2 nga rrjeta e Poisson-it (i pavarur, si te backend-i)
    ks = np.arange(11)
    hp = poisson.pmf(ks[None, :], ph[:, None])
    ap = poisson.pmf(ks[None, :], pa[:, None])
    joint = hp[:, :, None] * ap[:, None, :]                # (n, 11, 11)
    iu = np.triu_indices(11, k=1)
    p_away = joint[:, iu[0], iu[1]].sum(axis=1)            # home < away
    p_home = joint[:, iu[1], iu[0]].sum(axis=1)
    p_draw = joint[:, ks, ks].sum(axis=1)
    pred_1x2 = np.argmax(np.vstack([p_home, p_draw, p_away]).T, axis=1)
    real_1x2 = np.where(yh > ya, 0, np.where(yh == ya, 1, 2))

    tot = ph + pa
    pred_ov = (1 - poisson.cdf(2, tot)) > 0.5
    real_ov = (yh + ya) > 2.5

    flat = joint.reshape(len(ph), -1)
    top1 = flat.argmax(axis=1)
    cs_hit = (top1 // 11 == np.clip(yh, 0, 10)) & (top1 % 11 == np.clip(ya, 0, 10))

    return {
        "nll_per_ndeshje": nll,
        "NLL": nll.mean(),
        "MAE": mae.mean(),
        "1X2": (pred_1x2 == real_1x2).mean() * 100,
        "O/U": (pred_ov == real_ov).mean() * 100,
        "CS":  cs_hit.mean() * 100,
    }


def trajno_dhe_mat(tr, te, vecorite):
    out = {}
    for ana, target in [("h", "gola_home"), ("a", "gola_away")]:
        m = xgb.XGBRegressor(**PARAMS)
        m.fit(tr[vecorite], tr[target])
        out[ana] = np.clip(m.predict(te[vecorite]), 1e-6, None)
    return metrikat(out["h"], out["a"],
                    te["gola_home"].values, te["gola_away"].values)


def main():
    print("Duke shkarkuar historik_trajnimi...")
    df = merr_te_gjitha()
    print(f"Total: {len(df)} rreshta\n")

    df["data_ndeshjes"] = pd.to_datetime(df["data_ndeshjes"], errors="coerce")

    # ── DIAGNOSTIKË: mbulimi kohor për burim ──
    print("═" * 66)
    print("MBULIMI KOHOR")
    print("═" * 66)
    def _mbulim(g, kolonat):
        ekz = [c for c in kolonat if c in g.columns]
        if not ekz:
            return 0.0
        return 100.0 * g[ekz].notna().all(axis=1).mean()

    print(f"  {'burimi':6s} {'rreshta':>8s}  {'nga':10s} {'deri':10s} "
          f"{'baze31':>7s} {'goditje':>8s} {'h2h':>6s}")
    for burimi, g in df.groupby("burimi", dropna=False):
        print(f"  {str(burimi):6s} {len(g):8d}  "
              f"{str(g['data_ndeshjes'].min().date()):10s} {str(g['data_ndeshjes'].max().date()):10s} "
              f"{_mbulim(g, BAZE_31):6.1f}% {_mbulim(g, GODITJE_8):7.1f}% {_mbulim(g, H2H_4):5.1f}%")
    print("  (përqindjet = rreshta me TË GJITHA kolonat e atij grupi jo-NULL)")

    # dropna VETËM mbi targetin dhe datën
    targets = ["gola_home", "gola_away"]
    for c in set(BAZE_31 + GODITJE_8 + H2H_4 + targets):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = np.nan
            print(f"  ⚠️ kolona mungon te tabela, u mbush me NaN: {c}")

    df["tier"] = df["liga"].isin(KAT2).astype(int) if "liga" in df.columns else 0

    if VETEM_CSV:
        para = len(df)
        df = df[df["burimi"] == "csv"]
        print(f"\nVETEM_CSV=True → {para} - {para - len(df)} = {len(df)} rreshta")

    df = df.dropna(subset=targets + ["data_ndeshjes"]).sort_values("data_ndeshjes").reset_index(drop=True)
    print(f"\nPas dropna (vetëm target+datë): {len(df)} rreshta")
    print(f"Periudha: {df['data_ndeshjes'].min().date()} → {df['data_ndeshjes'].max().date()}")

    # ── PRERJET (origjinë rrotulluese) ──
    # ANKORIMI: dritaret e matjes duhet të bien aty ku goditjet EKZISTOJNË.
    # Rreshtat `api` mbarojnë 21 muaj më vonë se `csv` dhe s'kanë asnjë goditje;
    # po të ankoroheshim te data maksimale globale, të tria prerjet do të binin
    # brenda tyre dhe do të matnim efektin e goditjeve mbi rreshta pa goditje.
    me_sot = df.loc[df["home_avg_sot"].notna(), "data_ndeshjes"]
    if len(me_sot) == 0:
        sys.exit("❌ Asnjë rresht me goditje — s'ka çfarë të matet.")
    dmax = me_sot.max()
    if dmax < df["data_ndeshjes"].max():
        print(f"\n  ⚠️ Ankorim te {dmax.date()} (data e fundit ME goditje), "
              f"jo te {df['data_ndeshjes'].max().date()}.")
    prerjet = []
    for k in range(N_PRERJE):
        fund = dmax - pd.DateOffset(months=MUAJ_HOLDOUT * k)
        nis = fund - pd.DateOffset(months=MUAJ_HOLDOUT)
        prerjet.append((nis, fund))
    prerjet.reverse()   # nga më e vjetra te më e reja

    print("\n" + "═" * 66)
    print(f"PRERJET ({MUAJ_HOLDOUT} muaj secila, trajnim = gjithçka para prerjes)")
    print("═" * 66)

    rezultatet = {v: [] for v in VARIANTET}
    nll_ruajtur = {v: [] for v in VARIANTET}

    for i, (nis, fund) in enumerate(prerjet, 1):
        tr = df[df["data_ndeshjes"] < nis]
        te = df[(df["data_ndeshjes"] >= nis) & (df["data_ndeshjes"] < fund)]
        if len(tr) < 5000 or len(te) < 300:
            print(f"\n  Prerja {i}: kalohet (train={len(tr)}, test={len(te)} — pak).")
            continue
        sot_te = 100.0 * te["home_avg_sot"].isna().mean()
        print(f"\n  Prerja {i}: train={len(tr)} (deri {nis.date()}) | "
              f"test={len(te)} ({nis.date()} → {fund.date()}) | SOT NULL në test {sot_te:.1f}%")

        for emri, vec in VARIANTET.items():
            r = trajno_dhe_mat(tr, te, vec)
            rezultatet[emri].append(r)
            nll_ruajtur[emri].append(r["nll_per_ndeshje"])
            print(f"    {emri:16s} NLL {r['NLL']:.4f} | MAE {r['MAE']:.4f} | "
                  f"1X2 {r['1X2']:.1f}% | O/U {r['O/U']:.1f}% | CS {r['CS']:.1f}%")

    if not rezultatet["A_baze_31"]:
        sys.exit("\n❌ Asnjë prerje e përdorshme — shiko mbulimin kohor më sipër.")

    # ── PËRMBLEDHJE E ÇIFTUAR kundrejt bazës ──
    print("\n" + "═" * 66)
    print("PËRMBLEDHJE (mesatare mbi prerjet; Δ = kundrejt A, negative = më mirë)")
    print("═" * 66)
    print(f"  {'variant':16s} {'NLL':>9s} {'ΔNLL':>9s} {'±SE':>7s} {'MAE':>8s} "
          f"{'1X2':>7s} {'O/U':>7s} {'CS':>6s}")

    baze_nll = np.concatenate(nll_ruajtur["A_baze_31"])
    for emri in VARIANTET:
        rs = rezultatet[emri]
        nll = np.mean([r["NLL"] for r in rs])
        mae = np.mean([r["MAE"] for r in rs])
        a1 = np.mean([r["1X2"] for r in rs])
        ao = np.mean([r["O/U"] for r in rs])
        cs = np.mean([r["CS"] for r in rs])
        v_nll = np.concatenate(nll_ruajtur[emri])
        d = v_nll - baze_nll                      # diferencë e ÇIFTUAR, për-ndeshje
        dm = d.mean()
        se = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else float("nan")
        print(f"  {emri:16s} {nll:9.4f} {dm:+9.4f} {se:7.4f} {mae:8.4f} "
              f"{a1:7.1f} {ao:7.1f} {cs:6.1f}")
    print("\n  Rregull leximi: një variant fiton vetëm nëse ΔNLL është negativ DHE")
    print("  |ΔNLL| > 2×SE. Përndryshe ndryshimi s'dallohet nga rastësia.")

    # ── PROVA: a shtojnë zhurmë ligat e kategorisë së dytë? ──
    print("\n" + "═" * 66)
    print("PROVA E KATEGORISË SË DYTË (matur VETËM mbi holdout-in e kategorisë 1)")
    print("═" * 66)
    vec = VARIANTET["D_tier_44"]
    for i, (nis, fund) in enumerate(prerjet, 1):
        tr = df[df["data_ndeshjes"] < nis]
        te = df[(df["data_ndeshjes"] >= nis) & (df["data_ndeshjes"] < fund)]
        te1 = te[te["tier"] == 0]
        if len(tr) < 5000 or len(te1) < 300:
            continue
        r_gjitha = trajno_dhe_mat(tr, te1, vec)
        r_vetem1 = trajno_dhe_mat(tr[tr["tier"] == 0], te1, vec)
        d = r_vetem1["nll_per_ndeshje"] - r_gjitha["nll_per_ndeshje"]
        se = d.std(ddof=1) / np.sqrt(len(d))
        print(f"  Prerja {i} (n={len(te1)}):")
        print(f"    trajnuar mbi TË GJITHA : NLL {r_gjitha['NLL']:.4f} | 1X2 {r_gjitha['1X2']:.1f}%")
        print(f"    trajnuar VETËM kat-1   : NLL {r_vetem1['NLL']:.4f} | 1X2 {r_vetem1['1X2']:.1f}%")
        print(f"    Δ (vetëm1 − të gjitha) : {d.mean():+.4f} ± {se:.4f}"
              f"  → {'heqja ndihmon' if d.mean() < -2*se else 'heqja NUK ndihmon'}")

    print("\n✅ Eksperimenti mbaroi. Asnjë model s'u ruajt, prodhimi i paprekur.")


if __name__ == "__main__":
    main()
