-- ==========================================================
-- FAZA 1 — DREJTIMI: cili burim duhet ta zgjedhë fituesin?
-- ==========================================================
-- Rregulli i fituesit (rreshti 5545) lexon `prob_1x2` të llogaritur te rreshti
-- 5499 — probabilitetet e Monte Carlo-s PA treg. Përzierja me tregun ndodh te
-- rreshti 5961, PASI funksioni ka kthyer tashmë skorin.
--
-- Dhe dimë se tregu e mund modelin te 1X2: log-loss 0.9760 kundrejt 1.0095,
-- t = 2.33, p = 0.020 (koment te rreshti 5951).
--
-- Pra drejtimi i skorit vendoset nga burimi më i dobët, ndërsa ai më i mirë
-- llogaritet dy rreshta më poshtë dhe s'përdoret. Kjo e mat atë humbje.
--
-- KATËR ZGJEDHËS krahasohen mbi TË NJËJTAT ndeshje:
--   pub    = drejtimi i skorit që u publikua vërtet
--   mc     = argmax i probabiliteteve të Monte Carlo-s   (ç'përdor rregulli SOT)
--   blend  = argmax i probabiliteteve të përziera        (ç'DUHET të përdorte)
--   treg   = argmax i tregut të pastër                   (kufiri i sipërm)
--
-- ⚠️ KËRKON VIEW-n `v_analiza_rreze`.
-- ⚠️ `mesat_devijim_1x2` doli 0.0325 te kontrolli i shëndetit, pra `mc_p*` janë
--    të besueshëm. Pa atë verifikim kjo matje s'do të vlente.
-- ==========================================================


-- ══════════════════════════════════════════════════════════
-- PYETJA K — SAKTËSIA E DREJTIMIT, KATËR BURIME
-- ══════════════════════════════════════════════════════════
-- SI TA LEXOSH: nëse `blend_pct` > `mc_pct`, atëherë kalimi i rregullit të
-- fituesit te probabilitetet e përziera është fitim i drejtpërdrejtë, dhe
-- ndryshimi është tre rreshta kodi.
--
-- `treg_pct` është kufiri: askush s'e kalon dot tregun me këto të dhëna.
-- Nëse `blend_pct` afrohet me `treg_pct`, përzierja 0.35 është e mjaftueshme.
-- Nëse mbetet larg, `W_MKT_FINAL` duhet ngritur.
WITH x AS (
    SELECT match_id,
           CASE WHEN r1 > r2 THEN '1' WHEN r1 < r2 THEN '2' ELSE 'X' END AS reali,
           CASE WHEN p1g > p2g THEN '1' WHEN p1g < p2g THEN '2' ELSE 'X' END AS pub,
           CASE WHEN mc_p1 >= mc_px AND mc_p1 >= mc_p2 THEN '1'
                WHEN mc_p2 >  mc_p1 AND mc_p2 >= mc_px THEN '2'
                ELSE 'X' END                                              AS mc,
           CASE WHEN prob_1 >= prob_x AND prob_1 >= prob_2 THEN '1'
                WHEN prob_2 >  prob_1 AND prob_2 >= prob_x THEN '2'
                ELSE 'X' END                                              AS blend,
           CASE WHEN pm_1 >= pm_x AND pm_1 >= pm_2 THEN '1'
                WHEN pm_2 >  pm_1 AND pm_2 >= pm_x THEN '2'
                ELSE 'X' END                                              AS treg
    FROM v_analiza_rreze
    WHERE mc_p1 IS NOT NULL AND prob_1 IS NOT NULL
)
SELECT count(*)                                                    AS n,
       round(100.0*count(*) FILTER (WHERE pub   = reali)/count(*), 2) AS pub_pct,
       round(100.0*count(*) FILTER (WHERE mc    = reali)/count(*), 2) AS mc_pct,
       round(100.0*count(*) FILTER (WHERE blend = reali)/count(*), 2) AS blend_pct,
       round(100.0*count(*) FILTER (WHERE treg  = reali)/count(*), 2) AS treg_pct,
       count(*) FILTER (WHERE mc <> blend)                          AS sa_here_ndryshojne
FROM x;


-- ══════════════════════════════════════════════════════════
-- PYETJA L — TESTI I ÇIFTUAR: blend kundrejt mc
-- ══════════════════════════════════════════════════════════
-- Numërohen VETËM ndeshjet ku dy burimet zgjedhin drejtim të ndryshëm.
-- Kjo është matja që vendos nëse ndryshimi bëhet apo jo.
--
--   chi2 > 3.84 → p < 0.05 → bëje ndryshimin
--   chi2 < 2.71 → nuk provohet → mos e prek
WITH x AS (
    SELECT CASE WHEN r1 > r2 THEN '1' WHEN r1 < r2 THEN '2' ELSE 'X' END AS reali,
           CASE WHEN mc_p1 >= mc_px AND mc_p1 >= mc_p2 THEN '1'
                WHEN mc_p2 >  mc_p1 AND mc_p2 >= mc_px THEN '2'
                ELSE 'X' END                                              AS mc,
           CASE WHEN prob_1 >= prob_x AND prob_1 >= prob_2 THEN '1'
                WHEN prob_2 >  prob_1 AND prob_2 >= prob_x THEN '2'
                ELSE 'X' END                                              AS blend
    FROM v_analiza_rreze
    WHERE mc_p1 IS NOT NULL AND prob_1 IS NOT NULL
)
SELECT count(*)                                                    AS n,
       count(*) FILTER (WHERE mc = reali AND blend <> reali)        AS vetem_mc,
       count(*) FILTER (WHERE blend = reali AND mc <> reali)        AS vetem_blend,
       round(100.0*(count(*) FILTER (WHERE blend = reali)
                  - count(*) FILTER (WHERE mc = reali))/count(*), 2) AS fitimi_pp,
       CASE WHEN (count(*) FILTER (WHERE mc = reali AND blend <> reali)
                + count(*) FILTER (WHERE blend = reali AND mc <> reali)) > 0
            THEN round(power(abs(count(*) FILTER (WHERE mc = reali AND blend <> reali)
                               - count(*) FILTER (WHERE blend = reali AND mc <> reali))::numeric - 1, 2)
                       / (count(*) FILTER (WHERE mc = reali AND blend <> reali)
                        + count(*) FILTER (WHERE blend = reali AND mc <> reali)), 3)
       END                                                          AS chi2
FROM x;


-- ══════════════════════════════════════════════════════════
-- PYETJA M — A KA ANIM DREJT VENDASIT?
-- ══════════════════════════════════════════════════════════
-- Brenda rrezes, skori i publikuar jep vendas 50.0% ndërsa realiteti 44.0%.
-- Por kjo NUK është domosdo gabim: kush zgjedh gjithnjë favoritin publikon
-- më shumë favoritë nga sa fitojnë. Krahasimi i drejtë është me `mc` dhe
-- `blend`, jo me realitetin.
--
-- Nëse `pub` jep dukshëm më shumë '1' se `blend`, atëherë animi vjen nga
-- SHTRESAT, jo nga probabilitetet — dhe dyshimi kryesor është rreshti 5561:
-- kur rrumbullakosja e xG jep barazim, `+1` i shkon favoritit.
WITH x AS (
    SELECT CASE WHEN r1 > r2 THEN '1' WHEN r1 < r2 THEN '2' ELSE 'X' END AS reali,
           CASE WHEN p1g > p2g THEN '1' WHEN p1g < p2g THEN '2' ELSE 'X' END AS pub,
           CASE WHEN mc_p1 >= mc_px AND mc_p1 >= mc_p2 THEN '1'
                WHEN mc_p2 >  mc_p1 AND mc_p2 >= mc_px THEN '2'
                ELSE 'X' END                                              AS mc,
           CASE WHEN prob_1 >= prob_x AND prob_1 >= prob_2 THEN '1'
                WHEN prob_2 >  prob_1 AND prob_2 >= prob_x THEN '2'
                ELSE 'X' END                                              AS blend
    FROM v_analiza_rreze
    WHERE mc_p1 IS NOT NULL AND prob_1 IS NOT NULL
),
t AS (SELECT count(*)::numeric AS n FROM x)
SELECT 'reale'::text AS burimi,
       round(100.0*(SELECT count(*) FROM x WHERE reali='1')/t.n, 1) AS pct_1,
       round(100.0*(SELECT count(*) FROM x WHERE reali='X')/t.n, 1) AS pct_x,
       round(100.0*(SELECT count(*) FROM x WHERE reali='2')/t.n, 1) AS pct_2
FROM t
UNION ALL SELECT 'publikuar',
       round(100.0*(SELECT count(*) FROM x WHERE pub='1')/t.n, 1),
       round(100.0*(SELECT count(*) FROM x WHERE pub='X')/t.n, 1),
       round(100.0*(SELECT count(*) FROM x WHERE pub='2')/t.n, 1) FROM t
UNION ALL SELECT 'mc (pa treg)',
       round(100.0*(SELECT count(*) FROM x WHERE mc='1')/t.n, 1),
       round(100.0*(SELECT count(*) FROM x WHERE mc='X')/t.n, 1),
       round(100.0*(SELECT count(*) FROM x WHERE mc='2')/t.n, 1) FROM t
UNION ALL SELECT 'blend (me treg)',
       round(100.0*(SELECT count(*) FROM x WHERE blend='1')/t.n, 1),
       round(100.0*(SELECT count(*) FROM x WHERE blend='X')/t.n, 1),
       round(100.0*(SELECT count(*) FROM x WHERE blend='2')/t.n, 1) FROM t;


-- ══════════════════════════════════════════════════════════
-- PYETJA N — SA GJERË E DI TREGU TOTALIN? (baza e Fazës 2)
-- ══════════════════════════════════════════════════════════
-- Rreshtat 4704-4705 e nxjerrin totalin e tregut si 0.20 + (1 − px)·3.10,
-- pra vetëm nga probabiliteti i barazimit — diapazon ~0.37 gola për të gjithë
-- futbollin. Kuotat Over/Under, që e dinë totalin drejtpërdrejt, s'preken fare.
--
-- Kjo e mat sa informacion ka aty. `p_over_treg` është Over 2.5 i tregut pas
-- heqjes së marzhit. Nëse `korr_me_realen` është dukshëm mbi korrelacionin e
-- modelit me totalin (0.3100 nga PYETJA G), atëherë Faza 2 sjell sinjal të ri
-- dhe jo thjesht shtrirje zhurme.
--
-- `sd_p_over` tregon sa lëviz tregu mes ndeshjeve — krahasoje me sd-në e
-- modelit (0.361 në gola). Nëse tregu lëviz shumë më tepër, aty është burimi.
SELECT count(*)                                                        AS n,
       round(avg(po.p_over)::numeric, 4)                               AS p_over_mes,
       round(stddev_samp(po.p_over)::numeric, 4)                       AS sd_p_over,
       round(avg(CASE WHEN po.tot_real > 2.5 THEN 1.0 ELSE 0.0 END)::numeric, 4) AS ndodhi,
       round(corr(po.p_over, (po.tot_real)::float8)::numeric, 4)       AS korr_me_realen,
       round(corr(po.p_over, po.tot_pritur::float8)::numeric, 4)       AS korr_me_modelin
FROM (
    SELECT v.tot_real,
           v.tot_pritur,
           (1.0/(a.odds_reale::jsonb #>> '{OU,2.5,over}')::float8)
             / NULLIF((1.0/(a.odds_reale::jsonb #>> '{OU,2.5,over}')::float8)
                    + (1.0/(a.odds_reale::jsonb #>> '{OU,2.5,under}')::float8), 0) AS p_over
    FROM v_analiza_rreze v
    JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
    WHERE (a.odds_reale::jsonb #>> '{OU,2.5,over}')  ~ '^[0-9.]+$'
      AND (a.odds_reale::jsonb #>> '{OU,2.5,under}') ~ '^[0-9.]+$'
) po;
-- ⚠️ Struktura e `odds_reale` mund të mos jetë {OU:{2.5:{over,under}}}. Nëse kjo
--    kthen 0 rreshta, ekzekuto këtë dhe ma nis rezultatin që ta rregulloj rrugën:
--
--    SELECT jsonb_pretty(odds_reale::jsonb) FROM arkiv_rezultatesh
--    WHERE odds_reale::jsonb <> '{}'::jsonb ORDER BY data DESC LIMIT 1;
