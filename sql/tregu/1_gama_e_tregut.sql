-- ========================================================================
-- 1) GAMA E TREGUT — per cdo treg, cfare ndodhi vertet ne cdo brez kuotash
-- Ekzekutoje VETEM kete skedar.
-- ========================================================================
-- LEXIM I KUNDERT: jo "cfare parashikuam dhe a doli", po "kuota ishte X, sa
-- shpesh doli vertet". Kjo e mat TREGUN, jo ne — dhe tregon ku tregu eshte i
-- sakte dhe ku gabon. Aty ku gabon, kemi ku te fitojme.
--
-- KOLONAT:
--   n             sa ndeshje e kishin ate kuote ne ate brez
--   doli          sa here ndodhi vertet ai treg
--   e_dukshme     probabiliteti i nenkuptuar nga kuota (1/kuota) — me marzh brenda
--   nga_ne        probabiliteti qe i jepnim NE atij tregu
--   treg_gab      doli − e_dukshme. Pozitiv = tregu e NENVLERESON kete treg.
--   ne_gab        doli − nga_ne.   Pozitiv = NE e nenvleresojme.
--
-- Marzhi e ben `e_dukshme` sistematikisht me te larte se e verteta (~5%), ndaj
-- `treg_gab` pritet te jete rreth -3 deri -5pp KUDO. Ajo qe kerkojme jane brezat
-- ku ai dallim eshte SHUME me i madh ose ku nderron shenje.

WITH b AS (
  SELECT
    odds_reale AS od, tregjet_full AS tg,
    split_part(replace(rezultati_ft,' ',''),'-',1)::int AS gv,
    split_part(replace(rezultati_ft,' ',''),'-',2)::int AS gm
  FROM arkiv_rezultatesh
  WHERE odds_reale IS NOT NULL
    AND replace(rezultati_ft,' ','') ~ '^[0-9]+-[0-9]+$'
),
m AS (
  SELECT b.*, t.tregu,
    NULLIF(b.od->>t.tregu,'')::numeric        AS kuota,
    NULLIF(b.tg->>t.tregu,'')::numeric        AS prob_jona,
    CASE t.tregu
      WHEN '1'          THEN (gv >  gm)
      WHEN 'X'          THEN (gv =  gm)
      WHEN '2'          THEN (gv <  gm)
      WHEN '1X'         THEN (gv >= gm)
      WHEN 'X2'         THEN (gv <= gm)
      WHEN '12'         THEN (gv <> gm)
      WHEN 'GG'         THEN (gv > 0 AND gm > 0)
      WHEN 'NG'         THEN (gv = 0 OR  gm = 0)
      WHEN 'Over 1.5'   THEN (gv+gm > 1)
      WHEN 'Under 1.5'  THEN (gv+gm < 2)
      WHEN 'Over 2.5'   THEN (gv+gm > 2)
      WHEN 'Under 2.5'  THEN (gv+gm < 3)
      WHEN 'Over 3.5'   THEN (gv+gm > 3)
      WHEN 'Under 3.5'  THEN (gv+gm < 4)
    END AS doli
  FROM b
  CROSS JOIN LATERAL (VALUES ('1'),('X'),('2'),('GG'),('NG'),
                             ('Over 1.5'),('Under 1.5'),('Over 2.5'),
                             ('Under 2.5'),('Over 3.5'),('Under 3.5')) AS t(tregu)
),
z AS (
  SELECT *,
    CASE WHEN kuota < 1.25 THEN 'a) 1.00-1.25'
         WHEN kuota < 1.50 THEN 'b) 1.25-1.50'
         WHEN kuota < 1.75 THEN 'c) 1.50-1.75'
         WHEN kuota < 2.00 THEN 'd) 1.75-2.00'
         WHEN kuota < 2.50 THEN 'e) 2.00-2.50'
         WHEN kuota < 3.50 THEN 'f) 2.50-3.50'
         ELSE                   'g) 3.50+' END AS brezi
  FROM m WHERE kuota > 1.0 AND doli IS NOT NULL
)
SELECT
  tregu, brezi,
  count(*)                                             AS n,
  count(*) FILTER (WHERE doli)                         AS doli,
  round(100.0*count(*) FILTER (WHERE doli)/count(*),1) AS doli_pct,
  round(100.0*avg(1.0/kuota),1)                        AS e_dukshme,
  round(100.0*avg(prob_jona),1)                        AS nga_ne,
  round(100.0*count(*) FILTER (WHERE doli)/count(*) - 100.0*avg(1.0/kuota),1)  AS treg_gab,
  round(100.0*count(*) FILTER (WHERE doli)/count(*) - 100.0*avg(prob_jona),1)  AS ne_gab,
  round(avg(kuota),2)                                  AS kuota_mes
FROM z
GROUP BY tregu, brezi
HAVING count(*) >= 25
ORDER BY tregu, brezi;
