-- ========================================================================
-- λ NEN-PERGJIGJET NDAJ MOSPERPUTHJES? — testi mbi gjithe arkivin
-- Ekzekutoje VETEM kete skedar.
-- ========================================================================
-- HIPOTEZA (nga 42 ndeshje te 16-17 shtatorit):
--   λ = xg_1 + xg_2 eshte e kalibruar MESATARISHT (2.87 kundrejt 2.93 reale)
--   por e NGURTE: levize vetem +0.33 gola mes ndeshjeve te balancuara dhe
--   shtypjeve, kur realiteti levizi +1.82.
--
-- KY TEST e ndan sipas MUAJIT me qellim. Rregulli qe vendosem pas kater gjetjesh
-- qe avulluan: asgje nuk vlen derisa te shihet VECMAS ne dy periudha. Nese trendi
-- duket vetem ne shtator, eshte zhurme e nje dritareje.
--
-- LEXIMI: kolona `levizja_reale` minus `levizja_lambda` per cdo muaj. Nese λ e
-- ndjek realitetin, ato dy duhet te jene afer. Nese λ eshte e ngurte, `lambda_gab`
-- do te rritet monotonikisht nga brezi i pare te i fundit — ne CDO muaj.

WITH b AS (
  SELECT
    to_char(data::date, 'YYYY-MM')                       AS muaji,
    koef_1::numeric AS k1, koef_x::numeric AS kx, koef_2::numeric AS k2,
    (training_data->>'xg_1')::numeric                    AS xg1,
    (training_data->>'xg_2')::numeric                    AS xg2,
    split_part(parashikimi,'-',1)::int
      + split_part(parashikimi,'-',2)::int               AS totali_pub,
    split_part(replace(rezultati_ft,' ',''),'-',1)::int
      + split_part(replace(rezultati_ft,' ',''),'-',2)::int AS totali_real
  FROM arkiv_rezultatesh
  WHERE koef_1 IS NOT NULL AND koef_x IS NOT NULL AND koef_2 IS NOT NULL
    AND koef_1::numeric > 1 AND koef_x::numeric > 1 AND koef_2::numeric > 1
    AND training_data->>'xg_1' IS NOT NULL
    AND parashikimi ~ '^[0-9]+-[0-9]+$'
    AND replace(rezultati_ft,' ','') ~ '^[0-9]+-[0-9]+$'
),
d AS (
  SELECT *,
    GREATEST( (1/k1)/((1/k1)+(1/kx)+(1/k2)),
              (1/k2)/((1/k1)+(1/kx)+(1/k2)) ) AS p_fav,
    (xg1 + xg2) AS lambda
  FROM b
),
z AS (
  SELECT *,
    CASE WHEN p_fav < 0.45 THEN '1. e ngushte <45%'
         WHEN p_fav < 0.55 THEN '2. lehte 45-55%'
         WHEN p_fav < 0.65 THEN '3. qarte 55-65%'
         WHEN p_fav < 0.80 THEN '4. i forte 65-80%'
         ELSE                   '5. shtypes 80%+' END AS brezi
  FROM d
)
SELECT
  muaji, brezi,
  count(*)                                   AS n,
  round(avg(lambda), 2)                      AS lambda,
  round(avg(totali_real), 2)                 AS reali,
  round(avg(totali_real - lambda), 2)        AS lambda_gab,
  round(avg(totali_pub), 2)                  AS totali_publikuar,
  round(avg(totali_real - totali_pub), 2)    AS publikuar_gab,
  round(stddev_samp(totali_real), 2)         AS sd_reale
FROM z
GROUP BY muaji, brezi
ORDER BY muaji, brezi;
