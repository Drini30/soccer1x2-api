-- ========================================================================
-- SA RRESHTA TE ARKIVIT PERZIEJNE DY GJENERIME TE NDRYSHME?
-- Ekzekutoje VETEM kete skedar. Nje rresht per muaj.
-- ========================================================================
--
-- PSE: nje ndeshje rigjenerohet çdo ~30 min deri ne fillim. Kodi i ngrin disa
-- fusha qe ne gjenerimin e PARE dhe i mbishkruan te tjerat ne çdo gjenerim:
--
--   te ngrira (gjenerimi i PARE)    : parashikimi, dist_gola
--   te mbishkruara (i FUNDIT)        : training_data, tregjet_full, prob_1/x/2
--
-- Pra nje rresht arkivi mund ta kete skorin e publikuar nga nje gjenerim dhe
-- xg_1/xg_2/build nga nje tjeter. Çdo analize "ndeshje per ndeshje" qe i vendos
-- krah per krah i perzien — pa e ditur.
--
-- SI MATET: e njejta matrice H prodhon edhe dist_gola edhe tregjet. Nga te dyja
-- llogaritet P(Under 1.5) = P(0-0) + P(1-0) + P(0-1):
--     nga dist_gola     -> (n[0-0] + n[1-0] + n[0-1]) / 50000   (gjenerimi i pare)
--     nga tregjet_full  -> 'Under 1.5'                           (gjenerimi i fundit)
-- I njejti gjenerim: ndryshimi <= 0.00008 (vetem rrumbullakim). Gjenerime te
-- ndryshme: pothuajse gjithmone me shume, sepse λ leviz dhe simulimi ndryshon.
-- Pragu 0.0001. Disa perzierje me levizje fare te vogel kalojne si "i njejti" —
-- pra `pct_perziera` eshte kufi i POSHTEM.
--
-- KUJDES: perjashtohen rreshtat qe s'jane mbi baze 50000 (motori i vjeter ose
-- dist_gola bosh) — aty krahasimi s'ka kuptim.

WITH a AS (
  SELECT
    data,
    (COALESCE((dist_gola->>'0-0')::numeric, 0)
     + COALESCE((dist_gola->>'1-0')::numeric, 0)
     + COALESCE((dist_gola->>'0-1')::numeric, 0)) / 50000.0           AS u15_pare,
    NULLIF(tregjet_full->>'Under 1.5', '')::numeric                    AS u15_fundit,
    (SELECT sum(v::numeric) FROM jsonb_each_text(dist_gola) AS e(k, v)) AS shuma_dist
  FROM arkiv_rezultatesh
  WHERE jsonb_typeof(dist_gola) = 'object'
    AND dist_gola ? '0-0' AND dist_gola ? '1-0' AND dist_gola ? '0-1'
    AND tregjet_full ? 'Under 1.5'
),
b AS (
  SELECT data, abs(u15_pare - u15_fundit) AS diferenca
  FROM a
  WHERE shuma_dist BETWEEN 40000 AND 50100
)
SELECT
  to_char(date_trunc('month', data::date), 'YYYY-MM')                AS muaji,
  count(*)                                                            AS ndeshje,
  count(*) FILTER (WHERE diferenca <= 0.0001)                         AS i_njejti_gjenerim,
  count(*) FILTER (WHERE diferenca >  0.0001)                         AS gjenerime_te_perziera,
  round(100.0 * count(*) FILTER (WHERE diferenca > 0.0001) / count(*), 1) AS pct_perziera,
  round(avg(diferenca) FILTER (WHERE diferenca > 0.0001), 4)          AS dif_mesatare_kur_perziera,
  round(max(diferenca), 4)                                            AS dif_maks
FROM b
GROUP BY 1
ORDER BY 1;
