-- ==================== PYETJA 1 ====================
WITH b AS (
    SELECT v.match_id, v.p1g, v.p2g, a.dist_gola::jsonb AS dg
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
    WHERE a.dist_gola IS NOT NULL AND a.dist_gola::jsonb <> '{}'::jsonb
),
r AS (
    SELECT CASE WHEN b.dg ? (b.p1g || '-' || b.p2g)
                THEN (SELECT count(*) + 1 FROM jsonb_each_text(b.dg) AS e(k, v)
                       WHERE e.v::numeric > (b.dg ->> (b.p1g || '-' || b.p2g))::numeric)
           END AS renditja_e_publikuar
    FROM b
)
SELECT COALESCE(renditja_e_publikuar::text, 'jashte dist_gola') AS renditja,
       count(*)                                                 AS n,
       round(100.0*count(*)/sum(count(*)) OVER (), 1)           AS pct
FROM r
GROUP BY 1
ORDER BY (renditja_e_publikuar IS NULL), renditja_e_publikuar
LIMIT 12;


-- ==================== PYETJA 2 ====================
WITH b AS (
    SELECT v.match_id, v.r1, v.r2, a.dist_gola::jsonb AS dg
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
    WHERE a.dist_gola IS NOT NULL AND a.dist_gola::jsonb <> '{}'::jsonb
),
k AS (
    SELECT b.match_id, b.r1, b.r2,
           (SELECT sum(x.v::numeric)/50000.0 FROM
              (SELECT v FROM jsonb_each_text(b.dg) ORDER BY v::numeric DESC LIMIT 3) x) AS p3,
           (SELECT sum(x.v::numeric)/50000.0 FROM
              (SELECT v FROM jsonb_each_text(b.dg) ORDER BY v::numeric DESC LIMIT 4) x) AS p4,
           CASE WHEN b.dg ? (b.r1 || '-' || b.r2)
                THEN (SELECT count(*) + 1 FROM jsonb_each_text(b.dg) AS e(k, v)
                       WHERE e.v::numeric > (b.dg ->> (b.r1 || '-' || b.r2))::numeric)
                ELSE 99 END AS rend_reale
    FROM b
)
SELECT CASE WHEN p3 < 0.28 THEN 'a) p3 < 28%'
            WHEN p3 < 0.32 THEN 'b) p3 28-32%'
            WHEN p3 < 0.36 THEN 'c) p3 32-36%'
            ELSE               'd) p3 >= 36%' END          AS brezi,
       count(*)                                            AS n,
       round(avg(p3)*100, 1)                               AS premtuar_top3,
       round(100.0*count(*) FILTER (WHERE rend_reale <= 3)/count(*), 1) AS ndodhi_top3,
       round(avg(p4)*100, 1)                               AS premtuar_top4,
       round(100.0*count(*) FILTER (WHERE rend_reale <= 4)/count(*), 1) AS ndodhi_top4
FROM k
GROUP BY 1
ORDER BY 1;


-- ==================== PYETJA 3 ====================
WITH b AS (
    SELECT v.p1g, v.p2g, v.r1, v.r2, v.tot_pritur, v.besueshmeria,
           ((a.dist_gola::jsonb ->> (v.p1g || '-' || v.p2g))::numeric / 50000.0) AS prez,
           (SELECT sum(x.v::numeric)/50000.0 FROM
              (SELECT v FROM jsonb_each_text(a.dist_gola::jsonb) ORDER BY v::numeric DESC LIMIT 3) x) AS p3
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
    WHERE a.dist_gola IS NOT NULL AND a.dist_gola::jsonb <> '{}'::jsonb
      AND v.tot_pritur IS NOT NULL AND v.besueshmeria IS NOT NULL
),
c AS (
    SELECT CASE WHEN p1g = r1 AND p2g = r2 THEN 1.0 ELSE 0.0 END AS hit,
           COALESCE(prez, 0.0)::float8 AS prez, p3::float8 AS p3,
           tot_pritur::float8 AS lam, besueshmeria::float8 AS bes
    FROM b
)
SELECT count(*)                                          AS n,
       round(avg(hit)::numeric, 4)                       AS goditja_mes,
       round(corr(hit, prez)::numeric, 4)                AS korr_prob_skori,
       round((corr(hit, prez)*sqrt(count(*)-3))::numeric, 2)  AS sigma_prob,
       round(corr(hit, p3)::numeric, 4)                  AS korr_mbulimi_top3,
       round((corr(hit, p3)*sqrt(count(*)-3))::numeric, 2)    AS sigma_p3,
       round(corr(hit, lam)::numeric, 4)                 AS korr_lambda,
       round((corr(hit, lam)*sqrt(count(*)-3))::numeric, 2)   AS sigma_lam,
       round(corr(hit, bes)::numeric, 4)                 AS korr_besueshmeria,
       round((corr(hit, bes)*sqrt(count(*)-3))::numeric, 2)   AS sigma_bes
FROM c;


-- ==================== PYETJA 4 ====================
WITH b AS (
    SELECT (v.p1g || '-' || v.p2g) AS skori_yne,
           CASE WHEN v.p1g = v.r1 AND v.p2g = v.r2 THEN 1.0 ELSE 0.0 END AS hit,
           ((a.dist_gola::jsonb ->> (v.p1g || '-' || v.p2g))::numeric / 50000.0) AS prez
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
    WHERE a.dist_gola IS NOT NULL AND a.dist_gola::jsonb <> '{}'::jsonb
)
SELECT skori_yne,
       count(*)                                       AS here,
       round(avg(prez)*100, 2)                        AS premtuar_pct,
       round(avg(hit)*100, 2)                         AS goditi_pct,
       round((avg(hit) - avg(prez))*100, 2)           AS diferenca_pp,
       round((avg(hit) / NULLIF(avg(prez), 0))::numeric, 2) AS raporti
FROM b
GROUP BY 1
HAVING count(*) >= 25
ORDER BY here DESC;
