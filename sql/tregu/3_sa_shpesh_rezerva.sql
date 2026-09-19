-- ========================================================================
-- 3) SA SHPESH NDIZET VERTET REZERVA — pyetja qe duhet para cdo vendimi
-- Ekzekutoje VETEM kete skedar.
-- ========================================================================
-- `aftesia` ruhet BRENDA best_bet ne momentin e parashikimit, e llogaritur me
-- normat bazë të sakta të asaj dite. Pra s'kemi nevoje ta rindertojme — vetem
-- ta lexojme. Kjo e mbyll pyetjen pa asnje hamendje.
--
-- EDGE_MIN = 0.04. Nje zgjedhje me aftesi nen kete quhet "rezerve": kodi e ka
-- gjykuar pa aftesi dhe e publikon gjithsesi.
--
-- Pjesa e dyte e tabeles jep normen e goditjes per cdo brez aftesie — aty
-- shihet nese premtimi mbahet ose jo, brez per brez.

WITH b AS (
  SELECT
    data,
    best_bet->>'tregu'                          AS tregu,
    NULLIF(best_bet->>'aftesia','')::numeric    AS aftesia,
    NULLIF(best_bet->>'prob','')::numeric       AS prob,
    NULLIF(best_bet->>'baze','')::numeric       AS baze,
    NULLIF(best_bet->>'koef','')::numeric       AS koef,
    is_premium,
    split_part(replace(rezultati_ft,' ',''),'-',1)::int AS gv,
    split_part(replace(rezultati_ft,' ',''),'-',2)::int AS gm
  FROM arkiv_rezultatesh
  WHERE best_bet IS NOT NULL
    AND best_bet->>'tregu' IS NOT NULL
    AND replace(rezultati_ft,' ','') ~ '^[0-9]+-[0-9]+$'
),
z AS (
  SELECT *,
    CASE tregu
      WHEN '1'          THEN (gv >  gm)
      WHEN 'X'          THEN (gv =  gm)
      WHEN '2'          THEN (gv <  gm)
      WHEN 'GG'         THEN (gv > 0 AND gm > 0)
      WHEN 'NG'         THEN (gv = 0 OR  gm = 0)
      WHEN 'Over 1.5'   THEN (gv+gm > 1)
      WHEN 'Under 1.5'  THEN (gv+gm < 2)
      WHEN 'Over 2.5'   THEN (gv+gm > 2)
      WHEN 'Under 2.5'  THEN (gv+gm < 3)
      WHEN 'Over 3.5'   THEN (gv+gm > 3)
      WHEN 'Under 3.5'  THEN (gv+gm < 4)
    END AS goditi,
    CASE WHEN aftesia IS NULL   THEN '? pa aftesi te ruajtur'
         WHEN aftesia <  0.00   THEN 'a) NEGATIVE — nen normen baze'
         WHEN aftesia <  0.04   THEN 'b) 0-4pp — REZERVE'
         WHEN aftesia <  0.10   THEN 'c) 4-10pp'
         WHEN aftesia <  0.20   THEN 'd) 10-20pp'
         ELSE                        'e) 20pp+' END AS brezi
  FROM b
)
SELECT
  brezi,
  count(*)                                              AS n,
  round(100.0*count(*)/sum(count(*)) OVER (),1)         AS pjesa_pct,
  count(*) FILTER (WHERE goditi)                        AS goditje,
  round(100.0*count(*) FILTER (WHERE goditi)
        / NULLIF(count(*) FILTER (WHERE goditi IS NOT NULL),0),1) AS goditur_pct,
  round(100.0*avg(prob),1)                              AS e_premtuar_pct,
  round(100.0*count(*) FILTER (WHERE goditi)
        / NULLIF(count(*) FILTER (WHERE goditi IS NOT NULL),0)
        - 100.0*avg(prob),1)                            AS dallimi_pp,
  round(100.0*avg(aftesia),1)                           AS aftesia_mes_pp,
  round(avg(koef),2)                                    AS koef_mes,
  count(*) FILTER (WHERE is_premium)                    AS prej_tyre_premium
FROM z
GROUP BY brezi
ORDER BY brezi;
