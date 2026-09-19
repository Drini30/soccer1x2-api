-- ========================================================================
-- ANALIZA E FILTRIT — pse doli keq nje dite
-- ========================================================================
-- Ekzekutoje VETEM kete skedar (Supabase kthen vetem pyetjen e fundit).
--
-- Merr te gjitha ndeshjet e mbaruara te nje dite qe kane best_bet, vlereson
-- nese tregu i zgjedhur goditi, dhe e zberthen diten ne pesë kende:
--
--   0 TOTALI              sa u zgjodhen, sa goditen, sa premtoheshin
--   1 FILTRI              premium kundrejt jo-premium, value kundrejt jo
--   2 SIPAS TREGUT        cili treg e uli diten
--   3 SIPAS BESUESHMERISE a e ndan besueshmeria goditjen nga humbja
--   4 SIPAS KOEFICIENTIT  a jane humbjet te perqendruara ne nje brez kuotash
--   5 NDESHJET            nje per nje, per ta pare me sy
--
-- Kolona vendimtare eshte DALLIMI = e goditur% − e premtuar%. Nese filtri
-- premton 75% dhe realizon 40%, problemi eshte kalibrimi, jo fati. Nese
-- premium goditi ME PAK se jo-premium, filtri po zgjedh bastet e keqija —
-- pikerisht patologjia qe u gjet nje here te filtri i vleres.
-- ========================================================================

WITH parametrat AS (
  -- ▼▼ NDRYSHO VETEM KETU ▼▼
  SELECT DATE '2026-09-19' AS dita
),
baza AS (
  SELECT
    p.ora, p.ndeshja, p.liga_emri,
    p.best_bet->>'tregu'                                   AS tregu,
    NULLIF(p.best_bet->>'koef', '')::numeric               AS koef,
    NULLIF(p.best_bet->>'prob', '')::numeric               AS prob,
    NULLIF(regexp_replace(p.besueshmeria::text, '[^0-9.]', '', 'g'), '')::numeric AS besu,
    COALESCE(p.is_premium, false)                          AS premium,
    COALESCE(p.is_value,   false)                          AS value,
    p.rezultati,
    trim(split_part(p.rezultati, '-', 1))::int             AS r1,
    trim(split_part(p.rezultati, '-', 2))::int             AS r2
  FROM predictions p, parametrat par
  WHERE p.data::date = par.dita
    AND p.best_bet IS NOT NULL
    AND p.best_bet->>'tregu' IS NOT NULL
    -- Rezultati real ruhet si '0 - 0' (me hapesira)
    AND p.rezultati ~ '^\s*[0-9]+\s*-\s*[0-9]+\s*$'
    -- Vetem ndeshjet e luajtura: nje ndeshje NS mban '0 - 0' si vend-mbajtese
    AND p.statusi IN ('FT', 'AET', 'PEN', 'AWD', 'WO')
),
v AS (
  SELECT *,
    (r1 + r2) AS tot,
    CASE tregu
      WHEN '1'          THEN (r1 >  r2)
      WHEN 'X'          THEN (r1 =  r2)
      WHEN '2'          THEN (r1 <  r2)
      WHEN '1X'         THEN (r1 >= r2)
      WHEN 'X2'         THEN (r1 <= r2)
      WHEN '12'         THEN (r1 <> r2)
      WHEN 'Over 1.5'   THEN (r1 + r2) >= 2
      WHEN 'Under 1.5'  THEN (r1 + r2) <= 1
      WHEN 'Over 2.5'   THEN (r1 + r2) >= 3
      WHEN 'Under 2.5'  THEN (r1 + r2) <= 2
      WHEN 'Over 3.5'   THEN (r1 + r2) >= 4
      WHEN 'Under 3.5'  THEN (r1 + r2) <= 3
      WHEN 'GG'         THEN (r1 > 0 AND r2 > 0)
      WHEN 'NG'         THEN (r1 = 0 OR  r2 = 0)
      ELSE NULL                                  -- treg i panjohur: nuk gjykohet
    END AS goditi
  FROM baza
),
m AS (   -- nje rresht per ndeshje, me goditjen si 1/0
  SELECT *, CASE WHEN goditi THEN 1 ELSE 0 END AS g
  FROM v WHERE goditi IS NOT NULL
),
perm AS (
  SELECT '0 · TOTALI'::text AS seksioni, 'te gjitha'::text AS grupi,
         count(*)::int AS ndeshje, sum(g)::int AS goditje,
         round(100.0*sum(g)/count(*), 1) AS e_goditur,
         round(100.0*avg(prob), 1)       AS e_premtuar,
         round(avg(koef), 2)             AS koef_mes,
         round(avg(besu), 1)             AS besu_mes
  FROM m
  UNION ALL
  SELECT '1 · FILTRI', CASE WHEN premium THEN 'premium' ELSE 'jo premium' END,
         count(*)::int, sum(g)::int, round(100.0*sum(g)/count(*), 1),
         round(100.0*avg(prob), 1), round(avg(koef), 2), round(avg(besu), 1)
  FROM m GROUP BY premium
  UNION ALL
  SELECT '1 · FILTRI', CASE WHEN value THEN 'value' ELSE 'jo value' END,
         count(*)::int, sum(g)::int, round(100.0*sum(g)/count(*), 1),
         round(100.0*avg(prob), 1), round(avg(koef), 2), round(avg(besu), 1)
  FROM m GROUP BY value
  UNION ALL
  SELECT '2 · SIPAS TREGUT', tregu,
         count(*)::int, sum(g)::int, round(100.0*sum(g)/count(*), 1),
         round(100.0*avg(prob), 1), round(avg(koef), 2), round(avg(besu), 1)
  FROM m GROUP BY tregu
  UNION ALL
  SELECT '3 · SIPAS BESUESHMERISE',
         CASE WHEN besu IS NULL THEN 'pa besueshmeri'
              WHEN besu >= 85 THEN 'd) 85+'
              WHEN besu >= 75 THEN 'c) 75-85'
              WHEN besu >= 65 THEN 'b) 65-75'
              ELSE                 'a) nen 65' END,
         count(*)::int, sum(g)::int, round(100.0*sum(g)/count(*), 1),
         round(100.0*avg(prob), 1), round(avg(koef), 2), round(avg(besu), 1)
  FROM m
  GROUP BY 2
  UNION ALL
  SELECT '4 · SIPAS KOEFICIENTIT',
         CASE WHEN koef IS NULL THEN 'pa koef'
              WHEN koef >= 2.50 THEN 'd) 2.50+'
              WHEN koef >= 1.90 THEN 'c) 1.90-2.50'
              WHEN koef >= 1.50 THEN 'b) 1.50-1.90'
              ELSE                   'a) nen 1.50' END,
         count(*)::int, sum(g)::int, round(100.0*sum(g)/count(*), 1),
         round(100.0*avg(prob), 1), round(avg(koef), 2), round(avg(besu), 1)
  FROM m
  GROUP BY 2
  UNION ALL
  SELECT '5 · NDESHJET',
         COALESCE(ora, '--') || '  ' || ndeshja || '  →  ' || tregu
           || CASE WHEN premium THEN '  [premium]' ELSE '' END
           || '  (' || rezultati || ')',
         1, g, (g * 100)::numeric,
         round(100.0*prob, 1), koef, besu
  FROM m
)
SELECT
  seksioni,
  grupi,
  ndeshje,
  goditje,
  e_goditur,
  e_premtuar,
  round(e_goditur - e_premtuar, 1) AS dallimi,
  koef_mes,
  besu_mes
FROM perm
ORDER BY seksioni,
         CASE WHEN seksioni = '5 · NDESHJET' THEN goditje ELSE -ndeshje END,
         grupi;

-- LEXIMI:
--   • DALLIMI shume negativ te '0 · TOTALI' → dita nuk ishte thjesht fat i keq:
--     probabilitetet e publikuara nuk mbahen. Shih PLATT_A/PLATT_B.
--   • Nese 'premium' ka e_goditur ME TE ULET se 'jo premium', filtri po zgjedh
--     me keq se rastesia — atehere problemi eshte kriteri i zgjedhjes, jo modeli.
--   • Nese nje treg i vetem (p.sh. Over 2.5) mban shumicen e ndeshjeve dhe
--     goditi rreth 50%, zgjedhja s'po shton informacion: eshte maksimumi i
--     zhurmes. Kjo eshte arsyeja e EDGE_MIN.
--   • Nje dite ka pak ndeshje: 4 nga 10 mund te jete fat i keq. Perqindjet
--     lexoji si tregues, jo si prove — provoje te njejten pyetje per 5-7 dite.
