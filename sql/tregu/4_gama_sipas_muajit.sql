-- ========================================================================
-- 4) I NJEJTI TEST, PO I NDARE SIPAS MUAJIT — a qendron ne te tre periudhat?
-- Ekzekutoje VETEM kete skedar.
-- ========================================================================
-- Testi i pare nxori: tregjet e GOLAVE i nenvleresojme me +3.49pp (n=5,918),
-- tregjet PA GOLA i mbivleresojme me -3.50pp (n=5,946). Simetri e persosur —
-- nje shkak i vetem: λ jone ishte shume e ulet.
--
-- POR: arkivi mbulon korrik-shtator, dhe autokalibrimi e ka ndryshuar XG_NORM
-- gjate asaj periudhe — me 19/09 e ngriti λ nga ~2.81 ne ~2.94. Nese hendeku
-- eshte me i vogel ne shtator se ne korrik, atehere rregullimi ka nisur te
-- veproje dhe s'duhet prekur asgje tjeter.
--
-- Kolona `ne_gab` duhet te LEVIZE drejt zeros nga korriku ne shtator.

WITH b AS (
  SELECT
    to_char(data::date,'YYYY-MM') AS muaji,
    odds_reale AS od, tregjet_full AS tg,
    split_part(replace(rezultati_ft,' ',''),'-',1)::int AS gv,
    split_part(replace(rezultati_ft,' ',''),'-',2)::int AS gm
  FROM arkiv_rezultatesh
  WHERE odds_reale IS NOT NULL
    AND replace(rezultati_ft,' ','') ~ '^[0-9]+-[0-9]+$'
),
m AS (
  SELECT b.*, t.tregu, t.familja,
    NULLIF(b.tg->>t.tregu,'')::numeric AS prob_jona,
    CASE t.tregu
      WHEN 'GG'         THEN (gv > 0 AND gm > 0)
      WHEN 'NG'         THEN (gv = 0 OR  gm = 0)
      WHEN 'Over 1.5'   THEN (gv+gm > 1)
      WHEN 'Under 1.5'  THEN (gv+gm < 2)
      WHEN 'Over 2.5'   THEN (gv+gm > 2)
      WHEN 'Under 2.5'  THEN (gv+gm < 3)
      WHEN 'Over 3.5'   THEN (gv+gm > 3)
      WHEN 'Under 3.5'  THEN (gv+gm < 4)
    END AS doli
  FROM b
  CROSS JOIN LATERAL (VALUES
      ('GG','GOLA'),('Over 1.5','GOLA'),('Over 2.5','GOLA'),('Over 3.5','GOLA'),
      ('NG','PA GOLA'),('Under 1.5','PA GOLA'),('Under 2.5','PA GOLA'),('Under 3.5','PA GOLA')
  ) AS t(tregu, familja)
)
SELECT
  familja, muaji,
  count(*)                                             AS n,
  round(100.0*count(*) FILTER (WHERE doli)/count(*),1) AS doli_pct,
  round(100.0*avg(prob_jona),1)                        AS nga_ne,
  round(100.0*count(*) FILTER (WHERE doli)/count(*) - 100.0*avg(prob_jona),1) AS ne_gab
FROM m
WHERE doli IS NOT NULL AND prob_jona IS NOT NULL
GROUP BY familja, muaji
ORDER BY familja, muaji;
