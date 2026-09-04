-- ==================== PYETJA 1 ====================
SELECT jsonb_pretty(odds_reale::jsonb) AS struktura_e_kuotave
FROM arkiv_rezultatesh
WHERE odds_reale IS NOT NULL AND odds_reale::jsonb <> '{}'::jsonb
ORDER BY data DESC
LIMIT 1;


-- ==================== PYETJA 2 ====================
WITH s AS (
    SELECT v.match_id, v.r1, v.r2, v.mc_p1, v.mc_px, v.mc_p2,
           a.dist_gola::jsonb AS dg
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
    WHERE v.mc_p1 IS NOT NULL
      AND a.dist_gola IS NOT NULL
      AND a.dist_gola::jsonb <> '{}'::jsonb
),
d AS (
    SELECT s.*,
           CASE WHEN mc_p1 >= mc_p2 AND (mc_p1 - mc_px) > 0.15 THEN '1'
                WHEN mc_p2 >  mc_p1 AND (mc_p2 - mc_px) > 0.15 THEN '2'
                ELSE 'A' END AS dr15,
           CASE WHEN mc_p1 >= mc_p2 AND (mc_p1 - mc_px) > 0.10 THEN '1'
                WHEN mc_p2 >  mc_p1 AND (mc_p2 - mc_px) > 0.10 THEN '2'
                ELSE 'A' END AS dr10
    FROM s
),
z AS (
    SELECT d.*,
           (SELECT e.k FROM jsonb_each_text(d.dg) AS e(k,v)
             WHERE d.dr15 = 'A'
                OR (d.dr15='1' AND split_part(e.k,'-',1)::int > split_part(e.k,'-',2)::int)
                OR (d.dr15='2' AND split_part(e.k,'-',1)::int < split_part(e.k,'-',2)::int)
             ORDER BY e.v::numeric DESC, e.k ASC LIMIT 1) AS s15,
           (SELECT e.k FROM jsonb_each_text(d.dg) AS e(k,v)
             WHERE d.dr10 = 'A'
                OR (d.dr10='1' AND split_part(e.k,'-',1)::int > split_part(e.k,'-',2)::int)
                OR (d.dr10='2' AND split_part(e.k,'-',1)::int < split_part(e.k,'-',2)::int)
             ORDER BY e.v::numeric DESC, e.k ASC LIMIT 1) AS s10
    FROM d
),
f AS (
    SELECT (split_part(s15,'-',1)::int = r1 AND split_part(s15,'-',2)::int = r2) AS cs15,
           (split_part(s10,'-',1)::int = r1 AND split_part(s10,'-',2)::int = r2) AS cs10,
           ((CASE WHEN split_part(s15,'-',1)::int > split_part(s15,'-',2)::int THEN '1'
                  WHEN split_part(s15,'-',1)::int < split_part(s15,'-',2)::int THEN '2'
                  ELSE 'X' END)
            = (CASE WHEN r1 > r2 THEN '1' WHEN r1 < r2 THEN '2' ELSE 'X' END)) AS dir15,
           ((CASE WHEN split_part(s10,'-',1)::int > split_part(s10,'-',2)::int THEN '1'
                  WHEN split_part(s10,'-',1)::int < split_part(s10,'-',2)::int THEN '2'
                  ELSE 'X' END)
            = (CASE WHEN r1 > r2 THEN '1' WHEN r1 < r2 THEN '2' ELSE 'X' END)) AS dir10
    FROM z
    WHERE s15 IS NOT NULL AND s10 IS NOT NULL
)
SELECT 'SKORI'::text AS masa,
       count(*) AS n,
       count(*) FILTER (WHERE cs15 AND NOT cs10) AS vetem_prag015,
       count(*) FILTER (WHERE cs10 AND NOT cs15) AS vetem_prag010,
       CASE WHEN (count(*) FILTER (WHERE cs15 AND NOT cs10)
                + count(*) FILTER (WHERE cs10 AND NOT cs15)) > 0
            THEN round(power(abs(count(*) FILTER (WHERE cs15 AND NOT cs10)
                               - count(*) FILTER (WHERE cs10 AND NOT cs15))::numeric - 1, 2)
                       / (count(*) FILTER (WHERE cs15 AND NOT cs10)
                        + count(*) FILTER (WHERE cs10 AND NOT cs15)), 3)
       END AS chi2
FROM f
UNION ALL
SELECT 'DREJTIMI',
       count(*),
       count(*) FILTER (WHERE dir15 AND NOT dir10),
       count(*) FILTER (WHERE dir10 AND NOT dir15),
       CASE WHEN (count(*) FILTER (WHERE dir15 AND NOT dir10)
                + count(*) FILTER (WHERE dir10 AND NOT dir15)) > 0
            THEN round(power(abs(count(*) FILTER (WHERE dir15 AND NOT dir10)
                               - count(*) FILTER (WHERE dir10 AND NOT dir15))::numeric - 1, 2)
                       / (count(*) FILTER (WHERE dir15 AND NOT dir10)
                        + count(*) FILTER (WHERE dir10 AND NOT dir15)), 3)
       END
FROM f;


-- ==================== PYETJA 3 ====================
SELECT to_char(data::date, 'YYYY-MM') AS muaji,
       count(*) AS n,
       round(avg(tot_pritur), 3) AS lam_mes,
       round(avg(tot_real::float8)::numeric, 3) AS real_mes,
       round((avg(tot_pritur) - avg(tot_real::float8))::numeric, 3) AS gabimi,
       count(*) FILTER (WHERE tot_pritur >= 3.26) AS n_decili10,
       round(avg(tot_pritur) FILTER (WHERE tot_pritur >= 3.26), 3) AS d10_lam,
       round(avg(tot_real::float8) FILTER (WHERE tot_pritur >= 3.26)::numeric, 3) AS d10_real
FROM v_analiza_rreze
WHERE tot_pritur IS NOT NULL AND data IS NOT NULL
GROUP BY 1
ORDER BY 1;


-- ==================== PYETJA 4 ====================
SELECT to_char(v.data::date, 'YYYY-MM') AS muaji,
       count(*) AS n,
       round(avg((a.tregjet_full::jsonb ->> 'Over 2.5')::numeric), 4) AS premtuar,
       round(avg(CASE WHEN v.tot_real > 2.5 THEN 1.0 ELSE 0.0 END), 4) AS ndodhi,
       round(avg((a.tregjet_full::jsonb ->> 'Over 2.5')::numeric)
             - avg(CASE WHEN v.tot_real > 2.5 THEN 1.0 ELSE 0.0 END), 4) AS gabimi
FROM v_analiza_rreze v
JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
WHERE v.data IS NOT NULL
  AND a.tregjet_full::jsonb ? 'Over 2.5'
GROUP BY 1
ORDER BY 1;
