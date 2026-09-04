-- ==================== PYETJA 1 ====================
WITH b AS (
    SELECT v.match_id, v.data, v.liga, v.ndeshja,
           v.xg1, v.xg2, v.tot_pritur,
           v.parashikimi, v.p1g, v.p2g,
           v.rezultati_ft, v.r1, v.r2, v.tot_real,
           v.skor_amax, v.rregulli, v.besueshmeria,
           v.pm_1, v.pm_x, v.pm_2,
           v.mc_p1, v.mc_px, v.mc_p2,
           a.dist_gola::jsonb    AS dg,
           a.odds_reale::jsonb   AS od,
           a.training_data::jsonb AS td
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
    WHERE (v.p1g + v.p2g) = (v.r1 + v.r2)
      AND NOT (v.p1g = v.r1 AND v.p2g = v.r2)
),
t AS (
    SELECT b.match_id, sum(e.v::numeric) AS freq_tot
    FROM b, LATERAL jsonb_each_text(b.dg) AS e(k, v)
    GROUP BY 1
)
SELECT
    b.data, b.liga, b.ndeshja,
    b.parashikimi                                   AS skori_yne,
    b.rezultati_ft                                  AS skori_real,
    b.skor_amax                                     AS skori_argmax,
    (b.p1g + b.p2g)                                 AS totali,

    round(b.xg1, 2)                                 AS lam_home,
    round(b.xg2, 2)                                 AS lam_away,
    round(b.xg1 - b.xg2, 2)                         AS suprem_parashikuar,
    (b.r1 - b.r2)                                   AS suprem_real,
    round((b.r1 - b.r2) - (b.xg1 - b.xg2), 2)       AS gabim_suprem,

    round((b.td ->> 'elo_1')::numeric, 0)           AS elo_home,
    round((b.td ->> 'elo_2')::numeric, 0)           AS elo_away,
    round(((b.td ->> 'elo_1')::numeric
         - (b.td ->> 'elo_2')::numeric), 0)         AS elo_diff,

    round(b.pm_1, 3)                                AS treg_1,
    round(b.pm_x, 3)                                AS treg_x,
    round(b.pm_2, 3)                                AS treg_2,
    round(b.mc_p1, 3)                               AS modeli_1,
    round(b.mc_px, 3)                               AS modeli_x,
    round(b.mc_p2, 3)                               AS modeli_2,

    round((b.td ->> 'modulator_1')::numeric, 3)     AS modulator_home,
    round((b.td ->> 'modulator_2')::numeric, 3)     AS modulator_away,
    round((b.td ->> 'clutch_1')::numeric, 3)        AS clutch_home,
    round((b.td ->> 'clutch_2')::numeric, 3)        AS clutch_away,
    round((b.td ->> 'desp_1')::numeric, 3)          AS desp_home,
    round((b.td ->> 'desp_2')::numeric, 3)          AS desp_away,

    round((b.td ->> 'home_forma_pts')::numeric, 1)  AS forma_home,
    round((b.td ->> 'away_forma_pts')::numeric, 1)  AS forma_away,
    round((b.td ->> 'home_avg_scored')::numeric, 2)   AS shenoi_home,
    round((b.td ->> 'away_avg_scored')::numeric, 2)   AS shenoi_away,
    round((b.td ->> 'home_avg_conceded')::numeric, 2) AS pesoi_home,
    round((b.td ->> 'away_avg_conceded')::numeric, 2) AS pesoi_away,
    (b.td ->> 'pozicion_1')                         AS pozicion_home,
    (b.td ->> 'pozicion_2')                         AS pozicion_away,
    (b.td ->> 'burimi_xg')                          AS burimi_xg,

    round(100.0 * ((b.dg ->> (b.r1 || '-' || b.r2))::numeric)
          / NULLIF(t.freq_tot, 0), 2)               AS prob_reale_pct,
    CASE WHEN b.dg ? (b.r1 || '-' || b.r2)
         THEN (SELECT count(*) + 1 FROM jsonb_each_text(b.dg) AS e(k, v)
                WHERE e.v::numeric > (b.dg ->> (b.r1 || '-' || b.r2))::numeric)
    END                                             AS renditja_reale,
    round(100.0 * ((b.dg ->> (b.p1g || '-' || b.p2g))::numeric)
          / NULLIF(t.freq_tot, 0), 2)               AS prob_e_jona_pct,

    (b.od #>> ARRAY['CS', b.r1 || '-' || b.r2])     AS kuota_cs_reale,
    (b.od #>> ARRAY['CS', b.p1g || '-' || b.p2g])   AS kuota_cs_e_jona,

    b.rregulli, b.besueshmeria, b.match_id
FROM b
JOIN t ON t.match_id = b.match_id
ORDER BY abs((b.r1 - b.r2) - (b.xg1 - b.xg2)) DESC;


-- ==================== PYETJA 2 ====================
WITH b AS (
    SELECT v.r1, v.r2, v.xg1, v.xg2, v.pm_1, v.pm_2,
           a.training_data::jsonb AS td
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
    WHERE v.xg1 IS NOT NULL AND v.pm_1 IS NOT NULL
),
p AS (
    SELECT ((r1 - r2)::float8 - (xg1 - xg2)::float8)                    AS gabim,
           ((td ->> 'elo_1')::float8 - (td ->> 'elo_2')::float8)        AS elo_d,
           (pm_1 - pm_2)                                                AS treg_d,
           ((td ->> 'home_forma_pts')::float8 - (td ->> 'away_forma_pts')::float8) AS forma_d,
           ((td ->> 'modulator_1')::float8 - (td ->> 'modulator_2')::float8)       AS mod_d,
           ((td ->> 'clutch_1')::float8 - (td ->> 'clutch_2')::float8)  AS clutch_d,
           ((td ->> 'desp_1')::float8 - (td ->> 'desp_2')::float8)      AS desp_d,
           ((td ->> 'home_avg_scored')::float8 - (td ->> 'away_avg_scored')::float8)     AS shenoi_d,
           ((td ->> 'away_avg_conceded')::float8 - (td ->> 'home_avg_conceded')::float8) AS pesoi_d,
           ((td ->> 'home_rest_days')::float8 - (td ->> 'away_rest_days')::float8)       AS pushim_d,
           ((td ->> 'home_win_rate')::float8 - (td ->> 'away_win_rate')::float8)         AS winrate_d
    FROM b
    WHERE (td ->> 'elo_1') ~ '^-?[0-9.]+$'
      AND (td ->> 'modulator_1') ~ '^-?[0-9.]+$'
)
SELECT count(*)                                        AS n,
       round(avg(gabim)::numeric, 4)                   AS gabim_mes,
       round(corr(gabim, elo_d)::numeric, 4)           AS korr_elo,
       round(corr(gabim, treg_d)::numeric, 4)          AS korr_treg,
       round(corr(gabim, forma_d)::numeric, 4)         AS korr_forma,
       round(corr(gabim, mod_d)::numeric, 4)           AS korr_modulator,
       round(corr(gabim, clutch_d)::numeric, 4)        AS korr_clutch,
       round(corr(gabim, desp_d)::numeric, 4)          AS korr_desp,
       round(corr(gabim, shenoi_d)::numeric, 4)        AS korr_shenoi,
       round(corr(gabim, pesoi_d)::numeric, 4)         AS korr_pesoi,
       round(corr(gabim, pushim_d)::numeric, 4)        AS korr_pushim,
       round(corr(gabim, winrate_d)::numeric, 4)       AS korr_winrate
FROM p;
