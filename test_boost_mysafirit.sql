-- ==================== PYETJA 1 ====================
WITH b AS (
    SELECT v.r1, v.r2, v.xg1, v.xg2,
           (a.training_data::jsonb ->> 'home_forma_pts')::float8 AS hp,
           (a.training_data::jsonb ->> 'away_forma_pts')::float8 AS ap
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
    WHERE v.xg1 IS NOT NULL
      AND (a.training_data::jsonb ->> 'home_forma_pts') ~ '^-?[0-9.]+$'
      AND (a.training_data::jsonb ->> 'away_forma_pts') ~ '^-?[0-9.]+$'
),
r AS (
    SELECT *,
           (r1 - r2)::float8                              AS sup_real,
           (xg1 - xg2)::float8                            AS sup_pred,
           ((r1 - r2)::float8 - (xg1 - xg2)::float8)      AS mbetja,
           (ap - hp)                                      AS hendeku
    FROM b
)
SELECT CASE WHEN ap > hp THEN 'a) mysafiri forme me te mire'
            WHEN hp > ap THEN 'c) vendasi forme me te mire'
            ELSE                'b) barabar' END          AS grupi,
       count(*)                                           AS n,
       round(avg(sup_pred)::numeric, 3)                   AS suprem_parashikuar,
       round(avg(sup_real)::numeric, 3)                   AS suprem_real,
       round(avg(mbetja)::numeric, 3)                     AS mbetja,
       round((stddev_samp(mbetja)/sqrt(count(*)))::numeric, 3) AS se,
       round((avg(mbetja)/NULLIF(stddev_samp(mbetja)/sqrt(count(*)),0))::numeric, 2) AS sigma
FROM r
GROUP BY 1
ORDER BY 1;


-- ==================== PYETJA 2 ====================
WITH b AS (
    SELECT v.r1, v.r2, v.xg1, v.xg2,
           (a.training_data::jsonb ->> 'home_forma_pts')::float8 AS hp,
           (a.training_data::jsonb ->> 'away_forma_pts')::float8 AS ap
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
    WHERE v.xg1 IS NOT NULL
      AND (a.training_data::jsonb ->> 'home_forma_pts') ~ '^-?[0-9.]+$'
      AND (a.training_data::jsonb ->> 'away_forma_pts') ~ '^-?[0-9.]+$'
),
r AS (
    SELECT ((r1 - r2)::float8 - (xg1 - xg2)::float8) AS mbetja,
           (ap - hp)                                 AS hendeku
    FROM b
)
SELECT CASE WHEN hendeku <= -4 THEN 'a) vendasi shume me i mire'
            WHEN hendeku <  -1 THEN 'b) vendasi me i mire'
            WHEN hendeku <=  1 THEN 'c) afersisht barabar'
            WHEN hendeku <   4 THEN 'd) mysafiri me i mire'
            ELSE                    'e) mysafiri shume me i mire' END AS brezi,
       count(*)                                           AS n,
       round(avg(hendeku)::numeric, 2)                    AS hendeku_mes,
       round(avg(mbetja)::numeric, 3)                     AS mbetja,
       round((stddev_samp(mbetja)/sqrt(count(*)))::numeric, 3) AS se,
       round((avg(mbetja)/NULLIF(stddev_samp(mbetja)/sqrt(count(*)),0))::numeric, 2) AS sigma
FROM r
GROUP BY 1
ORDER BY 1;


-- ==================== PYETJA 3 ====================
WITH b AS (
    SELECT v.r1, v.r2, v.xg1, v.xg2,
           (a.training_data::jsonb ->> 'home_forma_pts')::float8 AS hp,
           (a.training_data::jsonb ->> 'away_forma_pts')::float8 AS ap
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
    WHERE v.xg1 IS NOT NULL
      AND (a.training_data::jsonb ->> 'home_forma_pts') ~ '^-?[0-9.]+$'
      AND (a.training_data::jsonb ->> 'away_forma_pts') ~ '^-?[0-9.]+$'
),
r AS (
    SELECT ((r1 - r2)::float8 - (xg1 - xg2)::float8) AS mbetja,
           (ap - hp)                                 AS hendeku
    FROM b
)
SELECT count(*)                                                        AS n,
       round(avg(mbetja)::numeric, 4)                                  AS mbetja_gjithsej,
       round(regr_slope(mbetja, hendeku)::numeric, 4)                  AS pjerresia,
       round((sqrt((1 - regr_r2(mbetja, hendeku)) / (count(*) - 2)::float8)
              * stddev_samp(mbetja) / stddev_samp(hendeku))::numeric, 4) AS se_pjerresia,
       round(regr_r2(mbetja, hendeku)::numeric, 4)                     AS r2,
       round(stddev_samp(hendeku)::numeric, 2)                         AS sd_hendeku
FROM r;
