-- ==================== PYETJA 1 ====================
WITH b AS (
    SELECT v.match_id, v.besueshmeria, v.p1g, v.p2g,
           v.mc_p1, v.mc_px, v.mc_p2,
           v.pm_1,  v.pm_x,  v.pm_2,
           (0.65*v.mc_p1 + 0.35*v.pm_1) AS b1,
           (0.65*v.mc_px + 0.35*v.pm_x) AS bx,
           (0.65*v.mc_p2 + 0.35*v.pm_2) AS b2,
           (a.training_data::jsonb ->> 'home_win_rate')::float8 AS wr1,
           (a.training_data::jsonb ->> 'away_win_rate')::float8 AS wr2,
           ((a.dist_gola::jsonb ->> (v.p1g || '-' || v.p2g))::numeric / 50000.0) AS prez
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
    WHERE v.mc_p1 IS NOT NULL AND v.pm_1 IS NOT NULL
      AND v.besueshmeria IS NOT NULL
      AND (a.training_data::jsonb ->> 'home_win_rate') ~ '^-?[0-9.]+$'
),
c AS (
    SELECT b.*,
           GREATEST(1.0 - LEAST(1.0, (abs(b1-pm_1)+abs(bx-pm_x)+abs(b2-pm_2))/1.5), 0.0) AS konsensus_kodi,
           GREATEST(1.0 - LEAST(1.0, (abs(mc_p1-pm_1)+abs(mc_px-pm_x)+abs(mc_p2-pm_2))/1.5), 0.0) AS konsensus_raw,
           ((GREATEST(b1, bx, b2) - 0.33) / 0.67)                                        AS sinjal,
           CASE WHEN b1 > b2 AND b1 > bx THEN wr1
                WHEN b2 > b1 AND b2 > bx THEN wr2
                ELSE 0.35 END                                                            AS forma_score,
           (COALESCE(prez, 0.0) * 0.5)                                                    AS bonus_rez
    FROM b
)
SELECT count(*)                                                     AS n,
       round(avg(konsensus_kodi)::numeric, 4)                       AS konsensus_mes,
       round(stddev_samp(konsensus_kodi)::numeric, 4)               AS konsensus_sd,
       round(avg(konsensus_raw)::numeric, 4)                        AS konsensus_raw_mes,
       round(stddev_samp(konsensus_raw)::numeric, 4)                AS konsensus_raw_sd,
       round(avg(sinjal)::numeric, 4)                               AS sinjal_mes,
       round(stddev_samp(sinjal)::numeric, 4)                       AS sinjal_sd,
       round(avg(forma_score)::numeric, 4)                          AS forma_mes,
       round(stddev_samp(forma_score)::numeric, 4)                  AS forma_sd,
       round(avg(bonus_rez)::numeric, 4)                            AS bonus_mes,
       round(stddev_samp(bonus_rez)::numeric, 4)                    AS bonus_sd,
       round(avg(55.0 + 37.0*(0.35*konsensus_kodi + 0.30*sinjal
                            + 0.25*forma_score + 0.10*bonus_rez))::numeric, 2) AS bes_rinderuar,
       round(avg(besueshmeria)::numeric, 2)                         AS bes_e_ruajtur,
       round(avg(abs(besueshmeria
                 - (55.0 + 37.0*(0.35*konsensus_kodi + 0.30*sinjal
                               + 0.25*forma_score + 0.10*bonus_rez))))::numeric, 3) AS devijimi
FROM c;


-- ==================== PYETJA 2 ====================
WITH b AS (
    SELECT v.match_id, v.besueshmeria, v.p1g, v.p2g, v.r1, v.r2,
           v.mc_p1, v.mc_px, v.mc_p2, v.pm_1, v.pm_x, v.pm_2,
           (0.65*v.mc_p1 + 0.35*v.pm_1) AS b1,
           (0.65*v.mc_px + 0.35*v.pm_x) AS bx,
           (0.65*v.mc_p2 + 0.35*v.pm_2) AS b2,
           (a.training_data::jsonb ->> 'home_win_rate')::float8 AS wr1,
           (a.training_data::jsonb ->> 'away_win_rate')::float8 AS wr2,
           ((a.dist_gola::jsonb ->> (v.p1g || '-' || v.p2g))::numeric / 50000.0) AS prez
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
    WHERE v.mc_p1 IS NOT NULL AND v.pm_1 IS NOT NULL
      AND v.besueshmeria IS NOT NULL
      AND (a.training_data::jsonb ->> 'home_win_rate') ~ '^-?[0-9.]+$'
),
c AS (
    SELECT b.*,
           GREATEST(1.0 - LEAST(1.0, (abs(b1-pm_1)+abs(bx-pm_x)+abs(b2-pm_2))/1.5), 0.0) AS konsensus_kodi,
           GREATEST(1.0 - LEAST(1.0, (abs(mc_p1-pm_1)+abs(mc_px-pm_x)+abs(mc_p2-pm_2))/1.5), 0.0) AS konsensus_raw,
           ((GREATEST(b1, bx, b2) - 0.33) / 0.67) AS sinjal,
           CASE WHEN b1 > b2 AND b1 > bx THEN wr1
                WHEN b2 > b1 AND b2 > bx THEN wr2
                ELSE 0.35 END AS forma_score,
           (COALESCE(prez, 0.0) * 0.5) AS bonus_rez,
           CASE WHEN (CASE WHEN p1g > p2g THEN '1' WHEN p1g < p2g THEN '2' ELSE 'X' END)
                   = (CASE WHEN r1  > r2  THEN '1' WHEN r1  < r2  THEN '2' ELSE 'X' END)
                THEN 1.0 ELSE 0.0 END AS hit_1x2,
           CASE WHEN p1g = r1 AND p2g = r2 THEN 1.0 ELSE 0.0 END AS hit_skor
    FROM b
)
SELECT count(*)                                                   AS n,
       round(corr(hit_1x2, besueshmeria::float8)::numeric, 4)      AS bes_vs_1x2,
       round(corr(hit_1x2, konsensus_kodi)::numeric, 4)            AS konsensus_kodi_vs_1x2,
       round(corr(hit_1x2, konsensus_raw)::numeric, 4)             AS konsensus_raw_vs_1x2,
       round(corr(hit_1x2, sinjal)::numeric, 4)                    AS sinjal_vs_1x2,
       round(corr(hit_1x2, forma_score)::numeric, 4)               AS forma_vs_1x2,
       round(corr(hit_1x2, bonus_rez)::numeric, 4)                 AS bonus_vs_1x2,
       round(corr(hit_skor, besueshmeria::float8)::numeric, 4)     AS bes_vs_skor,
       round(corr(hit_skor, konsensus_raw)::numeric, 4)            AS konsensus_raw_vs_skor,
       round(corr(hit_skor, sinjal)::numeric, 4)                   AS sinjal_vs_skor,
       round(corr(hit_skor, forma_score)::numeric, 4)              AS forma_vs_skor,
       round(corr(hit_skor, bonus_rez)::numeric, 4)                AS bonus_vs_skor
FROM c;
