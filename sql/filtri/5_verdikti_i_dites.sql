-- ========================================================================
-- 5) VERDIKTI I NJE DITE — tabela 2x2, me TE DY perkufizimet
-- Ekzekutoje VETEM kete skedar.  ⬇ NDRYSHO DATEN
-- ========================================================================
-- Kthen DY rreshta. Nese te dy tregojne te njejten gje, perfundimi eshte i
-- qendrueshem. Nese ndryshojne shume, ndotja e 18 shtatorit po e drejton
-- rezultatin — dhe atehere vlen vetem rreshti B.
--
-- Me kater numrat e secilit rresht llogaritet testi Fisher.

WITH b AS (
  SELECT
    p.is_premium,
    NULLIF(regexp_replace(p.koef_rez_sakt::text,'[^0-9.]','','g'),'')::numeric AS koef,
    split_part(p.rezultati_sakt,'-',1)::int AS g1,
    split_part(p.rezultati_sakt,'-',2)::int AS g2,
    NULLIF(split_part(replace(p.rezultati,' ',''),'-',1),'')::int AS r1,
    NULLIF(split_part(replace(p.rezultati,' ',''),'-',2),'')::int AS r2
  FROM predictions p
  WHERE p.data = '2026-09-18'
    AND p.rezultati_sakt ~ '^[0-9]+-[0-9]+$'
    AND p.koef_rez_sakt IS NOT NULL
    AND p.statusi IN ('FT','AET','PEN','AWD','WO')
    AND p.rezultati IS NOT NULL
    AND replace(p.rezultati,' ','') ~ '^[0-9]+-[0-9]+$'
),
r AS (
  SELECT *,
    row_number() OVER (ORDER BY koef ASC) AS vendi,
    CASE WHEN g1=r1 AND g2=r2 THEN 1 ELSE 0 END AS skor_ok,
    CASE WHEN (CASE WHEN g1>g2 THEN 1 WHEN g2>g1 THEN 2 ELSE 0 END)
            = (CASE WHEN r1>r2 THEN 1 WHEN r2>r1 THEN 2 ELSE 0 END) THEN 1 ELSE 0 END AS drejt_ok
  FROM b
),
dy AS (
  SELECT 'A. si eshte SHENUAR' AS perkufizimi, is_premium AS brenda, skor_ok, drejt_ok FROM r
  UNION ALL
  SELECT 'B. maja e VERTETE',  (vendi <= 10),  skor_ok, drejt_ok FROM r
)
SELECT
  perkufizimi,
  count(*)                                             AS ndeshje_gjithsej,
  count(*) FILTER (WHERE brenda)                       AS brenda_n,
  sum(skor_ok) FILTER (WHERE brenda)                   AS brenda_skor,
  count(*) FILTER (WHERE NOT brenda)                   AS jashte_n,
  sum(skor_ok) FILTER (WHERE NOT brenda)               AS jashte_skor,
  round(100.0*sum(skor_ok) FILTER (WHERE brenda)
        / NULLIF(count(*) FILTER (WHERE brenda),0),1)          AS brenda_pct,
  round(100.0*sum(skor_ok) FILTER (WHERE NOT brenda)
        / NULLIF(count(*) FILTER (WHERE NOT brenda),0),1)      AS jashte_pct,
  sum(drejt_ok) FILTER (WHERE brenda)                  AS brenda_drejt,
  sum(drejt_ok) FILTER (WHERE NOT brenda)              AS jashte_drejt,
  round(100.0*sum(drejt_ok) FILTER (WHERE brenda)
        / NULLIF(count(*) FILTER (WHERE brenda),0),1)          AS brenda_drejt_pct,
  round(100.0*sum(drejt_ok) FILTER (WHERE NOT brenda)
        / NULLIF(count(*) FILTER (WHERE NOT brenda),0),1)      AS jashte_drejt_pct
FROM dy
GROUP BY perkufizimi
ORDER BY perkufizimi;
