-- ========================================================================
-- 2) QE NGA RREGULLIMI — grumbullimi dite pas dite
-- Ekzekutoje VETEM kete skedar. Kjo eshte matja qe vlen.
-- ========================================================================
-- Nje dite e vetme s'thote asgje: sot p = 0.042, po nje goditje me pak e con ne
-- 0.32. Kjo pyetje e mban shumen qe rritet dite pas dite, dhe kolona
-- `p_kumulativ_perafert` tregon kur behet e pamundur qe te jete rastesi.
--
-- Perfshin VETEM ditet e gjeneruara nga kodi i rregulluar — ditet me vule te
-- vjeter ose pa vule i perkasin filtrit qe hoqem dhe do ta ndotnin matjen.

WITH b AS (
  SELECT
    p.data, p.is_premium,
    split_part(p.rezultati_sakt,'-',1)::int AS g1,
    split_part(p.rezultati_sakt,'-',2)::int AS g2,
    NULLIF(split_part(replace(p.rezultati,' ',''),'-',1),'')::int AS r1,
    NULLIF(split_part(replace(p.rezultati,' ',''),'-',2),'')::int AS r2
  FROM predictions p
  WHERE p.data >= '2026-09-18'
    AND p.rezultati_sakt ~ '^[0-9]+-[0-9]+$'
    AND p.rezultati IS NOT NULL
    AND replace(p.rezultati,' ','') ~ '^[0-9]+-[0-9]+$'
    AND p.statusi IN ('FT','AET','PEN','AWD','WO')
    AND COALESCE(p.training_data->>'build','') LIKE '2026-09-1%'
),
d AS (
  SELECT *,
    CASE WHEN g1=r1 AND g2=r2 THEN 1 ELSE 0 END AS skor_ok,
    CASE WHEN (CASE WHEN g1>g2 THEN 1 WHEN g2>g1 THEN 2 ELSE 0 END)
            = (CASE WHEN r1>r2 THEN 1 WHEN r2>r1 THEN 2 ELSE 0 END) THEN 1 ELSE 0 END AS drejt_ok
  FROM b
),
ditore AS (
  SELECT
    data,
    count(*)                                         AS ndeshje,
    count(*) FILTER (WHERE is_premium)               AS ppm,
    sum(skor_ok)                                     AS skor_te_gjitha,
    sum(skor_ok) FILTER (WHERE is_premium)           AS skor_ppm,
    sum(drejt_ok)                                    AS drejt_te_gjitha,
    sum(drejt_ok) FILTER (WHERE is_premium)          AS drejt_ppm
  FROM d GROUP BY data
)
SELECT
  data, ndeshje, ppm,
  skor_ppm, skor_te_gjitha,
  round(100.0*skor_ppm/NULLIF(ppm,0),1)                        AS skor_ppm_pct,
  round(100.0*(skor_te_gjitha-skor_ppm)/NULLIF(ndeshje-ppm,0),1) AS skor_jashte_pct,
  round(100.0*drejt_ppm/NULLIF(ppm,0),1)                       AS drejt_ppm_pct,
  round(100.0*(drejt_te_gjitha-drejt_ppm)/NULLIF(ndeshje-ppm,0),1) AS drejt_jashte_pct,
  -- shuma qe rritet: keto jane numrat qe do te lexojme pas nje jave
  sum(ppm)            OVER (ORDER BY data) AS kum_ppm,
  sum(skor_ppm)       OVER (ORDER BY data) AS kum_skor_ppm,
  sum(ndeshje-ppm)    OVER (ORDER BY data) AS kum_jashte,
  sum(skor_te_gjitha-skor_ppm) OVER (ORDER BY data) AS kum_skor_jashte
FROM ditore
ORDER BY data;
