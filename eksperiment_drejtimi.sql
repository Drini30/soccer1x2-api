WITH s AS (
    SELECT v.match_id, v.r1, v.r2,
           v.mc_p1, v.mc_px, v.mc_p2,
           v.pm_1,  v.pm_x,  v.pm_2,
           (0.65*v.mc_p1 + 0.35*v.pm_1) AS b1,
           (0.65*v.mc_px + 0.35*v.pm_x) AS bx,
           (0.65*v.mc_p2 + 0.35*v.pm_2) AS b2,
           a.dist_gola::jsonb AS dg
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
    WHERE v.mc_p1 IS NOT NULL
      AND v.pm_1  IS NOT NULL
      AND a.dist_gola IS NOT NULL
      AND a.dist_gola::jsonb <> '{}'::jsonb
),
prag AS (SELECT unnest(ARRAY[0.00,0.05,0.10,0.15,0.20,0.30,0.99]) AS p),
burim AS (SELECT unnest(ARRAY['mc','blend','treg']) AS b),
g AS (
    SELECT s.*, prag.p AS prag, burim.b AS burimi,
           CASE burim.b
               WHEN 'mc' THEN
                   CASE WHEN s.mc_p1 >= s.mc_p2 AND (s.mc_p1 - s.mc_px) > prag.p THEN '1'
                        WHEN s.mc_p2 >  s.mc_p1 AND (s.mc_p2 - s.mc_px) > prag.p THEN '2'
                        ELSE 'A' END
               WHEN 'blend' THEN
                   CASE WHEN s.b1 >= s.b2 AND (s.b1 - s.bx) > prag.p THEN '1'
                        WHEN s.b2 >  s.b1 AND (s.b2 - s.bx) > prag.p THEN '2'
                        ELSE 'A' END
               ELSE
                   CASE WHEN s.pm_1 >= s.pm_2 AND (s.pm_1 - s.pm_x) > prag.p THEN '1'
                        WHEN s.pm_2 >  s.pm_1 AND (s.pm_2 - s.pm_x) > prag.p THEN '2'
                        ELSE 'A' END
           END AS dr
    FROM s CROSS JOIN prag CROSS JOIN burim
),
z AS (
    SELECT g.*,
           (SELECT e.k
              FROM jsonb_each_text(g.dg) AS e(k, v)
             WHERE g.dr = 'A'
                OR (g.dr = '1' AND split_part(e.k,'-',1)::int > split_part(e.k,'-',2)::int)
                OR (g.dr = '2' AND split_part(e.k,'-',1)::int < split_part(e.k,'-',2)::int)
             ORDER BY e.v::numeric DESC, e.k ASC
             LIMIT 1) AS skor
    FROM g
)
SELECT burimi,
       prag,
       count(*)                                                        AS n,
       count(*) FILTER (WHERE dr <> 'A')                               AS u_ndez,
       round(100.0*count(*) FILTER (WHERE dr <> 'A')/count(*), 1)      AS ndez_pct,
       round(100.0*count(*) FILTER (
             WHERE split_part(skor,'-',1)::int = r1
               AND split_part(skor,'-',2)::int = r2)/count(*), 2)      AS cs_pct,
       round(100.0*count(*) FILTER (
             WHERE (CASE WHEN split_part(skor,'-',1)::int > split_part(skor,'-',2)::int THEN '1'
                         WHEN split_part(skor,'-',1)::int < split_part(skor,'-',2)::int THEN '2'
                         ELSE 'X' END)
                 = (CASE WHEN r1 > r2 THEN '1' WHEN r1 < r2 THEN '2' ELSE 'X' END)
             )/count(*), 2)                                            AS drejtim_pct
FROM z
WHERE skor IS NOT NULL
GROUP BY burimi, prag
ORDER BY burimi, prag;
