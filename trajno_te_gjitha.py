# ==========================================================
# TRAJNIM I UNIFIKUAR — FT + HT me 31 VEÇORI
# ==========================================================
# Ky është skripti KANONIK: verifikuar se prodhon modelet që janë në prodhim.
# Përputhja u konfirmua duke lexuar vetë skedarët .json:
#     31 veçori në të njëjtin rend  |  count:poisson  |  400 pemë
# Mos ekzekuto trajnuesit e vjetër (v3.2, v5.1, trajno_ht.py) — ata kanë 26
# veçori dhe do të prodhonin modele që backend-i nuk i lexon dot.
#
# NDRYSHIMI I VETËM nga kopja origjinale: çelësi lexohet nga environment-i.
# Asnjë parametër trajnimi nuk është prekur — që modelet të mbeten riprodhueshëm.
#
# Ekzekuto te Google Colab:
#   !pip install xgboost pandas requests scikit-learn numpy -q
#   import os; os.environ["SUPABASE_SERVICE_KEY"] = "..."   # ose getpass
#
# ⚠️ Pas trajnimit, shkarko TË 4 .json dhe vendosi në repo BASHKË me
#    soccer_api.py — të dyja duhen deployuar njëkohësisht.
# ==========================================================

import os
import sys

import pandas as pd
import requests
import xgboost as xgb
from sklearn.metrics import mean_absolute_error

SUPABASE_URL = os.environ.get(
    "SUPABASE_HISTORIK_URL",
    "https://oqfhlyybwwkjbkvfpsxi.supabase.co/rest/v1/historik_trajnimi",
)
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
if not SUPABASE_KEY:
    sys.exit("❌ Vendos SUPABASE_SERVICE_KEY te environment-i (mos e ngul në kod).")

HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

# 31 veçori — RENDI DUHET IDENTIK me XGB_FEATURES te soccer_api.py!
XGB_FEATURES = [
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

# (emri_skedar, kolona_target)
MODELET = [
    ("model_gola_home.json",    "gola_home"),
    ("model_gola_away.json",    "gola_away"),
    ("model_gola_home_ht.json", "gola_home_ht"),
    ("model_gola_away_ht.json", "gola_away_ht"),
]


def merr_te_gjitha():
    """Shkarkon të gjitha rreshtat (paginim limit/offset)."""
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
        print(f"  ...{len(rresht)} rreshta")
    return pd.DataFrame(rresht)


def main():
    print("Duke shkarkuar të dhënat nga historik_trajnimi...")
    df_full = merr_te_gjitha()
    print(f"Total: {len(df_full)} rreshta")

    mungojne = [c for c in XGB_FEATURES if c not in df_full.columns]
    if mungojne:
        raise SystemExit(f"❌ Mungojnë kolonat te tabela: {mungojne}\n"
                         f"   (Ri-importo me importues_csv_v4.py.)")

    # count:poisson për të 4 (gola = numërim → Poisson)
    params = dict(
        objective="count:poisson",
        max_depth=5, learning_rate=0.05, n_estimators=400,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
        n_jobs=-1, random_state=42,
    )

    print("=" * 62)
    for skedar, target in MODELET:
        df = df_full.copy()
        kolonat = XGB_FEATURES + [target]
        for c in kolonat:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=kolonat).sort_values("data_ndeshjes").reset_index(drop=True)

        n = len(df)
        if n < 500:
            print(f"[{target}] ⚠️ vetëm {n} rreshta — kalohet (pak të dhëna).")
            print("-" * 62)
            continue

        cut = int(n * 0.85)
        tr, te = df.iloc[:cut], df.iloc[cut:]
        Xtr, Xte = tr[XGB_FEATURES].astype(float), te[XGB_FEATURES].astype(float)
        ytr, yte = tr[target].astype(float), te[target].astype(float)

        model = xgb.XGBRegressor(**params)
        model.fit(Xtr, ytr, eval_set=[(Xte, yte)], verbose=False)

        pred_te = model.predict(Xte)
        mae_tr = mean_absolute_error(ytr, model.predict(Xtr))
        mae_te = mean_absolute_error(yte, pred_te)

        print(f"[{target}]  rreshta={n}  (train={len(tr)} | test={len(te)})")
        print(f"  MAE train: {mae_tr:.4f}  |  MAE test: {mae_te:.4f}")
        print(f"  Gola realë (mes test): {yte.mean():.3f}  |  parashik (mes): {pred_te.mean():.3f}")
        model.save_model(skedar)
        print(f"  → Ruajtur: {skedar}")
        print("-" * 62)

    print("\n✅ Modelet u trajnuan me 31 veçori.")
    print("VALIDIM: MAE test ≈ MAE train = pa mbifitim. Gola realë ≈ parashik = i kalibruar.")


if __name__ == "__main__":
    main()
