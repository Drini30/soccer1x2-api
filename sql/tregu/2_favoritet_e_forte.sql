-- ========================================================================
-- 2) FAVORITET E FORTE (kuota 1X2 nen 1.30) — pyetja jote per NG
-- Ekzekutoje VETEM kete skedar.
-- ========================================================================
-- Verejtja jote: ndeshjet me koeficient 1.10-1.25 dalin me NG.
-- Ka kuptim — nje favorit i madh shpesh e mban rivalin pa shenuar. Po a eshte
-- NG vertet me i mire aty, apo thjesht duket ashtu?
--
-- Kjo pyetje i nxjerr TE GJITHA tregjet ne ate zone, qe te shihet kush del vertet.

WITH b AS (
  SELECT
    odds_reale AS od, tregjet_full AS tg,
    LEAST(NULLIF(od->>'1','')::numeric, NULLIF(od->>'2','')::numeric) AS kuota_fav,
    split_part(replace(rezultati_ft,' ',''),'-',1)::int AS gv,
    split_part(replace(rezultati_ft,' ',''),'-',2)::int AS gm
  FROM arkiv_rezultatesh
  WHERE odds_reale IS NOT NULL
    AND odds_reale->>'1' IS NOT NULL AND odds_reale->>'2' IS NOT NULL
    AND replace(rezultati_ft,' ','') ~ '^[0-9]+-[0-9]+$'
),
z AS (
  SELECT b.*, t.tregu,
    NULLIF(b.od->>t.tregu,'')::numeric AS kuota,
    NULLIF(b.tg->>t.tregu,'')::numeric AS prob_jona,
    CASE t.tregu
      WHEN 'GG'         THEN (gv > 0 AND gm > 0)
      WHEN 'NG'         THEN (gv = 0 OR  gm = 0)
      WHEN 'Over 2.5'   THEN (gv+gm > 2)
      WHEN 'Under 2.5'  THEN (gv+gm < 3)
      WHEN 'Over 3.5'   THEN (gv+gm > 3)
      WHEN 'Under 1.5'  THEN (gv+gm < 2)
      WHEN 'Over 1.5'   THEN (gv+gm > 1)
    END AS doli,
    CASE WHEN kuota_fav < 1.15 THEN 'a) nen 1.15'
         WHEN kuota_fav < 1.30 THEN 'b) 1.15-1.30'
         WHEN kuota_fav < 1.50 THEN 'c) 1.30-1.50'
         ELSE                       'd) 1.50+' END AS brezi_fav
  FROM b
  CROSS JOIN LATERAL (VALUES ('GG'),('NG'),('Over 1.5'),('Under 1.5'),
                             ('Over 2.5'),('Under 2.5'),('Over 3.5')) AS t(tregu)
  WHERE kuota_fav IS NOT NULL
)
SELECT
  brezi_fav, tregu,
  count(*)                                             AS n,
  count(*) FILTER (WHERE doli)                         AS doli,
  round(100.0*count(*) FILTER (WHERE doli)/count(*),1) AS doli_pct,
  round(100.0*avg(1.0/kuota),1)                        AS e_dukshme,
  round(100.0*avg(prob_jona),1)                        AS nga_ne,
  round(100.0*count(*) FILTER (WHERE doli)/count(*) - 100.0*avg(1.0/kuota),1) AS treg_gab,
  round(100.0*count(*) FILTER (WHERE doli)/count(*) - 100.0*avg(prob_jona),1) AS ne_gab,
  round(avg(kuota),2)                                  AS kuota_mes
FROM z
WHERE doli IS NOT NULL AND kuota > 1.0
GROUP BY brezi_fav, tregu
HAVING count(*) >= 20
ORDER BY brezi_fav, doli_pct DESC;
