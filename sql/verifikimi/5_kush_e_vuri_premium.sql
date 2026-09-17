-- ========================================================================
-- KUSH E VURI is_premium? — kuota eshte 10/dite, po numrat dolen 14 dhe 12
-- Ekzekutoje VETEM kete skedar.
-- ========================================================================
--
-- DYSHIMI: `is_premium` sherben per DY gjera qe s'kane lidhje me njera-tjetren:
--   (1) "u publikua si premium sot"  — e kufizuar nga PPM_MAKS_DITE = 10
--   (2) "shfaqet te Historiku PPM"   — e pakufizuar, vihet me vone, retroaktive
--
-- Rruga (2) eshte te `_pf_risinkro`: kur nje pike PPM zbulohet dhe ndeshja mbaron,
-- kodi ben PATCH `is_premium = true` PA e pyetur fare kuoten.
--
-- PSE KA RENDESI: filtri PPM zgjedh ndeshjet me koeficientin me te ULET (pra
-- probabiliteti me i larte). Nese te grupi "premium" hyjne edhe ndeshje te vena
-- nga rruga (2), atehere cdo matje e ardhshme e tipit "a funksionoi filtri PPM"
-- eshte e ndotur — po masim nje grup qe filtri nuk e zgjodhi.
--
-- SI LEXOHET: nese `koef_maks` eshte shume me i larte se `koef_min_jashte`,
-- atehere ne grupin premium ka ndeshje qe filtri s'do t'i kishte zgjedhur kurre.

WITH p AS (
  SELECT
    data,
    is_premium,
    NULLIF(regexp_replace(koef_rez_sakt::text, '[^0-9.]', '', 'g'), '')::numeric AS koef,
    ndeshja, ora, liga_emri, rezultati_sakt, rezultati, statusi
  FROM predictions
  WHERE data IN ('2026-09-14', '2026-09-15', '2026-09-16')
    AND koef_rez_sakt IS NOT NULL
)
SELECT
  data,
  count(*) FILTER (WHERE is_premium)                    AS premium,
  10                                                    AS kuota,
  count(*) FILTER (WHERE is_premium) - 10               AS mbi_kuoten,
  round(min(koef) FILTER (WHERE is_premium), 2)         AS koef_min_premium,
  round(max(koef) FILTER (WHERE is_premium), 2)         AS koef_maks_premium,
  round(min(koef) FILTER (WHERE NOT is_premium), 2)     AS koef_min_jashte,
  CASE
    WHEN max(koef) FILTER (WHERE is_premium)
         > min(koef) FILTER (WHERE NOT is_premium)
    THEN 'NDOTUR — ka premium me koef me te keq se nje i lene jashte'
    ELSE 'i paster — premium = maja e dites'
  END                                                   AS gjykimi
FROM p
GROUP BY data
ORDER BY data;


-- ── Lista: cilat premium jane JASHTE majes se dites ──────────────────────
-- Keto jane kandidatet per "u vune nga rruga e dyte, jo nga filtri".
WITH p AS (
  SELECT
    data, is_premium, ndeshja, ora, liga_emri, statusi, rezultati_sakt, rezultati,
    NULLIF(regexp_replace(koef_rez_sakt::text, '[^0-9.]', '', 'g'), '')::numeric AS koef
  FROM predictions
  WHERE data IN ('2026-09-14', '2026-09-15', '2026-09-16')
    AND koef_rez_sakt IS NOT NULL
),
r AS (
  SELECT *, row_number() OVER (PARTITION BY data ORDER BY koef ASC) AS vendi
  FROM p
)
SELECT data, vendi, ndeshja, ora, liga_emri,
       round(koef, 2) AS koef,
       round(100.0 / koef, 1) AS prob_perqind,
       is_premium,
       statusi, rezultati_sakt AS skori_yne, rezultati AS reali,
       CASE WHEN is_premium AND vendi > 10 THEN '← mbi kuoten, jashte majes'
            WHEN NOT is_premium AND vendi <= 10 THEN '← ishte ne maje po s''u zgjodh'
            ELSE '' END AS shenim
FROM r
WHERE (is_premium AND vendi > 10) OR (NOT is_premium AND vendi <= 10)
ORDER BY data, vendi;
