-- ========================================================================
-- 2) A FUNKSIONOI FILTRI — premium duhet te jete PIKERISHT maja e dites
-- Ekzekutoje VETEM kete skedar.
-- ========================================================================
-- Filtri zgjedh ndeshjet me koeficientin me te ULET (probabilitet me te larte).
-- Nese punon, atehere: cdo premium ka vend <= 10, dhe asnje jo-premium nuk ka
-- vend <= 10 me perjashtim te atyre qe kishin nisur kur u zgjodh dita.
--
-- Kolona `gjykimi` e jep pergjigjen direkt.

WITH p AS (
  SELECT
    data, is_premium, ndeshja, ora, liga_emri, statusi,
    rezultati_sakt, rezultati,
    COALESCE(NULLIF(training_data->>'build',''),'(pa vule)') AS build,
    NULLIF(regexp_replace(koef_rez_sakt::text, '[^0-9.]', '', 'g'), '')::numeric AS koef
  FROM predictions
  WHERE data IN ('2026-09-16', '2026-09-17')
    AND koef_rez_sakt IS NOT NULL
),
r AS (
  SELECT *, row_number() OVER (PARTITION BY data ORDER BY koef ASC) AS vendi
  FROM p
)
SELECT
  data,
  count(*)                                             AS ndeshje,
  count(*) FILTER (WHERE is_premium)                   AS premium,
  max(vendi) FILTER (WHERE is_premium)                 AS vendi_me_i_keq_premium,
  min(vendi) FILTER (WHERE NOT is_premium)             AS vendi_me_i_mire_jashte,
  round(max(koef) FILTER (WHERE is_premium), 2)        AS koef_maks_premium,
  round(min(koef) FILTER (WHERE NOT is_premium), 2)    AS koef_min_jashte,
  CASE
    WHEN count(*) FILTER (WHERE is_premium) = 0 THEN 'pa premium fare'
    WHEN max(vendi) FILTER (WHERE is_premium)
         < min(vendi) FILTER (WHERE NOT is_premium)
      THEN 'PUNOI — premium = maja, pa asnje shkelje'
    ELSE 'DEFEKT — ka premium me poshte se nje i lene jashte'
  END                                                  AS gjykimi
FROM r
GROUP BY data
ORDER BY data;
