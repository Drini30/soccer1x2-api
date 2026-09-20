-- ========================================================================
-- TREGU I PLOTE: 2026-07 (korrik) — gjithcka qe tregu di per skorin
-- Ekzekutoje VETEM kete skedar, pastaj Export -> CSV.
-- ========================================================================
-- PYETJA: po ta ndertonim shperndarjen e skoreve TERESISHT nga tregu — jo vetem
-- nga O/U si tani, por nga CS, GG/NG dhe 1X2 bashke — a do te ishte me e mire se
-- e jona? Dhe a fiton dicka perzierja e te dyjave?
--
-- Per kete duhen te dy shperndarjet ne te njejtin rresht:
--   cs_*  = kuota e bukmejkerit per ate skor   (shperndarja e TREGUT)
--   ne_*  = sa nga 50,000 simulime dhane ate skor (shperndarja JONE)
--   k_*   = kuota e tregut per tregjet kryesore
--   p_*   = probabiliteti yne per te njejtat
--
-- 20 skoret e zgjedhura mbulojne mbi 95% te rezultateve reale.
-- ⚠️ `dist_gola` ruante 15 skore deri me 12/09 dhe 40 pas saj — prandaj muajt
--    ndahen, qe korriku te mos ndeshkohet per dicka qe s'e ruante.

SELECT
  data, liga, ndeshja,
  split_part(replace(rezultati_ft,' ',''),'-',1)::int   AS gola_vendas,
  split_part(replace(rezultati_ft,' ',''),'-',2)::int   AS gola_mysafir,
  replace(rezultati_ft,' ','')                          AS skori_real,
  parashikimi                                           AS skori_yne,
  (SELECT count(*) FROM jsonb_each_text(dist_gola))     AS sa_skore_ruajtem,
  (SELECT sum(1.0/NULLIF(e.v::numeric,0))
     FROM jsonb_each_text(odds_reale->'CS') AS e(k,v)
    WHERE e.v ~ '^[0-9.]+$')                            AS marzhi_cs,
  NULLIF(odds_reale->'CS'->>'0-0','')::numeric        AS cs_0_0,
  COALESCE((dist_gola->>'0-0')::numeric,0)            AS ne_0_0,
  NULLIF(odds_reale->'CS'->>'1-0','')::numeric        AS cs_1_0,
  COALESCE((dist_gola->>'1-0')::numeric,0)            AS ne_1_0,
  NULLIF(odds_reale->'CS'->>'0-1','')::numeric        AS cs_0_1,
  COALESCE((dist_gola->>'0-1')::numeric,0)            AS ne_0_1,
  NULLIF(odds_reale->'CS'->>'1-1','')::numeric        AS cs_1_1,
  COALESCE((dist_gola->>'1-1')::numeric,0)            AS ne_1_1,
  NULLIF(odds_reale->'CS'->>'2-0','')::numeric        AS cs_2_0,
  COALESCE((dist_gola->>'2-0')::numeric,0)            AS ne_2_0,
  NULLIF(odds_reale->'CS'->>'0-2','')::numeric        AS cs_0_2,
  COALESCE((dist_gola->>'0-2')::numeric,0)            AS ne_0_2,
  NULLIF(odds_reale->'CS'->>'2-1','')::numeric        AS cs_2_1,
  COALESCE((dist_gola->>'2-1')::numeric,0)            AS ne_2_1,
  NULLIF(odds_reale->'CS'->>'1-2','')::numeric        AS cs_1_2,
  COALESCE((dist_gola->>'1-2')::numeric,0)            AS ne_1_2,
  NULLIF(odds_reale->'CS'->>'2-2','')::numeric        AS cs_2_2,
  COALESCE((dist_gola->>'2-2')::numeric,0)            AS ne_2_2,
  NULLIF(odds_reale->'CS'->>'3-0','')::numeric        AS cs_3_0,
  COALESCE((dist_gola->>'3-0')::numeric,0)            AS ne_3_0,
  NULLIF(odds_reale->'CS'->>'0-3','')::numeric        AS cs_0_3,
  COALESCE((dist_gola->>'0-3')::numeric,0)            AS ne_0_3,
  NULLIF(odds_reale->'CS'->>'3-1','')::numeric        AS cs_3_1,
  COALESCE((dist_gola->>'3-1')::numeric,0)            AS ne_3_1,
  NULLIF(odds_reale->'CS'->>'1-3','')::numeric        AS cs_1_3,
  COALESCE((dist_gola->>'1-3')::numeric,0)            AS ne_1_3,
  NULLIF(odds_reale->'CS'->>'3-2','')::numeric        AS cs_3_2,
  COALESCE((dist_gola->>'3-2')::numeric,0)            AS ne_3_2,
  NULLIF(odds_reale->'CS'->>'2-3','')::numeric        AS cs_2_3,
  COALESCE((dist_gola->>'2-3')::numeric,0)            AS ne_2_3,
  NULLIF(odds_reale->'CS'->>'3-3','')::numeric        AS cs_3_3,
  COALESCE((dist_gola->>'3-3')::numeric,0)            AS ne_3_3,
  NULLIF(odds_reale->'CS'->>'4-0','')::numeric        AS cs_4_0,
  COALESCE((dist_gola->>'4-0')::numeric,0)            AS ne_4_0,
  NULLIF(odds_reale->'CS'->>'0-4','')::numeric        AS cs_0_4,
  COALESCE((dist_gola->>'0-4')::numeric,0)            AS ne_0_4,
  NULLIF(odds_reale->'CS'->>'4-1','')::numeric        AS cs_4_1,
  COALESCE((dist_gola->>'4-1')::numeric,0)            AS ne_4_1,
  NULLIF(odds_reale->'CS'->>'1-4','')::numeric        AS cs_1_4,
  COALESCE((dist_gola->>'1-4')::numeric,0)            AS ne_1_4,
  NULLIF(odds_reale->>'1','')::numeric              AS k_1,
  NULLIF(tregjet_full->>'1','')::numeric            AS p_1,
  NULLIF(odds_reale->>'X','')::numeric              AS k_x,
  NULLIF(tregjet_full->>'X','')::numeric            AS p_x,
  NULLIF(odds_reale->>'2','')::numeric              AS k_2,
  NULLIF(tregjet_full->>'2','')::numeric            AS p_2,
  NULLIF(odds_reale->>'GG','')::numeric              AS k_gg,
  NULLIF(tregjet_full->>'GG','')::numeric            AS p_gg,
  NULLIF(odds_reale->>'NG','')::numeric              AS k_ng,
  NULLIF(tregjet_full->>'NG','')::numeric            AS p_ng,
  NULLIF(odds_reale->>'Over 1.5','')::numeric              AS k_over_1_5,
  NULLIF(tregjet_full->>'Over 1.5','')::numeric            AS p_over_1_5,
  NULLIF(odds_reale->>'Under 1.5','')::numeric              AS k_under_1_5,
  NULLIF(tregjet_full->>'Under 1.5','')::numeric            AS p_under_1_5,
  NULLIF(odds_reale->>'Over 2.5','')::numeric              AS k_over_2_5,
  NULLIF(tregjet_full->>'Over 2.5','')::numeric            AS p_over_2_5,
  NULLIF(odds_reale->>'Under 2.5','')::numeric              AS k_under_2_5,
  NULLIF(tregjet_full->>'Under 2.5','')::numeric            AS p_under_2_5,
  NULLIF(odds_reale->>'Over 3.5','')::numeric              AS k_over_3_5,
  NULLIF(tregjet_full->>'Over 3.5','')::numeric            AS p_over_3_5,
  NULLIF(odds_reale->>'Under 3.5','')::numeric              AS k_under_3_5,
  NULLIF(tregjet_full->>'Under 3.5','')::numeric            AS p_under_3_5,
  is_premium
FROM arkiv_rezultatesh
WHERE data >= '2026-07-01' AND data < (date '2026-07-01' + interval '1 month')
  AND odds_reale IS NOT NULL
  AND odds_reale->'CS' IS NOT NULL
  AND dist_gola IS NOT NULL
  AND replace(rezultati_ft,' ','') ~ '^[0-9]+-[0-9]+$'
ORDER BY data, ndeshja;
