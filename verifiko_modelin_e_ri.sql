-- ══════════════════════════════════════════════════════════════════════════
-- A JANE GJENERUAR ME MODELIN E RI? (15 dhe 16 shtator)
-- ══════════════════════════════════════════════════════════════════════════
-- Nuk e ruajme ende etiketen e BUILD-it ne parashikime, ndaj e zbulojme nga
-- SJELLJA. Moduli i ri e merr drejtimin nga TREGU i devigosur me prag 0.12.
-- Nese modeli i ri i ka gjeneruar, atehere pothuajse cdo ndeshje me favorit
-- te qarte ne treg duhet ta kete skorin ne ate drejtim.
--
-- ⚠️ SA SHKELJE JANE NORMALE: dy rregulla veprojne PAS modulit dhe mund ta
--    ndryshojne skorin ligjerisht:
--      • draw→LEAN (PRAG_LEAN=0.30) — kur skori del barazim dhe xG ka anim
--      • mbrojtja "mos zbraz listen" — kur asnje nga top-5 s'e ploteson drejtimin
--    Pra prit 90-100%, jo domosdoshmerisht 100%. Nen ~85% = modeli i vjeter.

-- ── 1) PERMBLEDHJE PER DITE ──────────────────────────────────────────────
WITH b AS (
  SELECT
    p.data, p.ndeshja, p.ora, p.liga_emri, p.rezultati_sakt,
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


-- ── 3) ZINXHIRI I PLOTE PER TRI NDESHJET NE PYETJE ──────────────────────
-- Pse doli pikerisht ai skor: xG -> totali i pritur -> skori i zgjedhur.
SELECT
  p.data, p.ora, p.ndeshja, p.liga_emri,
  p.koef_1, p.koef_x, p.koef_2,
  -- tregu i devigosur
  round(((1/p.koef_1::numeric) / ((1/p.koef_1::numeric)+(1/p.koef_x::numeric)+(1/p.koef_2::numeric)))::numeric, 3) AS p1_treg,
  round(((1/p.koef_x::numeric) / ((1/p.koef_1::numeric)+(1/p.koef_x::numeric)+(1/p.koef_2::numeric)))::numeric, 3) AS px_treg,
  round(((1/p.koef_2::numeric) / ((1/p.koef_1::numeric)+(1/p.koef_x::numeric)+(1/p.koef_2::numeric)))::numeric, 3) AS p2_treg,
  -- xG-ja qe prodhoi skorin
  (p.training_data->>'xg_1')::numeric                                   AS xg_1,
  (p.training_data->>'xg_2')::numeric                                   AS xg_2,
  round(((p.training_data->>'xg_1')::numeric + (p.training_data->>'xg_2')::numeric), 2) AS totali_i_pritur,
  p.training_data->>'burimi_xg'                                         AS burimi_xg,
  -- 1X2 i modelit pas blendit me tregun
  p.training_data->'prob_1x2_mc'                                        AS prob_1x2_pas_blendit,
  -- outputi
  p.rezultati_sakt                                                      AS skori_yne,
  p.koef_rez_sakt                                                       AS koefi_i_skorit,
  p.rezultati                                                           AS reali,
  (split_part(p.rezultati_sakt,'-',1)::int + split_part(p.rezultati_sakt,'-',2)::int) AS totali_yne,
  p.besueshmeria
FROM parashikimet p
WHERE p.ndeshja ILIKE '%Rayo Vallecano%'
   OR p.ndeshja ILIKE '%Instituto%'
   OR p.ndeshja ILIKE '%Daejeon%'
ORDER BY p.data DESC, p.ora;


-- ── 4) A KA FARE PARASHIKIME PER 16 SHTATORIN ───────────────────────────
SELECT
  data,
  count(*)                                              AS gjithsej,
  count(*) FILTER (WHERE rezultati_sakt IS NOT NULL)    AS me_skor,
  count(*) FILTER (WHERE tregjet IS NOT NULL)           AS me_tregje,
  count(*) FILTER (WHERE is_premium)                    AS premium,
  min(ora) AS e_para, max(ora) AS e_fundit
FROM parashikimet
WHERE data IN ('2026-09-14', '2026-09-15', '2026-09-16')
GROUP BY data
ORDER BY data;
