-- ========================================================================
-- EKSPORT: 2026-07 (korrik) — nje muaj i vetem, qe te mos priteet
-- Ekzekutoje VETEM kete skedar, pastaj Export -> CSV.
-- ========================================================================
-- Heren e kaluar erdhen vetem 99 rreshta nga ~1,409. Redaktori i Supabase e pret
-- rezultatin. Nje muaj ka 300-570 rreshta, pra kalon i plote.
-- Ekzekutoji te tre dhe me nis te tre CSV-te.

SELECT
  data,
  liga, ndeshja,
  koef_1, koef_x, koef_2,
  round( ((1/koef_1::numeric)/((1/koef_1::numeric)+(1/koef_x::numeric)+(1/koef_2::numeric)))::numeric, 4) AS p1,
  round( ((1/koef_x::numeric)/((1/koef_1::numeric)+(1/koef_x::numeric)+(1/koef_2::numeric)))::numeric, 4) AS px,
  round( ((1/koef_2::numeric)/((1/koef_1::numeric)+(1/koef_x::numeric)+(1/koef_2::numeric)))::numeric, 4) AS p2,
  round((training_data->>'xg_1')::numeric, 3)             AS xg_1,
  round((training_data->>'xg_2')::numeric, 3)             AS xg_2,
  round(((training_data->>'xg_1')::numeric
       + (training_data->>'xg_2')::numeric), 3)           AS lambda,
  round(((training_data->>'xg_1')::numeric
       - (training_data->>'xg_2')::numeric), 3)           AS hendeku_xg,
  parashikimi,
  (split_part(parashikimi,'-',1)::int
 + split_part(parashikimi,'-',2)::int)                    AS totali_publikuar,
  rezultati_ft,
  split_part(replace(rezultati_ft,' ',''),'-',1)::int     AS gola_vendas,
  split_part(replace(rezultati_ft,' ',''),'-',2)::int     AS gola_mysafir,
  (split_part(replace(rezultati_ft,' ',''),'-',1)::int
 + split_part(replace(rezultati_ft,' ',''),'-',2)::int)   AS totali_real,
  is_premium
FROM arkiv_rezultatesh
WHERE data >= '2026-07-01' AND data < (date '2026-07-01' + interval '1 month')
  AND koef_1 IS NOT NULL AND koef_x IS NOT NULL AND koef_2 IS NOT NULL
  AND koef_1::numeric > 1 AND koef_x::numeric > 1 AND koef_2::numeric > 1
  AND training_data->>'xg_1' IS NOT NULL
  AND parashikimi ~ '^[0-9]+-[0-9]+$'
  AND replace(rezultati_ft,' ','') ~ '^[0-9]+-[0-9]+$'
ORDER BY data, ndeshja;
