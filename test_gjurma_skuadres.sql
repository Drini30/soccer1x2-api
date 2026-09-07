-- ==================== PYETJA 1 — A KEMBENGUL TOTALI I NJE SKUADRE? ====================
-- Pyetja: nese nje skuader ka prodhuar ndeshje me shume gola se sa priste tregu
-- ne ndeshjet e saj te meparshme, a ndodh e njejta gje edhe ne ndeshjen tjeter?
--
-- Baza eshte totali i tregut nga kuotat O/U — pra cdo gje qe tregu e di eshte
-- hequr. Ajo qe mbetet eshte informacion QE TREGU S'E KA.
--
-- `mbetja_para` eshte mesatarja e mbetjeve te ekipit NE NDESHJET E MEPARSHME te
-- atij sezoni — kurre e ndeshjes aktuale. Pra s'ka rrjedhje informacioni.
--
-- LEXIMI (n ~ 80,000 rreshta ekip-ndeshje, ndaj domethenia s'eshte kriter):
--     |korr| < 0.03  -> zhurme, hipoteza vdes
--     |korr| 0.03-0.06 -> i dobet; pesha e perzierjes do te ishte nen 0.10
--     |korr| > 0.06  -> gjurme reale, vlen te ndertohet
-- `pjerresia` te thote SA duhet te jete pesha nese sinjali ekziston.
WITH b AS (
    SELECT home_team_id, away_team_id, sezoni, data_ndeshjes,
           (gola_home + gola_away)::float8                        AS tot,
           (1.0/ou25_over) / ((1.0/ou25_over) + (1.0/ou25_under))  AS p_over
    FROM historik_trajnimi
    WHERE gola_home IS NOT NULL AND gola_away IS NOT NULL
      AND ou25_over > 1 AND ou25_under > 1
      AND home_team_id IS NOT NULL AND away_team_id IS NOT NULL
      AND sezoni IS NOT NULL AND data_ndeshjes IS NOT NULL
),
koef AS (
    SELECT regr_slope(tot, p_over) AS bb, regr_intercept(tot, p_over) AS aa FROM b
),
m AS (
    SELECT b.*, (b.tot - (k.aa + k.bb * b.p_over)) AS mbetja
    FROM b CROSS JOIN koef k
),
-- Cdo ndeshje jep DY rreshta: nje per vendasin, nje per mysafirin.
e AS (
    SELECT home_team_id AS ekipi, sezoni, data_ndeshjes, mbetja FROM m
    UNION ALL
    SELECT away_team_id AS ekipi, sezoni, data_ndeshjes, mbetja FROM m
),
w AS (
    SELECT ekipi, sezoni, data_ndeshjes, mbetja,
           avg(mbetja) OVER (PARTITION BY ekipi, sezoni ORDER BY data_ndeshjes
                             ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS mbetja_para,
           count(*)   OVER (PARTITION BY ekipi, sezoni ORDER BY data_ndeshjes
                            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS n_para
    FROM e
)
SELECT count(*)                                                       AS n,
       round(avg(n_para)::numeric, 1)                                 AS ndeshje_para_mes,
       round(corr(mbetja, mbetja_para)::numeric, 4)                   AS korr,
       round(regr_slope(mbetja, mbetja_para)::numeric, 4)             AS pjerresia,
       round((sqrt((1 - regr_r2(mbetja, mbetja_para)) / (count(*)-2)::float8)
              * stddev_samp(mbetja) / stddev_samp(mbetja_para))::numeric, 4) AS se_pjerresia,
       round(stddev_samp(mbetja_para)::numeric, 4)                    AS sd_mbetja_para
FROM w
WHERE n_para >= 5 AND mbetja_para IS NOT NULL;


-- ==================== PYETJA 2 — A PERSERIT NJE SKUADER SKORET E VETA? ====================
-- Ideja jote e drejtperdrejte: a prodhon nje skuader te njejtat skore me shpesh
-- se sa e jep liga e saj?
--
-- `f_ekipi` = sa pjese e ndeshjeve TE MEPARSHME te ketij ekipi ne shtepi kane
--             pasur SAKTESISHT skorin e ndeshjes aktuale
-- `f_liga`  = sa pjese e TE GJITHA ndeshjeve te asaj lige e atij sezoni e kane
--             pasur ate skor
--
-- Nese `f_ekipi` > `f_liga` ne menyre te qendrueshme, skuadrat kane gjurme skori.
-- Nese jane te barabarta, skori i nje ndeshjeje eshte i pavarur nga historiku i
-- ekipit pertej asaj qe forca e tij shpjegon.
--
-- ⚠️ Kjo NUK kontrollon per forcen. Nje ekip i forte prodhon 3-0 shpesh dhe liga
--    jo — ndaj pritet nje diference POZITIVE edhe pa asnje gjurme te vertete.
--    Prandaj pyetja 3 e ben kontrollin e duhur.
WITH b AS (
    SELECT home_team_id, sezoni, liga, data_ndeshjes,
           (gola_home || '-' || gola_away) AS skori
    FROM historik_trajnimi
    WHERE gola_home IS NOT NULL AND gola_away IS NOT NULL
      AND home_team_id IS NOT NULL AND sezoni IS NOT NULL
      AND liga IS NOT NULL AND data_ndeshjes IS NOT NULL
),
liga_f AS (
    SELECT liga, sezoni, skori,
           count(*)::float8 / sum(count(*)) OVER (PARTITION BY liga, sezoni) AS f_liga
    FROM b GROUP BY liga, sezoni, skori
),
t AS (
    SELECT b.*,
           count(*) OVER (PARTITION BY home_team_id, sezoni ORDER BY data_ndeshjes
                          ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)        AS n_para,
           count(*) OVER (PARTITION BY home_team_id, sezoni, skori ORDER BY data_ndeshjes
                          ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)        AS n_i_njejti
    FROM b
)
SELECT count(*)                                                     AS n,
       round(avg(t.n_para)::numeric, 1)                             AS ndeshje_para_mes,
       round(avg(t.n_i_njejti::float8 / t.n_para)::numeric, 4)      AS f_ekipi,
       round(avg(l.f_liga)::numeric, 4)                             AS f_liga,
       round(avg(t.n_i_njejti::float8 / t.n_para - l.f_liga)::numeric, 4) AS diferenca,
       round((stddev_samp(t.n_i_njejti::float8 / t.n_para - l.f_liga)
              / sqrt(count(*)))::numeric, 5)                        AS se,
       round((avg(t.n_i_njejti::float8 / t.n_para - l.f_liga)
              / NULLIF(stddev_samp(t.n_i_njejti::float8 / t.n_para - l.f_liga)
                       / sqrt(count(*)), 0))::numeric, 2)           AS sigma
FROM t
JOIN liga_f l ON l.liga = t.liga AND l.sezoni = t.sezoni AND l.skori = t.skori
WHERE t.n_para >= 8;


-- ==================== PYETJA 3 — E NJEJTA, POR ME KONTROLL PER FORCEN ====================
-- Kontrolli: ndaje sipas brezit te kuotave. Brenda nje brezi, ekipet kane forca
-- te ngjashme, ndaj cdo diference qe MBETET eshte gjurme e vertete e ekipit dhe
-- jo thjesht pasoje e forces se tij.
--
-- Nese `diferenca` bie ne zero pas ketij kontrolli, hipoteza vdes: skuadrat s'kane
-- gjurme skori — kane thjesht nivele te ndryshme, dhe ato modeli i di tashme.
WITH b AS (
    SELECT home_team_id, sezoni, liga, data_ndeshjes, odd_home,
           (gola_home || '-' || gola_away) AS skori
    FROM historik_trajnimi
    WHERE gola_home IS NOT NULL AND gola_away IS NOT NULL
      AND home_team_id IS NOT NULL AND sezoni IS NOT NULL
      AND liga IS NOT NULL AND data_ndeshjes IS NOT NULL
      AND odd_home > 1 AND odd_home < 6
),
z AS (
    SELECT b.*,
           CASE WHEN odd_home < 1.50 THEN 1
                WHEN odd_home < 1.80 THEN 2
                WHEN odd_home < 2.20 THEN 3
                WHEN odd_home < 3.00 THEN 4
                ELSE                       5 END AS brezi
    FROM b
),
brez_f AS (
    SELECT brezi, skori,
           count(*)::float8 / sum(count(*)) OVER (PARTITION BY brezi) AS f_brezi
    FROM z GROUP BY brezi, skori
),
t AS (
    SELECT z.*,
           count(*) OVER (PARTITION BY home_team_id, sezoni ORDER BY data_ndeshjes
                          ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)  AS n_para,
           count(*) OVER (PARTITION BY home_team_id, sezoni, skori ORDER BY data_ndeshjes
                          ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)  AS n_i_njejti
    FROM z
)
SELECT t.brezi,
       count(*)                                                          AS n,
       round(avg(t.n_i_njejti::float8 / t.n_para)::numeric, 4)           AS f_ekipi,
       round(avg(f.f_brezi)::numeric, 4)                                 AS f_brezi,
       round(avg(t.n_i_njejti::float8 / t.n_para - f.f_brezi)::numeric, 4) AS diferenca,
       round((avg(t.n_i_njejti::float8 / t.n_para - f.f_brezi)
              / NULLIF(stddev_samp(t.n_i_njejti::float8 / t.n_para - f.f_brezi)
                       / sqrt(count(*)), 0))::numeric, 2)                AS sigma
FROM t
JOIN brez_f f ON f.brezi = t.brezi AND f.skori = t.skori
WHERE t.n_para >= 8
GROUP BY t.brezi
ORDER BY t.brezi;
