SELECT jsonb_pretty(odds_reale::jsonb) AS struktura_e_kuotave
FROM arkiv_rezultatesh
WHERE odds_reale IS NOT NULL AND odds_reale::jsonb <> '{}'::jsonb
ORDER BY data DESC
LIMIT 1;


WITH y AS (
    SELECT r1, r2, p1g, p2g,
           mc_p1, mc_px, mc_p2,
           pm_1, pm_x, pm_2,
           (0.65*mc_p1 + 0.35*pm_1) AS b1,
           (0.65*mc_px + 0.35*pm_x) AS bx,
           (0.65*mc_p2 + 0.35*pm_2) AS b2
    FROM v_analiza_rreze
    WHERE mc_p1 IS NOT NULL AND pm_1 IS NOT NULL
),
x AS (
    SELECT CASE WHEN r1 > r2 THEN '1' WHEN r1 < r2 THEN '2' ELSE 'X' END AS reali,
           CASE WHEN p1g > p2g THEN '1' WHEN p1g < p2g THEN '2' ELSE 'X' END AS pub,
           CASE WHEN mc_p1 >= mc_px AND mc_p1 >= mc_p2 THEN '1'
                WHEN mc_p2 >  mc_p1 AND mc_p2 >= mc_px THEN '2'
                ELSE 'X' END AS mc,
           CASE WHEN b1 >= bx AND b1 >= b2 THEN '1'
                WHEN b2 >  b1 AND b2 >= bx THEN '2'
                ELSE 'X' END AS blend,
           CASE WHEN pm_1 >= pm_x AND pm_1 >= pm_2 THEN '1'
                WHEN pm_2 >  pm_1 AND pm_2 >= pm_x THEN '2'
                ELSE 'X' END AS treg
    FROM y
)
SELECT count(*) AS n,
       round(100.0*count(*) FILTER (WHERE pub   = reali)/count(*), 2) AS pub_pct,
       round(100.0*count(*) FILTER (WHERE mc    = reali)/count(*), 2) AS mc_pct,
       round(100.0*count(*) FILTER (WHERE blend = reali)/count(*), 2) AS blend_pct,
       round(100.0*count(*) FILTER (WHERE treg  = reali)/count(*), 2) AS treg_pct,
       count(*) FILTER (WHERE mc <> blend) AS sa_here_ndryshojne
FROM x;


WITH y AS (
    SELECT r1, r2,
           mc_p1, mc_px, mc_p2,
           (0.65*mc_p1 + 0.35*pm_1) AS b1,
           (0.65*mc_px + 0.35*pm_x) AS bx,
           (0.65*mc_p2 + 0.35*pm_2) AS b2
    FROM v_analiza_rreze
    WHERE mc_p1 IS NOT NULL AND pm_1 IS NOT NULL
),
x AS (
    SELECT CASE WHEN r1 > r2 THEN '1' WHEN r1 < r2 THEN '2' ELSE 'X' END AS reali,
           CASE WHEN mc_p1 >= mc_px AND mc_p1 >= mc_p2 THEN '1'
                WHEN mc_p2 >  mc_p1 AND mc_p2 >= mc_px THEN '2'
                ELSE 'X' END AS mc,
           CASE WHEN b1 >= bx AND b1 >= b2 THEN '1'
                WHEN b2 >  b1 AND b2 >= bx THEN '2'
                ELSE 'X' END AS blend
    FROM y
)
SELECT count(*) AS n,
       count(*) FILTER (WHERE mc = reali AND blend <> reali) AS vetem_mc,
       count(*) FILTER (WHERE blend = reali AND mc <> reali) AS vetem_blend,
       round(100.0*(count(*) FILTER (WHERE blend = reali)
                  - count(*) FILTER (WHERE mc = reali))/count(*), 2) AS fitimi_pp,
       CASE WHEN (count(*) FILTER (WHERE mc = reali AND blend <> reali)
                + count(*) FILTER (WHERE blend = reali AND mc <> reali)) > 0
            THEN round(power(abs(count(*) FILTER (WHERE mc = reali AND blend <> reali)
                               - count(*) FILTER (WHERE blend = reali AND mc <> reali))::numeric - 1, 2)
                       / (count(*) FILTER (WHERE mc = reali AND blend <> reali)
                        + count(*) FILTER (WHERE blend = reali AND mc <> reali)), 3)
       END AS chi2
FROM x;


WITH y AS (
    SELECT r1, r2, p1g, p2g,
           mc_p1, mc_px, mc_p2,
           (0.65*mc_p1 + 0.35*pm_1) AS b1,
           (0.65*mc_px + 0.35*pm_x) AS bx,
           (0.65*mc_p2 + 0.35*pm_2) AS b2
    FROM v_analiza_rreze
    WHERE mc_p1 IS NOT NULL AND pm_1 IS NOT NULL
),
x AS (
    SELECT CASE WHEN r1 > r2 THEN '1' WHEN r1 < r2 THEN '2' ELSE 'X' END AS reali,
           CASE WHEN p1g > p2g THEN '1' WHEN p1g < p2g THEN '2' ELSE 'X' END AS pub,
           CASE WHEN mc_p1 >= mc_px AND mc_p1 >= mc_p2 THEN '1'
                WHEN mc_p2 >  mc_p1 AND mc_p2 >= mc_px THEN '2'
                ELSE 'X' END AS mc,
           CASE WHEN b1 >= bx AND b1 >= b2 THEN '1'
                WHEN b2 >  b1 AND b2 >= bx THEN '2'
                ELSE 'X' END AS blend
    FROM y
),
t AS (SELECT count(*)::numeric AS n FROM x)
SELECT 'reale'::text AS burimi,
       round(100.0*(SELECT count(*) FROM x WHERE reali='1')/t.n, 1) AS pct_1,
       round(100.0*(SELECT count(*) FROM x WHERE reali='X')/t.n, 1) AS pct_x,
       round(100.0*(SELECT count(*) FROM x WHERE reali='2')/t.n, 1) AS pct_2
FROM t
UNION ALL
SELECT 'publikuar',
       round(100.0*(SELECT count(*) FROM x WHERE pub='1')/t.n, 1),
       round(100.0*(SELECT count(*) FROM x WHERE pub='X')/t.n, 1),
       round(100.0*(SELECT count(*) FROM x WHERE pub='2')/t.n, 1)
FROM t
UNION ALL
SELECT 'mc pa treg',
       round(100.0*(SELECT count(*) FROM x WHERE mc='1')/t.n, 1),
       round(100.0*(SELECT count(*) FROM x WHERE mc='X')/t.n, 1),
       round(100.0*(SELECT count(*) FROM x WHERE mc='2')/t.n, 1)
FROM t
UNION ALL
SELECT 'blend me treg',
       round(100.0*(SELECT count(*) FROM x WHERE blend='1')/t.n, 1),
       round(100.0*(SELECT count(*) FROM x WHERE blend='X')/t.n, 1),
       round(100.0*(SELECT count(*) FROM x WHERE blend='2')/t.n, 1)
FROM t;
