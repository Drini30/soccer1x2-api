-- ========================================================================
-- 1) DITA E SOTME, NDESHJE PER NDESHJE — brenda dhe jashte filtrit
-- Ekzekutoje VETEM kete skedar.
-- ========================================================================
-- Rendit sipas koeficientit (probabilitetit tone). Nese filtri punon, ndeshjet
-- me shenjen PPM duhet te jene TE GJITHA ne maje te listes, pa asnje te lene
-- jashte mes tyre — dhe goditjet duhet te grumbullohen aty.
--
-- Ndrysho daten nese do nje dite tjeter.

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
  WHERE p.data = CURRENT_DATE::text
    AND p.rezultati_sakt ~ '^[0-9]+-[0-9]+$'
    AND p.koef_rez_sakt IS NOT NULL
),
r AS (
  SELECT *, row_number() OVER (ORDER BY koef ASC) AS vendi FROM b
)
SELECT
  vendi,
  CASE WHEN is_premium THEN '★ PPM' ELSE '' END AS filtri,
  ora, ndeshja, liga_emri,
  round(koef,2) AS koef, round(100.0/koef,1) AS prob_perqind,
  rezultati_sakt AS skori_yne, rezultati AS reali, statusi,
  CASE WHEN r1 IS NULL THEN NULL WHEN g1=r1 AND g2=r2 THEN 1 ELSE 0 END AS skori_ok,
  CASE WHEN r1 IS NULL THEN NULL
       WHEN (CASE WHEN g1>g2 THEN 1 WHEN g2>g1 THEN 2 ELSE 0 END)
          = (CASE WHEN r1>r2 THEN 1 WHEN r2>r1 THEN 2 ELSE 0 END) THEN 1 ELSE 0 END AS drejtimi_ok,
  round(xg1,2) AS xg_1, round(xg2,2) AS xg_2,
  build
FROM r
ORDER BY vendi;
