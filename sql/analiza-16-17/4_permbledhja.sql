-- ========================================================================
-- 4) PERMBLEDHJA — sa goditem, dhe ku eshte kufizuesi
-- Ekzekutoje VETEM kete skedar.
-- ========================================================================
-- Ndarja premium/jo-premium eshte thelbi: nese filtri punon, rreshti premium
-- duhet te jete DUKSHEM me i mire se ai i pergjithshem. Perndryshe filtri s'po
-- ben asgje pervec qe zvogelon numrin e ndeshjeve.

WITH b AS (
  SELECT
    p.data, p.is_premium,
    split_part(p.rezultati_sakt,'-',1)::int AS g1,
    split_part(p.rezultati_sakt,'-',2)::int AS g2,
    NULLIF(split_part(replace(p.rezultati,' ',''),'-',1),'')::int AS r1,
    NULLIF(split_part(replace(p.rezultati,' ',''),'-',2),'')::int AS r2
  FROM predictions p
  WHERE p.data IN ('2026-09-16','2026-09-17')
    AND p.rezultati_sakt ~ '^[0-9]+-[0-9]+$'
    AND p.rezultati IS NOT NULL
    AND replace(p.rezultati,' ','') ~ '^[0-9]+-[0-9]+$'
)
SELECT
  data,
  CASE WHEN is_premium THEN 'PREMIUM (te shitura)' ELSE 'te tjerat' END AS grupi,
  count(*) AS ndeshje,
  -- DREJTIMI
  count(*) FILTER (WHERE (CASE WHEN g1>g2 THEN '1' WHEN g2>g1 THEN '2' ELSE 'X' END)
                       = (CASE WHEN r1>r2 THEN '1' WHEN r2>r1 THEN '2' ELSE 'X' END)) AS drejtim_ok,
  round(100.0*count(*) FILTER (WHERE (CASE WHEN g1>g2 THEN '1' WHEN g2>g1 THEN '2' ELSE 'X' END)
                                   = (CASE WHEN r1>r2 THEN '1' WHEN r2>r1 THEN '2' ELSE 'X' END))
        / NULLIF(count(*),0), 1) AS drejtim_perqind,
  -- SKORI I SAKTE
  count(*) FILTER (WHERE g1=r1 AND g2=r2) AS skor_ok,
  round(100.0*count(*) FILTER (WHERE g1=r1 AND g2=r2) / NULLIF(count(*),0), 1) AS skor_perqind,
  -- TOTALI (kufizuesi i matur: P(totali sakte) ~ 21.8%)
  count(*) FILTER (WHERE (g1+g2) = (r1+r2)) AS totali_ok,
  round(100.0*count(*) FILTER (WHERE (g1+g2)=(r1+r2)) / NULLIF(count(*),0), 1) AS totali_perqind,
  round(avg((r1+r2) - (g1+g2)), 2)  AS gabimi_mes_totalit,
  round(avg(abs((r1+r2) - (g1+g2))), 2) AS gabimi_absolut_totalit
FROM b
GROUP BY data, is_premium
ORDER BY data, is_premium DESC;
