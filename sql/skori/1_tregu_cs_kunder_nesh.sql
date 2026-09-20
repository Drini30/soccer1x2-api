-- ========================================================================
-- 1) SHPERNDARJA E SKOREVE: e jona kunder asaj te TREGUT, koke me koke
-- Ekzekutoje VETEM kete skedar.
-- ========================================================================
-- `odds_reale->'CS'` permban kuotat e bukmejkerit per CDO skor — pra nje
-- shperndarje te plote skoresh, te pavarur nga e jona. E ruajme prej muajsh
-- dhe e perdorim VETEM per te cmuar piken tone (rreshti 363). Kurre si input.
--
-- TESTI: per ndeshjen qe ndodhi vertet, kush i dha me shume probabilitet
-- skorit REAL — ne apo tregu? Kjo eshte matja e drejtperdrejte e asaj se kush
-- di me shume per skorin, pa asnje hamendje.
--
--   p_jona  = dist_gola[skori_real] / 50000
--   p_tregu = (1/kuota_CS[skori_real]) / shuma e te gjitha 1/kuota  (i devigosur)
--   humbja  = -ln(p). Me e VOGEL eshte me mire.
--
-- ⚠️ KUJDES: `dist_gola` ruante vetem 15 skore deri me 12/09, pastaj 40. Rreshtat
--    e vjeter e kane shperndarjen e prere, ndaj ndarja sipas muajit eshte e
--    domosdoshme — pa te, korriku do ta ndeshkonte padrejtesisht modelin tone.

WITH b AS (
  SELECT
    to_char(data::date,'YYYY-MM')          AS muaji,
    replace(rezultati_ft,' ','')           AS real,
    dist_gola                              AS dg,
    odds_reale->'CS'                       AS cs
  FROM arkiv_rezultatesh
  WHERE replace(rezultati_ft,' ','') ~ '^[0-9]+-[0-9]+$'
    AND dist_gola IS NOT NULL
),
m AS (
  SELECT b.*,
    (SELECT sum(1.0/NULLIF(e.v::numeric,0))
       FROM jsonb_each_text(b.cs) AS e(k,v)
      WHERE e.v ~ '^[0-9.]+$') AS shuma_cs,
    (SELECT count(*) FROM jsonb_each_text(b.dg)) AS sa_skore_ruajtem
  FROM b
  WHERE b.cs IS NOT NULL
),
h AS (
  SELECT *,
    GREATEST(COALESCE((dg->>real)::numeric, 0) / 50000.0, 0.00002)          AS p_jona,
    GREATEST(CASE WHEN (cs->>real) ~ '^[0-9.]+$' AND shuma_cs > 0
                  THEN (1.0/(cs->>real)::numeric) / shuma_cs
                  ELSE 0 END, 0.00002)                                       AS p_tregu
  FROM m
  WHERE shuma_cs > 0
)
SELECT
  muaji,
  count(*)                                            AS ndeshje,
  round(avg(sa_skore_ruajtem),1)                      AS skore_te_ruajtura,
  round(100.0*avg(p_jona),2)                          AS p_jona_mes,
  round(100.0*avg(p_tregu),2)                         AS p_tregu_mes,
  round(avg(-ln(p_jona))::numeric, 4)                 AS humbja_jone,
  round(avg(-ln(p_tregu))::numeric, 4)                AS humbja_tregut,
  round((avg(-ln(p_jona)) - avg(-ln(p_tregu)))::numeric, 4) AS dallimi,
  count(*) FILTER (WHERE p_jona > p_tregu)            AS ne_me_mire,
  count(*) FILTER (WHERE p_tregu > p_jona)            AS tregu_me_mire,
  round(100.0*count(*) FILTER (WHERE p_jona > p_tregu)/count(*),1) AS ne_me_mire_pct
FROM h
GROUP BY muaji
ORDER BY muaji;
