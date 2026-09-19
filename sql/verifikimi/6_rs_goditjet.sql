-- ========================================================================
-- GODITJET E REZULTATIT TE SAKTE — rikontroll pasi mbarojne ndeshjet
-- ========================================================================
-- Ekzekutoje VETEM kete skedar (Supabase kthen vetem pyetjen e fundit).
--
-- Cfare pergjigjet:
--   1) Sa RS goditem, per dite dhe gjithsej.
--   2) Cilat goditen — dhe nga ato, cilat ishin JASHTE rregullit te tregut
--      (skori yne kundershtonte favoritin e qarte) e megjithate dolen sakte.
--      Keto jane rastet interesante: ose fat, ose modeli pa dicka qe tregu
--      s'e cmonte.
--
-- Rregulli i tregut eshte i njejti i verifikimeve 1 dhe 2: favorit i qarte
-- kur (p_favorit − p_barazim) > 0.12.
-- ========================================================================

WITH parametrat AS (
  -- ▼▼ NDRYSHO VETEM KETU ▼▼  (perfshirese ne te dy skajet)
  SELECT DATE '2026-09-15' AS nga, DATE '2026-09-19' AS deri
),
b AS (
  SELECT
    p.data::date                                   AS data,
    p.ora, p.ndeshja, p.liga_emri,
    p.rezultati_sakt                               AS skori_yne,
    p.rezultati                                    AS reali,
    NULLIF(regexp_replace(p.koef_1::text, '[^0-9.]', '', 'g'), '')::numeric AS k1,
    NULLIF(regexp_replace(p.koef_x::text, '[^0-9.]', '', 'g'), '')::numeric AS kx,
    NULLIF(regexp_replace(p.koef_2::text, '[^0-9.]', '', 'g'), '')::numeric AS k2,
    split_part(p.rezultati_sakt, '-', 1)::int      AS g1,
    split_part(p.rezultati_sakt, '-', 2)::int      AS g2,
    split_part(p.rezultati,      '-', 1)::int      AS r1,
    split_part(p.rezultati,      '-', 2)::int      AS r2
  FROM predictions p, parametrat par
  WHERE p.data::date BETWEEN par.nga AND par.deri
    AND p.rezultati_sakt ~ '^[0-9]+-[0-9]+$'
    AND p.rezultati      ~ '^[0-9]+-[0-9]+$'      -- vetem ndeshjet e mbaruara
),
d AS (
  SELECT *,
    (1/k1) / ((1/k1)+(1/kx)+(1/k2)) AS p1,
    (1/kx) / ((1/k1)+(1/kx)+(1/k2)) AS px,
    (1/k2) / ((1/k1)+(1/kx)+(1/k2)) AS p2
  FROM b
  WHERE k1 > 1 AND kx > 1 AND k2 > 1
),
v AS (
  SELECT *,
    CASE WHEN g1 = r1 AND g2 = r2 THEN 1 ELSE 0 END AS rs_goditi,
    CASE WHEN g1 > g2 THEN '1' WHEN g2 > g1 THEN '2' ELSE 'X' END AS shenja_jone,
    CASE WHEN r1 > r2 THEN '1' WHEN r2 > r1 THEN '2' ELSE 'X' END AS shenja_reale,
    CASE WHEN p1 >= p2 AND (p1 - px) > 0.12 THEN '1'
         WHEN p2 >  p1 AND (p2 - px) > 0.12 THEN '2'
         ELSE 'X' END AS kerkon_tregu
  FROM d
)
SELECT
  data,
  ora,
  ndeshja,
  liga_emri                                        AS liga,
  skori_yne,
  reali,
  CASE WHEN rs_goditi = 1 THEN '✔ RS'  ELSE '' END AS rs,
  shenja_jone,
  shenja_reale,
  CASE WHEN shenja_jone = shenja_reale THEN '✔ 1X2' ELSE '' END AS njesh_x_dysh,
  kerkon_tregu,
  CASE WHEN kerkon_tregu = 'X'              THEN 'pa favorit te qarte'
       WHEN shenja_jone = kerkon_tregu      THEN 'brenda rregullit'
       ELSE 'JASHTE rregullit' END                 AS ndaj_tregut,
  -- Rasti qe kerkohet: e shkelem rregullin dhe prape e goditem RS-ne
  CASE WHEN rs_goditi = 1 AND kerkon_tregu <> 'X' AND shenja_jone <> kerkon_tregu
       THEN '★ goditje jashte rregullit' ELSE '' END AS shenim,
  -- Permbledhja e dites, e mbartur ne cdo rresht (pa pyetje te dyte)
  count(*)        OVER (PARTITION BY data)         AS dita_ndeshje,
  sum(rs_goditi)  OVER (PARTITION BY data)         AS dita_rs,
  round(100.0 * sum(rs_goditi) OVER (PARTITION BY data)
        / count(*) OVER (PARTITION BY data), 1)    AS dita_rs_perqind,
  -- Permbledhja e gjithe periudhes
  count(*)        OVER ()                          AS gjithsej_ndeshje,
  sum(rs_goditi)  OVER ()                          AS gjithsej_rs,
  round(100.0 * sum(rs_goditi) OVER () / count(*) OVER (), 1) AS gjithsej_rs_perqind
FROM v
ORDER BY rs_goditi DESC, data DESC, ora;

-- LEXIMI:
--   • Rreshtat e pare jane goditjet (rs_goditi DESC).
--   • Kolona 'shenim' shenon me ★ ato qe goditen edhe pse skori yne
--     kundershtonte favoritin e qarte te tregut.
--   • 'dita_rs_perqind' dhe 'gjithsej_rs_perqind' perseriten ne cdo rresht;
--     lexoji nje here, jane totale, jo per rresht.
--   • Nese nje ndeshje e mbaruar nuk del fare ketu, i mungon 'rezultati' ne
--     baze — ekzekuto rifreskimin e rezultateve dhe provoje perseri.
