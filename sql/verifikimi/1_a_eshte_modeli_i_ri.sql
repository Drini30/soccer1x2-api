-- ========================================================================
-- A ESHTE MODELI I RI? — permbledhje per dite
-- Ekzekutoje VETEM kete skedar. Supabase kthen vetem rezultatin e
-- pyetjes se FUNDIT kur i jep disa njeheresh — prandaj jane te ndara.
-- ========================================================================

-- ── 1) PERMBLEDHJE PER DITE ──────────────────────────────────────────────
WITH b AS (
  SELECT
    p.data, p.ndeshja, p.ora, p.liga_emri, p.rezultati_sakt,
    NULLIF(regexp_replace(p.koef_1::text, '[^0-9.]', '', 'g'), '')::numeric AS k1,
    NULLIF(regexp_replace(p.koef_x::text, '[^0-9.]', '', 'g'), '')::numeric AS kx,
    NULLIF(regexp_replace(p.koef_2::text, '[^0-9.]', '', 'g'), '')::numeric AS k2,
    split_part(p.rezultati_sakt, '-', 1)::int AS g1,
    split_part(p.rezultati_sakt, '-', 2)::int AS g2
  FROM predictions p
  WHERE p.data IN ('2026-09-15', '2026-09-16')
    AND p.rezultati_sakt ~ '^[0-9]+-[0-9]+$'
),
d AS (
  SELECT *,
    (1/k1) / ((1/k1)+(1/kx)+(1/k2)) AS p1,
    (1/kx) / ((1/k1)+(1/kx)+(1/k2)) AS px,
    (1/k2) / ((1/k1)+(1/kx)+(1/k2)) AS p2
  FROM b
  WHERE k1 > 1 AND kx > 1 AND k2 > 1
),
v AS (
  SELECT *,
    CASE WHEN p1 >= p2 AND (p1 - px) > 0.12 THEN '1'
         WHEN p2 >  p1 AND (p2 - px) > 0.12 THEN '2'
         ELSE 'X' END AS kerkon_tregu,
    CASE WHEN g1 > g2 THEN '1' WHEN g2 > g1 THEN '2' ELSE 'X' END AS jep_skori
  FROM d
)
SELECT
  data,
  count(*)                                                   AS ndeshje,
  count(*) FILTER (WHERE kerkon_tregu <> 'X')                AS me_favorit_te_qarte,
  count(*) FILTER (WHERE kerkon_tregu <> 'X'
                     AND jep_skori = kerkon_tregu)           AS respektojne,
  count(*) FILTER (WHERE kerkon_tregu <> 'X'
                     AND jep_skori <> kerkon_tregu)          AS shkelje,
  round(100.0 * count(*) FILTER (WHERE kerkon_tregu <> 'X' AND jep_skori = kerkon_tregu)
        / NULLIF(count(*) FILTER (WHERE kerkon_tregu <> 'X'), 0), 1) AS perqindja,
  count(*) FILTER (WHERE jep_skori = 'X')                    AS barazime_te_publikuara
FROM v
GROUP BY data
ORDER BY data;

-- LEXIMI:
--   perqindja 90-100%  -> modeli i RI i ka gjeneruar
--   perqindja < 85%    -> modeli i VJETER; duhet rigjenerim per ate dite
