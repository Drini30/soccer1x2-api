-- ==================== PYETJA 0 — SKEMA ====================
-- Ekzekutoje TE PARIN. Testet me poshte mbeshteten te kolonat qe kthen ky.
-- Nese ndonje kolone qe perdor une nuk eshte ne liste, ma thuaj dhe e rregulloj.
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'historik_trajnimi'
ORDER BY ordinal_position;


-- ==================== PYETJA 1 — H6: SINJALI I TOTALIT ====================
-- Pyetja: cfare parashikon mbetjen e totalit qe as tregu nuk e kap?
--
-- Metoda: totali i tregut merret nga kuotat Over/Under 2.5 (pas heqjes se marzhit),
-- regresohet totali real mbi te, dhe mbetja korrelohet me pese kandidate.
-- Nese ndonje kandidat korrelon me mbetjen, ai mban informacion QE TREGU S'E KA.
--
-- ⚠️ ME ~40,000 RRESHTA, DOMETHENIA STATISTIKORE ESHTE E PAVLEFSHME SI KRITER.
--    |r| > 0.010 del "p < 0.05" dhe s'do te thote asgje. Lexo VETEM madhesine:
--        |r| < 0.05  -> pa vlere praktike (r2 nen 0.25%)
--        |r| 0.05-0.10 -> i dobet, ndoshta i perdorshem si modifikues
--        |r| > 0.10  -> gjetje reale, vlen zbatimi
WITH b AS (
    SELECT (gola_home + gola_away)::float8                                   AS tot_real,
           (1.0/ou25_over) / ((1.0/ou25_over) + (1.0/ou25_under))            AS p_over,
           (home_volatility + away_volatility)::float8                       AS vol_shuma,
           abs(home_volatility - away_volatility)::float8                    AS vol_hendeku,
           LEAST(home_rest_days, away_rest_days)::float8                     AS pushimi_min,
           tipi_ndeshjes::float8                                             AS tipi,
           ((1.0/odd_home) + (1.0/odd_draw) + (1.0/odd_away))::float8        AS marzhi_1x2,
           ((1.0/ou25_over) + (1.0/ou25_under))::float8                      AS marzhi_ou
    FROM historik_trajnimi
    WHERE gola_home IS NOT NULL AND gola_away IS NOT NULL
      AND ou25_over > 1 AND ou25_under > 1
      AND odd_home  > 1 AND odd_draw   > 1 AND odd_away > 1
      AND home_volatility IS NOT NULL AND away_volatility IS NOT NULL
      AND home_rest_days  IS NOT NULL AND away_rest_days  IS NOT NULL
),
koef AS (
    SELECT regr_slope(tot_real, p_over)     AS bb,
           regr_intercept(tot_real, p_over) AS aa,
           regr_r2(tot_real, p_over)        AS r2_tregu
    FROM b
),
m AS (
    SELECT b.*, (b.tot_real - (k.aa + k.bb * b.p_over)) AS mbetja, k.r2_tregu
    FROM b CROSS JOIN koef k
)
SELECT count(*)                                             AS n,
       round(avg(tot_real)::numeric, 3)                     AS totali_mes,
       round(max(r2_tregu)::numeric, 4)                     AS r2_i_tregut,
       round(corr(mbetja, vol_shuma)::numeric, 4)           AS korr_volatiliteti,
       round(corr(mbetja, vol_hendeku)::numeric, 4)         AS korr_vol_hendeku,
       round(corr(mbetja, pushimi_min)::numeric, 4)         AS korr_pushimi,
       round(corr(mbetja, tipi)::numeric, 4)                AS korr_tipi,
       round(corr(mbetja, marzhi_1x2)::numeric, 4)          AS korr_marzhi_1x2,
       round(corr(mbetja, marzhi_ou)::numeric, 4)           AS korr_marzhi_ou
FROM m;


-- ==================== PYETJA 2 — H6b: A ESHTE MONOTON? ====================
-- Korrelacioni kap vetem lidhje lineare. Nese ndonje kandidat del > 0.05 te
-- pyetja 1, kjo tregon a eshte monoton apo thjesht zhurme e strukturuar.
-- Zevendeso `vol_shuma` me kandidatin fitues nese eshte tjeter.
WITH b AS (
    SELECT (gola_home + gola_away)::float8                        AS tot_real,
           (1.0/ou25_over) / ((1.0/ou25_over) + (1.0/ou25_under)) AS p_over,
           (home_volatility + away_volatility)::float8            AS kandidati
    FROM historik_trajnimi
    WHERE gola_home IS NOT NULL AND gola_away IS NOT NULL
      AND ou25_over > 1 AND ou25_under > 1
      AND home_volatility IS NOT NULL AND away_volatility IS NOT NULL
),
koef AS (SELECT regr_slope(tot_real, p_over) AS bb, regr_intercept(tot_real, p_over) AS aa FROM b),
m AS (
    SELECT b.*, (b.tot_real - (k.aa + k.bb * b.p_over)) AS mbetja,
           ntile(5) OVER (ORDER BY b.kandidati) AS brezi
    FROM b CROSS JOIN koef k
)
SELECT brezi,
       count(*)                              AS n,
       round(avg(kandidati)::numeric, 3)     AS kandidati_mes,
       round(avg(tot_real)::numeric, 3)      AS totali_real,
       round(avg(mbetja)::numeric, 4)        AS mbetja_mes,
       round((stddev_samp(mbetja)/sqrt(count(*)))::numeric, 4) AS se
FROM m
GROUP BY brezi
ORDER BY brezi;


-- ==================== PYETJA 3 — H1: BREZI I KUOTAVE ====================
-- Pyetja jote: "jo cdo ndeshje me koef 1.2 del 2:0".
-- Kjo tregon shperndarjen REALE te skoreve brenda brezave te ngushte kuotash.
-- Kolona `pjesa_e_modes` eshte pergjigjja: sa perqind e ndeshjeve te atij brezi
-- e kane skorin me te shpeshte. Nese eshte 12-15%, atehere asnje skor i vetem
-- s'e perfaqeson brezin — dhe publikimi i te njejtit skor per gjithe brezin eshte
-- i pashmangshem si mode, por i varfer si informacion.
WITH b AS (
    SELECT odd_home,
           (gola_home || '-' || gola_away) AS skori,
           (gola_home + gola_away)         AS totali
    FROM historik_trajnimi
    WHERE gola_home IS NOT NULL AND gola_away IS NOT NULL
      AND odd_home > 1 AND odd_home < 3.0
      AND gola_home <= 6 AND gola_away <= 6
),
z AS (
    SELECT CASE WHEN odd_home < 1.25 THEN 'a) 1.00-1.25'
                WHEN odd_home < 1.50 THEN 'b) 1.25-1.50'
                WHEN odd_home < 1.80 THEN 'c) 1.50-1.80'
                WHEN odd_home < 2.20 THEN 'd) 1.80-2.20'
                ELSE                      'e) 2.20-3.00' END AS brezi,
           skori, totali
    FROM b
),
agg AS (
    SELECT brezi, skori, count(*) AS n,
           row_number() OVER (PARTITION BY brezi ORDER BY count(*) DESC) AS rn,
           sum(count(*)) OVER (PARTITION BY brezi) AS n_brezi
    FROM z GROUP BY brezi, skori
)
SELECT brezi,
       max(n_brezi)                                                  AS ndeshje_ne_brez,
       string_agg(skori || ' ' || round(100.0*n/n_brezi, 1) || '%',
                  '  |  ' ORDER BY n DESC) FILTER (WHERE rn <= 6)    AS gjashte_skoret_kryesore,
       round(100.0 * max(n) FILTER (WHERE rn = 1) / max(n_brezi), 1) AS pjesa_e_modes
FROM agg
GROUP BY brezi
ORDER BY brezi;


-- ==================== PYETJA 4 — H1b: TOTALI SIPAS BREZIT ====================
-- E njejta ndarje, por mbi TOTALIN e golave — ku modeli yne eshte i ngushte.
-- Nese brezi 1.00-1.25 ka totale nga 0 deri 6 me shperndarje te gjere, atehere
-- "koef i ulet -> 2:0" eshte thjeshtezim qe humbet informacion.
WITH b AS (
    SELECT odd_home, (gola_home + gola_away) AS totali
    FROM historik_trajnimi
    WHERE gola_home IS NOT NULL AND gola_away IS NOT NULL
      AND odd_home > 1 AND odd_home < 3.0
),
z AS (
    SELECT CASE WHEN odd_home < 1.25 THEN 'a) 1.00-1.25'
                WHEN odd_home < 1.50 THEN 'b) 1.25-1.50'
                WHEN odd_home < 1.80 THEN 'c) 1.50-1.80'
                WHEN odd_home < 2.20 THEN 'd) 1.80-2.20'
                ELSE                      'e) 2.20-3.00' END AS brezi,
           totali
    FROM b
)
SELECT brezi,
       count(*)                                                    AS n,
       round(avg(totali)::numeric, 2)                              AS totali_mes,
       round(stddev_samp(totali)::numeric, 2)                      AS sd,
       round(100.0*count(*) FILTER (WHERE totali <= 1)/count(*), 1) AS pct_0_1,
       round(100.0*count(*) FILTER (WHERE totali  = 2)/count(*), 1) AS pct_2,
       round(100.0*count(*) FILTER (WHERE totali  = 3)/count(*), 1) AS pct_3,
       round(100.0*count(*) FILTER (WHERE totali  = 4)/count(*), 1) AS pct_4,
       round(100.0*count(*) FILTER (WHERE totali >= 5)/count(*), 1) AS pct_5plus
FROM z
GROUP BY brezi
ORDER BY brezi;
