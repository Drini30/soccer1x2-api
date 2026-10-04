-- ========================================================================
-- KONTROLLI PAS DEPLOY-IT: a e mbajne rreshtat e rinj λ-n QE SIMULOHET?
-- Ekzekutoje VETEM kete skedar (nje pyetje e vetme).  ⬇ NDRYSHO 2 VLERAT te `param`
-- ========================================================================
-- training_data.xg_1/xg_2 = PARA XG_NORM dhe PARA blendit me O/U  -> NUK eshte λ.
-- training_data.lam_1/lam_2 = λ qe hyri ne simulim (e plote, pa rrumbullakim).
--
-- Kolonat e para (te njejta ne cdo rresht) jane permbledhja:
--   me_build_te_ri / build_i_ri_pa_lam -> rreshtat e shkruar nga kodi i ri; i dyti DUHET 0
--   pct_me_lam      -> pjesa me lam_1/lam_2 mes ndeshjeve me data >= data e deploy-it
--                      (ndeshjet e nisura para deploy-it s'rigjenerohen, ndaj s'e kane)
--   gjurma_e_publikimit -> gjurma (λ, top5, zgjedhja) eshte e PO atij gjenerimi qe dha
--                      rezultati_sakt + dist_gola + koef_rez_sakt e ngrira. VETEM keta
--                      rreshta lejohen ne analizen ndeshje-per-ndeshje "λ -> skori i publikuar".
--   gjurma_e_mevonshme -> training_data u rishkrua nga nje rigjenerim i mevonshem (kuotat/
--                      inputet levizen): λ eshte e fundit para fillimit, JO ajo e skorit te
--                      publikuar. Pritet te jene SHUMICA e ndeshjeve qe rigjenerohen.
--   prej_tyre_me_skor_te_njejte -> sa nga keto do t'i kishte pranuar gabimisht prova e
--                      thjeshte "zgjedhja.rez = rezultati_sakt" (skori mbetet, λ jo).
--   PROVA: zgjedhja.rez = rezultati_sakt  DHE  dist_gola::jsonb @> zgjedhja.dist_shenja
--          (dist_shenja = numrat int te top-5 + skorit, po ata qe ai gjenerim shkroi te
--          dist_gola; me te njejtat inpute dalin bit-per-bit njesoj).
--   dev_max_rindertimi -> |λ e ruajtur - λ e rindertuar nga xg_1 + A/B + shk_treg|; duhet
--                      < 0.001 (xg_1 ruhet me 3 shifra). XG_FLOOR supozohet 0.10.
--   build_i_ri_jashte_filtrit_09_1 -> rreshtat me vulen e re qe filtri i vjeter
--                      LIKE '2026-09-1%' (sql/filtri/2 dhe /3) i perjashton. Jane te
--                      numeruar atje VETEM nese vula e re u shtua te lista e atyre dy
--                      skedareve (filtri_build.patch). Pritet = me_build_te_ri.
-- Pas permbledhjes vijne deri ne 12 shembuj: xg_1 kundrejt lam_1, hap pas hapi.
--
-- Per arkiv_rezultatesh e njejta prove (dist_gola dhe parashikimi kopjohen te ngrira):
--   replace(a.parashikimi,' ','') = a.training_data->'zgjedhja'->>'rez'
--   AND a.dist_gola::jsonb @> (a.training_data->'zgjedhja'->'dist_shenja')
--   AND a.training_data->'zgjedhja'->'dist_shenja' <> '{}'::jsonb
--   (KLLAPAT jane te detyrueshme: @> dhe -> kane te njejten perparesi, pa to del gabim)

WITH param AS (
  SELECT '2026-10-03'::text                   AS data_deploy,   -- ⬅ dita e deploy-it
         '2026-10-03-lambda-e-simuluar'::text AS build_i_ri     -- ⬅ BUILD i deploy-it
),
baza AS (
  SELECT p.id, p.data, p.ndeshja, p.statusi,
         replace(COALESCE(p.rezultati_sakt, ''), ' ', '') AS rez_publikuar,
         p.dist_gola::jsonb                                AS dist_gola,
         p.training_data                                   AS td,
         q.build_i_ri
  FROM predictions p
  CROSS JOIN param q
  WHERE p.data::text >= q.data_deploy
    AND p.training_data IS NOT NULL
),
fushat AS (
  SELECT b.id, b.data, b.ndeshja, b.statusi, b.rez_publikuar,
         COALESCE(b.td->>'build', '(pa vule)')                      AS build,
         (b.td->>'build') IS NOT DISTINCT FROM b.build_i_ri          AS eshte_build_i_ri,
         ((b.td->>'lam_1') IS NOT NULL AND (b.td->>'lam_2') IS NOT NULL) AS ka_lam,
         (b.td->>'xg_1')::numeric                 AS xg_1,
         (b.td->>'xg_2')::numeric                 AS xg_2,
         (b.td->>'lam_n_1')::numeric              AS lam_n_1,
         (b.td->>'lam_n_2')::numeric              AS lam_n_2,
         (b.td->>'lam_1')::numeric                AS lam_1,
         (b.td->>'lam_2')::numeric                AS lam_2,
         (b.td->'xg_norm'->>'a_1')::numeric       AS a_1,
         (b.td->'xg_norm'->>'b_1')::numeric       AS b_1,
         (b.td->'xg_norm'->>'a_2')::numeric       AS a_2,
         (b.td->'xg_norm'->>'b_2')::numeric       AS b_2,
         (b.td->>'lam_treg')::numeric             AS lam_treg,
         (b.td->>'shk_treg')::numeric             AS shk_treg,
         COALESCE((b.td->>'boost')::numeric, 0)   AS boost,
         b.td->'zgjedhja'->>'rez'                 AS rez_gjenerimi,
         b.td->'zgjedhja'->>'rez_fit'             AS rez_fit,
         b.td->'zgjedhja'->>'rez_sim'             AS rez_sim,
         b.td->'zgjedhja'->>'drejtimi'            AS drejtimi,
         (b.td->'zgjedhja'->>'lean')::boolean     AS lean,
         (b.td->'zgjedhja'->>'fb')::boolean       AS fb,
         b.td->>'gjeneruar_ne'                    AS gjeneruar_ne,
         -- shenja e gjenerimit: e vlefshme vetem si objekt jo-bosh
         COALESCE(jsonb_typeof(b.td->'zgjedhja'->'dist_shenja') = 'object'
                  AND b.td->'zgjedhja'->'dist_shenja' <> '{}'::jsonb
                  AND b.dist_gola @> (b.td->'zgjedhja'->'dist_shenja'), false) AS dist_perputhet
  FROM baza b
),
-- rindertimi i zinxhirit (soccer_api.py: XG_NORM -> blendi O/U -> boost), hap pas hapi
r1 AS (
  SELECT f.*,
         LEAST(GREATEST(f.a_1 + f.b_1 * f.xg_1, 0.10), 5.00) AS n1,
         LEAST(GREATEST(f.a_2 + f.b_2 * f.xg_2, 0.10), 5.00) AS n2
  FROM fushat f
),
r2 AS (
  SELECT r.*,
         LEAST(GREATEST(r.n1 * COALESCE(r.shk_treg, 1), 0.10), 5.00) AS m1,
         LEAST(GREATEST(r.n2 * COALESCE(r.shk_treg, 1), 0.10), 5.00) AS m2
  FROM r1 r
),
r3 AS (
  SELECT r.*,
         LEAST(GREATEST(r.m1 - r.boost / 2, 0.10), 5.00) AS q1,
         LEAST(GREATEST(r.m2 + r.boost / 2, 0.10), 5.00) AS q2
  FROM r2 r
),
r4 AS (
  SELECT r.*,
         GREATEST(abs(r.q1 - r.lam_1), abs(r.q2 - r.lam_2))          AS dev_rindertimi,
         COALESCE(r.rez_gjenerimi = r.rez_publikuar, false)          AS rez_njejte,
         (COALESCE(r.rez_gjenerimi = r.rez_publikuar, false) AND r.dist_perputhet) AS gjurma_e_publikimit
  FROM r3 r
),
permbledhje AS (
  SELECT count(*)                                                       AS rreshta_pas_deploy,
         count(*) FILTER (WHERE eshte_build_i_ri)                       AS me_build_te_ri,
         count(*) FILTER (WHERE eshte_build_i_ri AND NOT ka_lam)        AS build_i_ri_pa_lam,
         count(*) FILTER (WHERE ka_lam)                                 AS me_lam,
         round(100.0 * count(*) FILTER (WHERE ka_lam) / NULLIF(count(*), 0), 1) AS pct_me_lam,
         count(*) FILTER (WHERE ka_lam AND gjurma_e_publikimit)         AS gjurma_e_publikimit,
         count(*) FILTER (WHERE ka_lam AND NOT gjurma_e_publikimit)     AS gjurma_e_mevonshme,
         count(*) FILTER (WHERE ka_lam AND NOT gjurma_e_publikimit AND rez_njejte) AS prej_tyre_me_skor_te_njejte,
         round(avg((lam_1 + lam_2) - (xg_1 + xg_2)) FILTER (WHERE ka_lam), 3) AS mes_lam_tot_minus_xg_tot,
         round(avg(lam_2 - lam_1) FILTER (WHERE ka_lam), 3)            AS mes_lam2_minus_lam1,
         round(avg(xg_2 - xg_1) FILTER (WHERE ka_lam), 3)              AS mes_xg2_minus_xg1,
         round(max(dev_rindertimi) FILTER (WHERE ka_lam), 4)           AS dev_max_rindertimi,
         count(*) FILTER (WHERE eshte_build_i_ri AND build NOT LIKE '2026-09-1%') AS build_i_ri_jashte_filtrit_09_1
  FROM r4
),
shembuj AS (
  SELECT data, ndeshja, statusi, build,
         xg_1, round(lam_n_1, 3) AS lam_n_1, round(lam_1, 3) AS lam_1, round(lam_1 - xg_1, 3) AS lam1_minus_xg1,
         xg_2, round(lam_n_2, 3) AS lam_n_2, round(lam_2, 3) AS lam_2, round(lam_2 - xg_2, 3) AS lam2_minus_xg2,
         lam_treg, shk_treg, boost,
         rez_fit, lean, rez_sim, fb, rez_gjenerimi, rez_publikuar,
         rez_njejte, dist_perputhet, gjurma_e_publikimit AS kjo_gjurme_eshte_e_publikimit,
         round(dev_rindertimi, 4) AS dev_rindertimi, gjeneruar_ne
  FROM r4
  WHERE ka_lam
  ORDER BY gjeneruar_ne DESC NULLS LAST, id
  LIMIT 12
)
SELECT p.*, s.*
FROM permbledhje p
LEFT JOIN shembuj s ON true
ORDER BY s.gjeneruar_ne DESC NULLS LAST, s.ndeshja;
