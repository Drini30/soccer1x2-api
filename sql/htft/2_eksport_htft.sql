-- ========================================================================
-- 2) EKSPORT HT/FT — ndeshje per ndeshje, per analize te thelle
-- Ekzekutoje VETEM kete skedar, pastaj Export -> CSV.
-- ========================================================================
-- Te gjitha 9 qelizat e shperndarjes sone, plus HT dhe FT reale. Me kete mund
-- te matet kalibrimi qelize per qelize, jo vetem norma e goditjes — dhe te
-- shihet nese njohuria jone per gjysmen e pare eshte e vertete apo derivat i FT-se.

SELECT
  data, liga, ndeshja,
  replace(rezultati_ht,' ','')            AS ht_real,
  replace(parashikimi_ht,' ','')          AS ht_yne,
  replace(rezultati_ft,' ','')            AS ft_real,
  parashikimi                             AS ft_yne,
  goditi_ht, goditi_skor, goditi_1x2,
  round((tregjet_full->'ht_ft'->>'1/1')::numeric,4) AS c11,
  round((tregjet_full->'ht_ft'->>'1/X')::numeric,4) AS c1x,
  round((tregjet_full->'ht_ft'->>'1/2')::numeric,4) AS c12,
  round((tregjet_full->'ht_ft'->>'X/1')::numeric,4) AS cx1,
  round((tregjet_full->'ht_ft'->>'X/X')::numeric,4) AS cxx,
  round((tregjet_full->'ht_ft'->>'X/2')::numeric,4) AS cx2,
  round((tregjet_full->'ht_ft'->>'2/1')::numeric,4) AS c21,
  round((tregjet_full->'ht_ft'->>'2/X')::numeric,4) AS c2x,
  round((tregjet_full->'ht_ft'->>'2/2')::numeric,4) AS c22,
  round((tregjet_full->>'HT 1')::numeric,4)         AS ht_1,
  round((tregjet_full->>'HT X')::numeric,4)         AS ht_x,
  round((tregjet_full->>'HT 2')::numeric,4)         AS ht_2,
  round((tregjet_full->>'HT Over 0.5')::numeric,4)  AS ht_over05,
  round((tregjet_full->>'HT Over 1.5')::numeric,4)  AS ht_over15,
  round((tregjet_full->>'HT GG')::numeric,4)        AS ht_gg,
  koef_1, koef_x, koef_2,
  is_premium
FROM arkiv_rezultatesh
WHERE rezultati_ht IS NOT NULL
  AND tregjet_full->'ht_ft' IS NOT NULL
  AND replace(rezultati_ht,' ','') ~ '^[0-9]+-[0-9]+$'
  AND replace(rezultati_ft,' ','') ~ '^[0-9]+-[0-9]+$'
ORDER BY data, ndeshja;
