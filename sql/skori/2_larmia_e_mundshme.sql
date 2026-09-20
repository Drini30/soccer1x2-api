-- ========================================================================
-- 2) SA LARMI KA VERTET NE SHPERNDARJET TONA — dhe sa e humbim duke zgjedhur moden
-- Ekzekutoje VETEM kete skedar.
-- ========================================================================
-- Verejtja: publikojme vetem 2-1, 1-2, 2-0, 1-1. Pyetja: a eshte faji i
-- SHPERNDARJES (s'i jep kurre 1-3 nje probabilitet te larte) apo i ZGJEDHJES
-- (shperndarja e ka, po ne marrim gjithmone maje)?
--
-- Per cdo ndeshje shohim skorin me te mundshem nga shperndarja dhe sa
-- probabilitet ka; pastaj sa shpesh skori REAL ishte brenda 3 te pareve.
-- Nese `brenda_3_pct` eshte shume me i larte se `mode_pct`, shperndarja di me
-- shume se sa tregojme — dhe humbja vjen nga publikimi i nje skori te vetem.

WITH b AS (
  SELECT
    to_char(data::date,'YYYY-MM')  AS muaji,
    replace(rezultati_ft,' ','')   AS real,
    parashikimi                     AS pub,
    dist_gola                       AS dg
  FROM arkiv_rezultatesh
  WHERE replace(rezultati_ft,' ','') ~ '^[0-9]+-[0-9]+$'
    AND dist_gola IS NOT NULL
    AND parashikimi ~ '^[0-9]+-[0-9]+$'
),
top AS (
  SELECT b.*,
    (SELECT e.k FROM jsonb_each_text(b.dg) AS e(k,v)
      ORDER BY e.v::numeric DESC LIMIT 1)                       AS skori_1,
    (SELECT array_agg(k ORDER BY v::numeric DESC)
       FROM (SELECT e.k, e.v FROM jsonb_each_text(b.dg) AS e(k,v)
              ORDER BY e.v::numeric DESC LIMIT 3) AS t3(k,v))   AS tre_te_paret,
    (SELECT max(e.v::numeric) FROM jsonb_each_text(b.dg) AS e(k,v)) AS freq_maks
  FROM b
)
SELECT
  muaji,
  count(*)                                                        AS ndeshje,
  count(DISTINCT pub)                                             AS skore_te_publikuara,
  round(100.0*avg(freq_maks/50000.0),1)                           AS prob_e_modes,
  count(*) FILTER (WHERE pub = real)                              AS goditje_1_skor,
  round(100.0*count(*) FILTER (WHERE pub = real)/count(*),1)      AS goditje_1_pct,
  count(*) FILTER (WHERE real = ANY(tre_te_paret))                AS goditje_3_skore,
  round(100.0*count(*) FILTER (WHERE real = ANY(tre_te_paret))/count(*),1) AS goditje_3_pct,
  count(*) FILTER (WHERE (dg->>real) IS NOT NULL)                 AS real_ne_shperndarje,
  round(100.0*count(*) FILTER (WHERE (dg->>real) IS NOT NULL)/count(*),1) AS real_ne_shperndarje_pct
FROM top
GROUP BY muaji
ORDER BY muaji;
