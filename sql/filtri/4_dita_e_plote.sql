-- ========================================================================
-- 4) NJE DITE E PLOTE, PASI TE KENE MBARUAR TE GJITHA
-- Ekzekutoje VETEM kete skedar.  ⬇ NDRYSHO DATEN TE DY VENDET
-- ========================================================================
-- Analiza e djeshme u be me disa ndeshje ende pa mbaruar. Kjo e rimat diten e
-- plote, dhe i ndan DY perkufizimet e "filtrit" — qe per 18 shtatorin NUK jane
-- e njejta gje:
--
--   is_premium   = si eshte SHENUAR ne baze. Per 18/09 kjo eshte E NDOTUR:
--                  rruga `_zbulo_pf` shtonte ndeshje te mbaruara jashte kuotes,
--                  dhe u hoq vetem ne mbremje te 18-tes.
--   vendi <= 10  = maja e VERTETE sipas koeficientit tone — grupi qe filtri do
--                  te kishte zgjedhur pa ate ndotje.
--
-- Kolona `filtri`:
--   ★ PPM     = ne maje DHE e shenuar  (zgjedhje e ligjshme)
--   ⚠ shtese  = e shenuar po JASHTE majes (ndotja)
--   · maja    = ne maje po e pashenuar (nuk duhet te ndodhe)

WITH b AS (
  SELECT
    p.data, p.ora, p.ndeshja, p.liga_emri, p.statusi, p.is_premium,
    p.rezultati_sakt, p.rezultati,
    COALESCE(NULLIF(p.training_data->>'build',''),'(pa vule)') AS build,
    NULLIF(regexp_replace(p.koef_rez_sakt::text,'[^0-9.]','','g'),'')::numeric AS koef,
    (p.training_data->>'xg_1')::numeric AS xg1,
    (p.training_data->>'xg_2')::numeric AS xg2,
    split_part(p.rezultati_sakt,'-',1)::int AS g1,
    split_part(p.rezultati_sakt,'-',2)::int AS g2,
    NULLIF(split_part(replace(p.rezultati,' ',''),'-',1),'')::int AS r1,
    NULLIF(split_part(replace(p.rezultati,' ',''),'-',2),'')::int AS r2
  FROM predictions p
  WHERE p.data = '2026-09-18'
    AND p.rezultati_sakt ~ '^[0-9]+-[0-9]+$'
    AND p.koef_rez_sakt IS NOT NULL
),
r AS (SELECT *, row_number() OVER (ORDER BY koef ASC) AS vendi FROM b)
SELECT
  vendi,
  CASE WHEN is_premium AND vendi <= 10 THEN 'PPM'
       WHEN is_premium AND vendi >  10 THEN 'shtese'
       WHEN vendi <= 10                THEN 'maja-pa-shenje'
       ELSE '' END                                        AS filtri,
  ora, ndeshja, liga_emri,
  round(koef,2) AS koef, round(100.0/koef,1) AS prob_perqind,
  rezultati_sakt AS skori_yne, rezultati AS reali, statusi,
  CASE WHEN r1 IS NULL THEN NULL WHEN g1=r1 AND g2=r2 THEN 1 ELSE 0 END AS skori_ok,
  CASE WHEN r1 IS NULL THEN NULL
       WHEN (CASE WHEN g1>g2 THEN 1 WHEN g2>g1 THEN 2 ELSE 0 END)
          = (CASE WHEN r1>r2 THEN 1 WHEN r2>r1 THEN 2 ELSE 0 END) THEN 1 ELSE 0 END AS drejtimi_ok,
  round(xg1,2) AS xg_1, round(xg2,2) AS xg_2,
  round(xg1+xg2,2) AS totali_i_pritur,
  (g1+g2) AS totali_yne, (r1+r2) AS totali_real,
  build
FROM r
ORDER BY vendi;
