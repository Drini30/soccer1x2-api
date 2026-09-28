-- ========================================================================
-- PRAGU I AFTESISE DHE FALLBACK-U — testi vendimtar
-- ========================================================================
-- _best_bet_value zgjedh tregun me VALUE me te larte MIDIS atyre qe kane
-- aftesi >= EDGE_MIN (0.04) mbi normen baze te atij tregu. Kur ASNJE kandidat
-- s'e kalon pragun, bie te kandidati me aftesine me te larte — edhe nese ajo
-- eshte thuajse zero (soccer_api.py, fundi i _best_bet_value).
--
-- Kjo pyetje ndan zgjedhjet ne dy grupe dhe i mat vecmas:
--   • KALOI PRAGUN  — aftesia >= 4pp: zgjedhje me informacion
--   • FALLBACK      — aftesia < 4pp: maksimumi i zhurmes, sipas kodit
--
-- Nese fallback-u godet dukshem me pak, ai eshte vrima — jo modeli, jo dita.
-- ========================================================================

WITH parametrat AS (
  -- ▼▼ NDRYSHO KETU ▼▼  (nje dite: vendos te njejten date te dyja)
  SELECT DATE '2026-09-19' AS nga, DATE '2026-09-19' AS deri, 0.04::numeric AS edge_min
),
normat (tregu, baza) AS (          -- NORMA_BAZE_DEFAULT nga soccer_api.py
  VALUES ('1', 0.45), ('X', 0.25), ('2', 0.30),
         ('1X', 0.70), ('X2', 0.55), ('12', 0.75),
         ('GG', 0.50), ('NG', 0.50),
         ('Over 1.5', 0.74), ('Under 1.5', 0.26),
         ('Over 2.5', 0.49), ('Under 2.5', 0.51),
         ('Over 3.5', 0.25), ('Under 3.5', 0.75)
),
baza AS (
  SELECT
    p.data::date AS data, p.ora, p.ndeshja,
    p.best_bet->>'tregu'                       AS tregu,
    NULLIF(p.best_bet->>'prob', '')::numeric   AS prob,
    NULLIF(p.best_bet->>'koef', '')::numeric   AS koef,
    COALESCE(p.is_premium, false)              AS premium,
    p.rezultati,
    trim(split_part(p.rezultati, '-', 1))::int AS r1,
    trim(split_part(p.rezultati, '-', 2))::int AS r2
  FROM predictions p, parametrat par
  WHERE p.data::date BETWEEN par.nga AND par.deri
    AND p.best_bet->>'tregu' IS NOT NULL
    AND p.rezultati ~ '^\s*[0-9]+\s*-\s*[0-9]+\s*$'
    AND p.statusi IN ('FT', 'AET', 'PEN', 'AWD', 'WO')
),
v AS (
  SELECT b.*, n.baza,
    (b.prob - n.baza) AS aftesia,
    CASE b.tregu
      WHEN '1' THEN (r1 > r2)   WHEN 'X' THEN (r1 = r2)   WHEN '2' THEN (r1 < r2)
      WHEN '1X' THEN (r1 >= r2) WHEN 'X2' THEN (r1 <= r2) WHEN '12' THEN (r1 <> r2)
      WHEN 'Over 1.5'  THEN (r1+r2) >= 2  WHEN 'Under 1.5' THEN (r1+r2) <= 1
      WHEN 'Over 2.5'  THEN (r1+r2) >= 3  WHEN 'Under 2.5' THEN (r1+r2) <= 2
      WHEN 'Over 3.5'  THEN (r1+r2) >= 4  WHEN 'Under 3.5' THEN (r1+r2) <= 3
      WHEN 'GG' THEN (r1 > 0 AND r2 > 0)  WHEN 'NG' THEN (r1 = 0 OR r2 = 0)
      ELSE NULL END AS goditi
  FROM baza b JOIN normat n ON n.tregu = b.tregu
),
m AS (
  SELECT v.*, CASE WHEN goditi THEN 1 ELSE 0 END AS g,
         (v.aftesia >= (SELECT edge_min FROM parametrat)) AS kaloi
  FROM v WHERE goditi IS NOT NULL
),
perm AS (
  SELECT '1 · PRAGU'::text AS seksioni,
         CASE WHEN kaloi THEN 'a) KALOI pragun (aftesi >= 4pp)'
                         ELSE 'b) FALLBACK (aftesi < 4pp)' END AS grupi,
         count(*)::int AS ndeshje, sum(g)::int AS goditje,
         round(100.0*sum(g)/count(*), 1)  AS e_goditur,
         round(100.0*avg(prob), 1)        AS e_premtuar,
         round(100.0*avg(aftesia), 1)     AS aftesia_pp,
         round(avg(koef), 2)              AS koef_mes
  FROM m GROUP BY kaloi
  UNION ALL
  SELECT '2 · PRAGU × PREMIUM',
         (CASE WHEN kaloi THEN 'kaloi' ELSE 'fallback' END) ||
         (CASE WHEN premium THEN ' · premium' ELSE ' · jo premium' END),
         count(*)::int, sum(g)::int, round(100.0*sum(g)/count(*), 1),
         round(100.0*avg(prob), 1), round(100.0*avg(aftesia), 1), round(avg(koef), 2)
  FROM m GROUP BY kaloi, premium
  UNION ALL
  SELECT '3 · SIPAS TREGUT',
         tregu || CASE WHEN bool_and(kaloi) THEN '  (kalon)'
                       WHEN bool_or(kaloi)  THEN '  (i perzier)'
                       ELSE '  ← fallback' END,
         count(*)::int, sum(g)::int, round(100.0*sum(g)/count(*), 1),
         round(100.0*avg(prob), 1), round(100.0*avg(aftesia), 1), round(avg(koef), 2)
  FROM m GROUP BY tregu
  UNION ALL
  SELECT '4 · SIPAS DITES', data::text,
         count(*)::int, sum(g)::int, round(100.0*sum(g)/count(*), 1),
         round(100.0*avg(prob), 1), round(100.0*avg(aftesia), 1), round(avg(koef), 2)
  FROM m GROUP BY data
)
SELECT seksioni, grupi, ndeshje, goditje, e_goditur, e_premtuar,
       round(e_goditur - e_premtuar, 1) AS dallimi,
       aftesia_pp, koef_mes
FROM perm
ORDER BY seksioni, ndeshje DESC, grupi;

-- LEXIMI:
--   • Nese 'FALLBACK' ka e_goditur dukshem me te ulet se 'KALOI pragun',
--     atehere zgjedhja pa aftesi eshte vrima. Zgjidhja nuk eshte ta ulesh
--     pragun, por te mos zgjedhesh fare kur askush s'e kalon.
--   • Kolona 'aftesia_pp' te thote sa larg normes baze ishte mesatarja e atij
--     grupi. Nje grup me aftesi ~1pp qe premton 52% eshte, sipas perkufizimit,
--     zhurme e etiketuar si siguri.
--   • Perseritja per 5-7 dite eshte e domosdoshme para se te preket kodi:
--     nje dite nuk e ndan dot fatin nga struktura.
