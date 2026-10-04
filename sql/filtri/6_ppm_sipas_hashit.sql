-- ========================================================================
-- 6) TOTALI I FILTRIT PPM — PPM-ja njihet nga HASH-i, jo nga is_premium
-- Ekzekutoje VETEM kete skedar. Zevendeson numrat e 3_totali_deri_tani.sql.
-- ========================================================================
--
-- PSE: `is_premium` ka DY shkrues ne kod, jo nje:
--   (1) _gjenero_pf ben PATCH is_premium = true per 10 zgjedhjet e PPM-se;
--   (2) çdo rigjenerim (çdo ~30 min deri ne fillim) i rishkruan is_premium te
--       GJITHA ndeshjet VIP: true per 3 me besueshmerine me te larte, false per
--       te tjerat (VALUE_FILTER_ON = 0, sjellja e vjeter "top-3").
-- Rezultati: grupi is_premium = zgjedhjet e PPM-se + deri ne ~3 ne dite qe filtri
-- PPM s'i zgjodhi kurre. Ja pse dolen 14 dhe 12 premium ne dite kur kuota eshte 10.
--
-- Hash-i ne provably_fair krijohet VETEM nga _gjenero_pf, nje here per ndeshje
-- (UNIQUE mbi ndeshja + data), dhe nuk preket me. Pra ai eshte lista e paster e
-- asaj qe zgjodhi filtri.
--
-- PRAGU mbetet ai i vendosur me pare: >= 60 ndeshje PPM te mbaruara.

WITH pf AS (
  SELECT DISTINCT ndeshja, data::text AS data
  FROM provably_fair
  WHERE data::text >= '2026-09-18'
),
r AS (
  SELECT
    p.id, p.is_premium,
    split_part(p.rezultati_sakt, '-', 1)::int                         AS s1,
    split_part(p.rezultati_sakt, '-', 2)::int                         AS s2,
    split_part(replace(p.rezultati, ' ', ''), '-', 1)::int            AS r1,
    split_part(replace(p.rezultati, ' ', ''), '-', 2)::int            AS r2,
    EXISTS (SELECT 1 FROM pf
            WHERE pf.ndeshja = p.ndeshja AND pf.data = p.data::text)   AS ka_hash
  FROM predictions p
  WHERE p.data::text >= '2026-09-18'
    AND p.rezultati_sakt ~ '^[0-9]+-[0-9]+$'
    AND replace(p.rezultati, ' ', '') ~ '^[0-9]+-[0-9]+$'
    AND p.statusi IN ('FT', 'AET', 'PEN', 'AWD', 'WO')
    AND COALESCE(p.training_data->>'build', '') LIKE '2026-09-1%'
),
b AS (
  SELECT
    is_premium, ka_hash,
    CASE WHEN s1 = r1 AND s2 = r2 THEN 1 ELSE 0 END                   AS skor_ok,
    CASE WHEN sign(s1 - s2) = sign(r1 - r2) THEN 1 ELSE 0 END          AS drejt_ok
  FROM r
)
SELECT
  count(*)                                                            AS ndeshje_gjithsej,
  count(*) FILTER (WHERE ka_hash)                                     AS ppm_n,
  sum(skor_ok) FILTER (WHERE ka_hash)                                 AS ppm_skor,
  count(*) FILTER (WHERE NOT ka_hash)                                 AS jashte_n,
  sum(skor_ok) FILTER (WHERE NOT ka_hash)                             AS jashte_skor,
  round(100.0 * sum(skor_ok) FILTER (WHERE ka_hash)
        / NULLIF(count(*) FILTER (WHERE ka_hash), 0), 1)              AS ppm_skor_pct,
  round(100.0 * sum(skor_ok) FILTER (WHERE NOT ka_hash)
        / NULLIF(count(*) FILTER (WHERE NOT ka_hash), 0), 1)          AS jashte_skor_pct,
  sum(drejt_ok) FILTER (WHERE ka_hash)                                AS ppm_drejt,
  sum(drejt_ok) FILTER (WHERE NOT ka_hash)                            AS jashte_drejt,
  round(100.0 * sum(drejt_ok) FILTER (WHERE ka_hash)
        / NULLIF(count(*) FILTER (WHERE ka_hash), 0), 1)              AS ppm_drejt_pct,
  round(100.0 * sum(drejt_ok) FILTER (WHERE NOT ka_hash)
        / NULLIF(count(*) FILTER (WHERE NOT ka_hash), 0), 1)          AS jashte_drejt_pct,
  -- Ndotja e grupit te vjeter: sa premium s'kane hash, dhe anasjelltas.
  count(*) FILTER (WHERE is_premium AND NOT ka_hash)                  AS premium_pa_hash,
  count(*) FILTER (WHERE ka_hash AND NOT COALESCE(is_premium, false)) AS hash_pa_premium
FROM b;
