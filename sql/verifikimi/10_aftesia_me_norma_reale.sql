-- ========================================================================
-- AFTESIA E VERTETE — me normat baze qe perdor VERTET kodi
-- ========================================================================
-- Verifikimi 9 perdori NORMA_BAZE_DEFAULT te ngurta. Por _norma_baze lexon
-- `model_config` nese aty ka nje celes BAZE_<treg>, dhe /api/cron/kalibro i
-- rishkruan ato nga arkivi. Ndryshimi nuk eshte kozmetik: NG ka 0.407 ne
-- model_config kundrejt 0.50 si parazgjedhje — aftesia e nje zgjedhjeje NG
-- ndryshon nga +2.9pp ne +12.2pp, pra nga "nen prag" ne "mbi prag".
--
-- Kjo pyetje i lexon normat nga model_config dhe bie te parazgjedhja vetem
-- kur celesi mungon. Keshtu aftesia e matur eshte ajo qe pa vete kodi.
--
-- NJE KUFI: _konf() lexon model_config -> env-var -> parazgjedhje. SQL-ja nuk
-- i sheh dot env-variablat e Render-it, ndaj nje norme e vendosur SI ENV-VAR
-- (pa rresht ne model_config) do te dilte ketu si "baze e parazgj.". Kolona
-- 'grupi' e seksionit 2 e shenon secilin rast, qe te mos lexohet gabim.
--
-- EDGE_MIN merret si parameter ketu (0.04); vlera e vertete lexohet nga
-- model_config.EDGE_MIN. Nese e ke ndryshuar aty, ndrysho edhe 'edge_min'.
--
-- Tri pyetje qe i pergjigjet:
--   1 · PRAGU     a i kaloi zgjedhjet pragun EDGE_MIN (me normat e verteta)
--   2 · TREGU     a e mundi secili treg normen e VET baze
--   3 · KLASA     drejtimore (1/X/2) kundrejt totaleve (O/U, GG/NG)
-- ========================================================================

WITH parametrat AS (
  -- ▼▼ NDRYSHO KETU ▼▼
  SELECT DATE '2026-09-19' AS nga, DATE '2026-09-19' AS deri, 0.04::numeric AS edge_min
),
parazgjedhjet (tregu, baza_def) AS (
  VALUES ('1', 0.45), ('X', 0.25), ('2', 0.30),
         ('1X', 0.70), ('X2', 0.55), ('12', 0.75),
         ('GG', 0.50), ('NG', 0.50),
         ('Over 1.5', 0.74), ('Under 1.5', 0.26),
         ('Over 2.5', 0.49), ('Under 2.5', 0.51),
         ('Over 3.5', 0.25), ('Under 3.5', 0.75)
),
normat AS (
  SELECT d.tregu,
         COALESCE(
           (SELECT NULLIF(regexp_replace(mc.vlera::text, '[^0-9.]', '', 'g'), '')::numeric
              FROM model_config mc
             WHERE mc.celes = 'BAZE_' || replace(replace(d.tregu, ' ', '_'), '.', '_')),
           d.baza_def) AS baza,
         (EXISTS (SELECT 1 FROM model_config mc2
                   WHERE mc2.celes = 'BAZE_' || replace(replace(d.tregu, ' ', '_'), '.', '_')))
           AS nga_config
  FROM parazgjedhjet d
),
baza AS (
  SELECT
    p.data::date AS data, p.ndeshja,
    p.best_bet->>'tregu'                       AS tregu,
    NULLIF(p.best_bet->>'prob', '')::numeric   AS prob,
    NULLIF(p.best_bet->>'koef', '')::numeric   AS koef,
    COALESCE(p.is_premium, false)              AS premium,
    trim(split_part(p.rezultati, '-', 1))::int AS r1,
    trim(split_part(p.rezultati, '-', 2))::int AS r2
  FROM predictions p, parametrat par
  WHERE p.data::date BETWEEN par.nga AND par.deri
    AND p.best_bet->>'tregu' IS NOT NULL
    AND p.rezultati ~ '^\s*[0-9]+\s*-\s*[0-9]+\s*$'
    AND p.statusi IN ('FT', 'AET', 'PEN', 'AWD', 'WO')
),
v AS (
  SELECT b.*, n.baza, n.nga_config,
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
         CASE WHEN kaloi THEN 'a) kaloi EDGE_MIN' ELSE 'b) nen EDGE_MIN' END AS grupi,
         count(*)::int AS ndeshje, sum(g)::int AS goditje,
         round(100.0*sum(g)/count(*), 1) AS e_goditur,
         round(100.0*avg(prob), 1)       AS e_premtuar,
         round(100.0*avg(baza), 1)       AS baza_mes,
         round(100.0*avg(aftesia), 1)    AS aftesia_pp
  FROM m GROUP BY kaloi
  UNION ALL
  SELECT '2 · TREGU',
         tregu || CASE WHEN bool_and(nga_config) THEN '' ELSE '  (baze e parazgj.)' END,
         count(*)::int, sum(g)::int, round(100.0*sum(g)/count(*), 1),
         round(100.0*avg(prob), 1), round(100.0*avg(baza), 1), round(100.0*avg(aftesia), 1)
  FROM m GROUP BY tregu
  UNION ALL
  SELECT '3 · KLASA',
         CASE WHEN tregu IN ('1','X','2','1X','X2','12') THEN 'drejtimore (1/X/2)'
              ELSE 'totale (O/U, GG/NG)' END,
         count(*)::int, sum(g)::int, round(100.0*sum(g)/count(*), 1),
         round(100.0*avg(prob), 1), round(100.0*avg(baza), 1), round(100.0*avg(aftesia), 1)
  FROM m GROUP BY 2
  UNION ALL
  SELECT '4 · SIPAS DITES', data::text,
         count(*)::int, sum(g)::int, round(100.0*sum(g)/count(*), 1),
         round(100.0*avg(prob), 1), round(100.0*avg(baza), 1), round(100.0*avg(aftesia), 1)
  FROM m GROUP BY data
)
SELECT seksioni, grupi, ndeshje, goditje,
       e_goditur, e_premtuar, baza_mes,
       round(e_goditur - e_premtuar, 1) AS ndaj_premtimit,
       round(e_goditur - baza_mes, 1)   AS ndaj_bazes,
       aftesia_pp
FROM perm
ORDER BY seksioni, ndeshje DESC, grupi;

-- LEXIMI:
--   • 'ndaj_bazes' eshte matja e vetme e aftesise reale: sa me shume goditi
--     modeli se sa do te godiste dikush qe luan ate treg verberisht.
--     Pozitive = ka aftesi. Zero = zgjedhja nuk shton asgje.
--   • 'ndaj_premtimit' eshte kalibrimi: sa i mban modeli fjalet e veta.
--     Mund te jete negativ edhe kur aftesia eshte pozitive — do te thote
--     "ka aftesi, por e mbivleresoi".
--   • Nje treg qe del nen normen e VET baze eshte me keq se zgjedhja e rastit:
--     ai treg duhet hequr nga TREGJET_KANDIDATE ose ri-kalibruar vecmas.
