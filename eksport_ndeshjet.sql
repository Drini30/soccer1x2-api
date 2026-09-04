WITH b AS (
    SELECT v.match_id, v.data, v.liga, v.ndeshja, v.besueshmeria,
           v.xg1, v.xg2, v.tot_pritur,
           v.pm_1, v.pm_x, v.pm_2,
           v.mc_p1, v.mc_px, v.mc_p2,
           v.parashikimi, v.p1g, v.p2g,
           v.rezultati_ft, v.r1, v.r2, v.tot_real,
           v.skor_amax, v.rregulli, v.brenda_rreze,
           v.goditi_pub, v.goditi_amax, v.n_skore,
           a.dist_gola::jsonb  AS dg,
           a.odds_reale::jsonb AS od
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
),
t AS (
    SELECT b.match_id, sum(e.v::numeric) AS freq_tot
    FROM b, LATERAL jsonb_each_text(b.dg) AS e(k, v)
    GROUP BY 1
)
SELECT
    b.data,
    b.liga,
    b.ndeshja,

    round(b.xg1, 2)                                    AS lam_home,
    round(b.xg2, 2)                                    AS lam_away,
    round(b.tot_pritur, 2)                             AS lam_total,

    b.parashikimi                                      AS skori_yne,
    b.rezultati_ft                                     AS skori_real,
    b.skor_amax                                        AS skori_argmax,

    (b.p1g - b.r1)                                     AS gabim_home,
    (b.p2g - b.r2)                                     AS gabim_away,
    ((b.p1g + b.p2g) - (b.r1 + b.r2))                  AS gabim_total,
    (abs(b.p1g - b.r1) + abs(b.p2g - b.r2))            AS distanca,

    CASE WHEN b.p1g = b.r1 AND b.p2g = b.r2            THEN '0 GODITJE'
         WHEN abs(b.p1g-b.r1) + abs(b.p2g-b.r2) = 1    THEN '1 NJE GOL'
         WHEN abs(b.p1g-b.r1) + abs(b.p2g-b.r2) = 2    THEN '2 DY GOLA'
         ELSE                                               '3 LARG' END AS lloji,

    CASE WHEN b.p1g > b.p2g THEN '1' WHEN b.p1g < b.p2g THEN '2' ELSE 'X' END AS drejtimi_yne,
    CASE WHEN b.r1  > b.r2  THEN '1' WHEN b.r1  < b.r2  THEN '2' ELSE 'X' END AS drejtimi_real,

    round(100.0 * ((b.dg ->> (b.r1 || '-' || b.r2))::numeric)
          / NULLIF(t.freq_tot, 0), 2)                  AS prob_reale_pct,

    CASE WHEN b.dg ? (b.r1 || '-' || b.r2)
         THEN (SELECT count(*) + 1
                 FROM jsonb_each_text(b.dg) AS e(k, v)
                WHERE e.v::numeric > (b.dg ->> (b.r1 || '-' || b.r2))::numeric)
    END                                                AS renditja_reale,

    round(100.0 * ((b.dg ->> (b.p1g || '-' || b.p2g))::numeric)
          / NULLIF(t.freq_tot, 0), 2)                  AS prob_e_jona_pct,

    (SELECT string_agg(x.k || ' ' || to_char(100.0*x.v::numeric/t.freq_tot, 'FM990.0') || '%',
                       '  /  ' ORDER BY x.v::numeric DESC)
       FROM (SELECT k, v FROM jsonb_each_text(b.dg) ORDER BY v::numeric DESC LIMIT 4) x
    )                                                  AS top4_i_yni,

    round(b.pm_1, 3)                                   AS treg_1,
    round(b.pm_x, 3)                                   AS treg_x,
    round(b.pm_2, 3)                                   AS treg_2,
    round(b.mc_p1, 3)                                  AS modeli_1,
    round(b.mc_px, 3)                                  AS modeli_x,
    round(b.mc_p2, 3)                                  AS modeli_2,

    (b.od ->> 'Over 2.5')                              AS kuota_over25,
    (b.od ->> 'Under 2.5')                             AS kuota_under25,
    (b.od #>> ARRAY['CS', b.r1 || '-' || b.r2])        AS kuota_cs_reale,
    (b.od #>> ARRAY['CS', b.p1g || '-' || b.p2g])      AS kuota_cs_e_jona,

    b.rregulli,
    b.brenda_rreze,
    b.besueshmeria,
    b.n_skore,
    b.match_id
FROM b
JOIN t ON t.match_id = b.match_id
ORDER BY b.data DESC, b.ndeshja;
