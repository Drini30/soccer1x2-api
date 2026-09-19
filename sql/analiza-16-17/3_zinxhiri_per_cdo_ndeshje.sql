-- ========================================================================
-- 3) ZINXHIRI I PERLLOGARITJES — ndeshje per ndeshje, vlere per vlere
-- Ekzekutoje VETEM kete skedar. Eksportoje si CSV.
-- ========================================================================
-- Kjo eshte matja qe kerkove: jo mesatare, po rruga e plote e CDO ndeshjeje —
-- nga kuota te tregu i devigosur, te xG, te vendimi i modulit te fituesit, te
-- skori i publikuar, dhe perballe tij realiteti.
--
-- KOLONAT KRYESORE:
--   p1_treg/px_treg/p2_treg  tregu pa marzh (baza e vendimit te drejtimit)
--   diferenca                p_fitues - p_barazim; mbi 0.12 -> drejtimi detyrohet
--   moduli_kerkoi            drejtimi qe caktoi moduli i fituesit
--   drejtimi_yne / real      cfare dhame dhe cfare ndodhi
--   totali_yne / real        aty eshte kufizuesi: drejtimin e gjejme, totalin jo

WITH b AS (
  SELECT
    p.data, p.ora, p.ndeshja, p.liga_emri, p.statusi, p.is_premium,
    p.rezultati_sakt, p.rezultati, p.besueshmeria,
    COALESCE(NULLIF(p.training_data->>'build',''),'(pa vule)')      AS build,
    NULLIF(regexp_replace(p.koef_1::text,'[^0-9.]','','g'),'')::numeric AS k1,
    NULLIF(regexp_replace(p.koef_x::text,'[^0-9.]','','g'),'')::numeric AS kx,
    NULLIF(regexp_replace(p.koef_2::text,'[^0-9.]','','g'),'')::numeric AS k2,
    NULLIF(regexp_replace(p.koef_rez_sakt::text,'[^0-9.]','','g'),'')::numeric AS koef_skori,
    (p.training_data->>'xg_1')::numeric                              AS xg1,
    (p.training_data->>'xg_2')::numeric                              AS xg2,
    (p.training_data->'prob_1x2_mc'->>'p1')::numeric                 AS mc_p1,
    (p.training_data->'prob_1x2_mc'->>'px')::numeric                 AS mc_px,
    (p.training_data->'prob_1x2_mc'->>'p2')::numeric                 AS mc_p2,
    p.training_data->>'burimi_xg'                                    AS burimi_xg,
    split_part(p.rezultati_sakt,'-',1)::int                          AS g1,
    split_part(p.rezultati_sakt,'-',2)::int                          AS g2,
    NULLIF(split_part(replace(p.rezultati,' ',''),'-',1),'')::int     AS r1,
    NULLIF(split_part(replace(p.rezultati,' ',''),'-',2),'')::int     AS r2
  FROM predictions p
  WHERE p.data IN ('2026-09-16','2026-09-17')
    AND p.rezultati_sakt ~ '^[0-9]+-[0-9]+$'
),
d AS (
  SELECT *,
    (1/k1)/((1/k1)+(1/kx)+(1/k2)) AS p1t,
    (1/kx)/((1/k1)+(1/kx)+(1/k2)) AS pxt,
    (1/k2)/((1/k1)+(1/kx)+(1/k2)) AS p2t
  FROM b WHERE k1 > 1 AND kx > 1 AND k2 > 1
)
SELECT
  data, ora, ndeshja, liga_emri, build, is_premium,
  -- TREGU
  k1, kx, k2,
  round(p1t,3) AS p1_treg, round(pxt,3) AS px_treg, round(p2t,3) AS p2_treg,
  round(GREATEST(p1t,p2t) - pxt, 4) AS diferenca,
  CASE WHEN p1t >= p2t AND (p1t-pxt) > 0.12 THEN '1'
       WHEN p2t >  p1t AND (p2t-pxt) > 0.12 THEN '2'
       ELSE 'X (lire)' END            AS moduli_kerkoi,
  -- MODELI
  round(mc_p1,3) AS p1_model, round(mc_px,3) AS px_model, round(mc_p2,3) AS p2_model,
  round(xg1,2) AS xg_1, round(xg2,2) AS xg_2,
  round(xg1+xg2,2) AS totali_i_pritur, burimi_xg,
  -- OUTPUTI
  rezultati_sakt AS skori_yne, koef_skori, round(100.0/koef_skori,1) AS prob_skori_perqind,
  besueshmeria,
  -- REALITETI
  rezultati AS reali, statusi,
  CASE WHEN g1>g2 THEN '1' WHEN g2>g1 THEN '2' ELSE 'X' END AS drejtimi_yne,
  CASE WHEN r1 IS NULL THEN NULL
       WHEN r1>r2 THEN '1' WHEN r2>r1 THEN '2' ELSE 'X' END AS drejtimi_real,
  CASE WHEN r1 IS NULL THEN NULL
       WHEN (CASE WHEN g1>g2 THEN '1' WHEN g2>g1 THEN '2' ELSE 'X' END)
          = (CASE WHEN r1>r2 THEN '1' WHEN r2>r1 THEN '2' ELSE 'X' END)
       THEN 1 ELSE 0 END                                     AS drejtimi_ok,
  CASE WHEN r1 IS NULL THEN NULL
       WHEN g1=r1 AND g2=r2 THEN 1 ELSE 0 END                AS skori_ok,
  (g1+g2)                                                    AS totali_yne,
  (r1+r2)                                                    AS totali_real,
  ((r1+r2) - (g1+g2))                                        AS gabimi_totalit
FROM d
ORDER BY data, ora, ndeshja;
