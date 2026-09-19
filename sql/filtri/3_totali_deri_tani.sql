-- ========================================================================
-- 3) TOTALI DERI TANI — nje rresht i vetem per test
-- Ekzekutoje VETEM kete skedar. Kete ma nis sa here qe te duash nje verdikt.
-- ========================================================================
-- Kater numrat e tabeles 2x2 qe i duhen testit Fisher. Me kete rresht une e
-- llogaris sakte sa e pamundur eshte qe filtri te mos beje asgje.
--
-- PRAGU (i vendosur PARA se te shihen numrat): duhen >= 60 ndeshje PPM te
-- mbaruara para se te nxjerrim perfundim. Sot jemi ne 8.

WITH b AS (
  SELECT
    p.is_premium,
    CASE WHEN split_part(p.rezultati_sakt,'-',1)::int
            = NULLIF(split_part(replace(p.rezultati,' ',''),'-',1),'')::int
          AND split_part(p.rezultati_sakt,'-',2)::int
            = NULLIF(split_part(replace(p.rezultati,' ',''),'-',2),'')::int
         THEN 1 ELSE 0 END AS skor_ok,
    CASE WHEN (CASE WHEN split_part(p.rezultati_sakt,'-',1)::int > split_part(p.rezultati_sakt,'-',2)::int THEN 1
                    WHEN split_part(p.rezultati_sakt,'-',1)::int < split_part(p.rezultati_sakt,'-',2)::int THEN 2 ELSE 0 END)
            = (CASE WHEN NULLIF(split_part(replace(p.rezultati,' ',''),'-',1),'')::int > NULLIF(split_part(replace(p.rezultati,' ',''),'-',2),'')::int THEN 1
                    WHEN NULLIF(split_part(replace(p.rezultati,' ',''),'-',1),'')::int < NULLIF(split_part(replace(p.rezultati,' ',''),'-',2),'')::int THEN 2 ELSE 0 END)
         THEN 1 ELSE 0 END AS drejt_ok
  FROM predictions p
  WHERE p.data >= '2026-09-18'
    AND p.rezultati_sakt ~ '^[0-9]+-[0-9]+$'
    AND p.rezultati IS NOT NULL
    AND replace(p.rezultati,' ','') ~ '^[0-9]+-[0-9]+$'
    AND p.statusi IN ('FT','AET','PEN','AWD','WO')
    AND COALESCE(p.training_data->>'build','') LIKE '2026-09-1%'
)
SELECT
  count(*)                                              AS ndeshje_gjithsej,
  count(*) FILTER (WHERE is_premium)                    AS ppm_n,
  sum(skor_ok) FILTER (WHERE is_premium)                AS ppm_skor,
  count(*) FILTER (WHERE NOT is_premium)                AS jashte_n,
  sum(skor_ok) FILTER (WHERE NOT is_premium)            AS jashte_skor,
  round(100.0*sum(skor_ok) FILTER (WHERE is_premium)
        / NULLIF(count(*) FILTER (WHERE is_premium),0), 1)      AS ppm_skor_pct,
  round(100.0*sum(skor_ok) FILTER (WHERE NOT is_premium)
        / NULLIF(count(*) FILTER (WHERE NOT is_premium),0), 1)  AS jashte_skor_pct,
  sum(drejt_ok) FILTER (WHERE is_premium)               AS ppm_drejt,
  sum(drejt_ok) FILTER (WHERE NOT is_premium)           AS jashte_drejt,
  round(100.0*sum(drejt_ok) FILTER (WHERE is_premium)
        / NULLIF(count(*) FILTER (WHERE is_premium),0), 1)      AS ppm_drejt_pct,
  round(100.0*sum(drejt_ok) FILTER (WHERE NOT is_premium)
        / NULLIF(count(*) FILTER (WHERE NOT is_premium),0), 1)  AS jashte_drejt_pct
FROM b;
