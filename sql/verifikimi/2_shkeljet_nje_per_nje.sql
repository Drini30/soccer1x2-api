-- ========================================================================
-- SHKELJET NJE PER NJE — me xG, per te dalluar draw→LEAN
-- Ekzekutoje VETEM kete skedar. Supabase kthen vetem rezultatin e
-- pyetjes se FUNDIT kur i jep disa njeheresh — prandaj jane te ndara.
-- ========================================================================

-- ── 2) SHKELJET, NJE PER NJE (ketu shihet nese jane te ligjshme) ─────────
WITH b AS (
  SELECT
    p.data, p.ndeshja, p.ora, p.liga_emri, p.rezultati_sakt, p.statusi, p.rezultati,
    (p.training_data->>'xg_1')::numeric AS xg1,
    (p.training_data->>'xg_2')::numeric AS xg2,
    NULLIF(regexp_replace(p.koef_1::text, '[^0-9.]', '', 'g'), '')::numeric AS k1,
    NULLIF(regexp_replace(p.koef_x::text, '[^0-9.]', '', 'g'), '')::numeric AS kx,
    NULLIF(regexp_replace(p.koef_2::text, '[^0-9.]', '', 'g'), '')::numeric AS k2,
    split_part(p.rezultati_sakt, '-', 1)::int AS g1,
    split_part(p.rezultati_sakt, '-', 2)::int AS g2
  FROM parashikimet p
  WHERE p.data IN ('2026-09-15', '2026-09-16')
    AND p.rezultati_sakt ~ '^[0-9]+-[0-9]+$'
),
d AS (
  SELECT *,
    (1/k1) / ((1/k1)+(1/kx)+(1/k2)) AS p1,
    (1/kx) / ((1/k1)+(1/kx)+(1/k2)) AS px,
    (1/k2) / ((1/k1)+(1/kx)+(1/k2)) AS p2
  FROM b WHERE k1 > 1 AND kx > 1 AND k2 > 1
)
SELECT
  data, ora, ndeshja, liga_emri,
  round(p1,3) AS p1, round(px,3) AS px, round(p2,3) AS p2,
  round(GREATEST(p1,p2) - px, 4)                AS diferenca,
  CASE WHEN p1 >= p2 THEN '1' ELSE '2' END      AS kerkon_tregu,
  rezultati_sakt                                 AS skori_yne,
  round(xg1,2) AS xg1, round(xg2,2) AS xg2,
  round(abs(xg1 - xg2), 2)                       AS anim_xg,
  CASE WHEN g1 = g2 AND abs(xg1 - xg2) >= 0.30
       THEN 'draw→LEAN e ndryshoi' ELSE 'shkelje e vertete' END AS shpjegimi,
  rezultati                                      AS reali
FROM d
WHERE (p1 >= p2 AND (p1 - px) > 0.12 AND g1 <= g2)
   OR (p2 >  p1 AND (p2 - px) > 0.12 AND g2 <= g1)
ORDER BY data, ora;
