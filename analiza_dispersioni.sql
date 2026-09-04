-- ==========================================================
-- NDJEKJE: A ËSHTË λ NËN-DISPERSUAR?
-- ==========================================================
-- Nga PYETJA 4 doli ky model, dhe ai është shkaku i gjithçkaje tjetër:
--
--   brezi        parashikuar   real     gabimi
--   < 2.2           2.03       1.73     +0.30  (mbivlerësim)
--   2.2-2.6         2.43       2.50     -0.07
--   2.6-3.0         2.79       2.68     +0.11
--   3.0-3.4         3.16       3.51     -0.35  (nënvlerësim)
--   >= 3.4          3.57       4.34     -0.77  (nënvlerësim i rëndë)
--
-- Modeli e ngjesh diapazonin: parashikon 2.03→3.57 kur realiteti bën 1.73→4.34.
-- Nga 5 mesataret e brezave del pjerrësi ≈ 1.51, ndërsa kalibrimi aktual mban
-- XG_NORM_B_HOME = 1.0621. Por një përllogaritje nga 5 pika të grupuara NUK
-- është provë — ajo e heq variancën brenda brezit dhe mund ta fryjë pjerrësinë.
-- PYETJA A e mat drejtpërdrejt, mbi çdo rresht, me gabimin standard.
--
-- ⚠️ KËRKON që VIEW-ja `v_analiza_rreze` të ekzistojë (PYETJA 0 e skedarit
--    të mëparshëm). Nëse e ke fshirë, rikrijoje.
-- ==========================================================


-- ══════════════════════════════════════════════════════════
-- PYETJA A — REGRESIONI I DREJTPËRDREJTË (kjo është prova)
-- ══════════════════════════════════════════════════════════
-- `B` = pjerrësia e `gola_realë ~ A + B · λ`.
--
--   B ≈ 1.00  → λ është i kalibruar mirë; s'ka nën-dispersion.
--   B > 1.00  → λ është NGJESHUR: parashikimet e ulëta duhen ulur më shumë dhe
--               ato të lartat ngritur më shumë. Sa më lart B, aq më e rëndë.
--   B < 1.00  → e kundërta (λ shumë i shpërndarë).
--
-- `se_B` = gabimi standard. Rëndësia lexohet kështu:
--   (B − 1.0) / se_B  > 2  → nën-dispersioni është real, jo zhurmë.
--
-- ⚠️ Rreshti 'TOTALI' dhe rreshtat 'VENDAS'/'MYSAFIR' mund të ndryshojnë shumë.
--    Kjo nuk është kontradiktë: λ_home dhe λ_away janë të korreluara NEGATIVISHT
--    (favorit i fortë = njëri lart, tjetri poshtë), ndaj varianca e SHUMËS është
--    shumë më e vogël se shuma e variancave. Autokalibrimi (rreshtat 7118-7124)
--    e përshtat VETËM secilën anë veç e veç — dispersionin e TOTALIT nuk e mat
--    kurrë askush. Prandaj rreshti 'TOTALI' është ai që ka rëndësi për diapazonin
--    e rezultateve, sepse totali vendos nëse 3-1 / 2-2 / 4-0 janë fare të arritshme.
SELECT 'TOTALI'::text                                                     AS madhesia,
       count(*)                                                           AS n,
       round(regr_slope(tot_real::float8, tot_pritur::float8)::numeric, 4)     AS b_pjerresia,
       round(regr_intercept(tot_real::float8, tot_pritur::float8)::numeric, 4) AS a_konstanta,
       round((sqrt((1 - regr_r2(tot_real::float8, tot_pritur::float8))
                   / (count(*) - 2)::float8)
              * stddev_samp(tot_real::float8)
              / stddev_samp(tot_pritur::float8))::numeric, 4)             AS se_b,
       round(regr_r2(tot_real::float8, tot_pritur::float8)::numeric, 4)   AS r2,
       round(stddev_samp(tot_pritur)::numeric, 3)                         AS sd_parashikuar,
       round(stddev_samp(tot_real::float8)::numeric, 3)                   AS sd_real,
       round(avg(tot_pritur)::numeric, 3)                                 AS mes_parashikuar,
       round(avg(tot_real::float8)::numeric, 3)                           AS mes_real
FROM v_analiza_rreze WHERE tot_pritur IS NOT NULL

UNION ALL

SELECT 'VENDAS (λ_home)',
       count(*),
       round(regr_slope(r1::float8, xg1::float8)::numeric, 4),
       round(regr_intercept(r1::float8, xg1::float8)::numeric, 4),
       round((sqrt((1 - regr_r2(r1::float8, xg1::float8)) / (count(*) - 2)::float8)
              * stddev_samp(r1::float8) / stddev_samp(xg1::float8))::numeric, 4),
       round(regr_r2(r1::float8, xg1::float8)::numeric, 4),
       round(stddev_samp(xg1)::numeric, 3),
       round(stddev_samp(r1::float8)::numeric, 3),
       round(avg(xg1)::numeric, 3),
       round(avg(r1::float8)::numeric, 3)
FROM v_analiza_rreze WHERE xg1 IS NOT NULL

UNION ALL

SELECT 'MYSAFIR (λ_away)',
       count(*),
       round(regr_slope(r2::float8, xg2::float8)::numeric, 4),
       round(regr_intercept(r2::float8, xg2::float8)::numeric, 4),
       round((sqrt((1 - regr_r2(r2::float8, xg2::float8)) / (count(*) - 2)::float8)
              * stddev_samp(r2::float8) / stddev_samp(xg2::float8))::numeric, 4),
       round(regr_r2(r2::float8, xg2::float8)::numeric, 4),
       round(stddev_samp(xg2)::numeric, 3),
       round(stddev_samp(r2::float8)::numeric, 3),
       round(avg(xg2)::numeric, 3),
       round(avg(r2::float8)::numeric, 3)
FROM v_analiza_rreze WHERE xg2 IS NOT NULL;


-- ══════════════════════════════════════════════════════════
-- PYETJA B — KURBA E KALIBRIMIT SIPAS DECILEVE
-- ══════════════════════════════════════════════════════════
-- E njëjta gjë si PYETJA A, por pa supozuar linearitet — 10 grupe të barabarta.
-- Nëse `gabimi` shkon nga POZITIV te decilet e ulëta drejt NEGATIV te ato të
-- larta në mënyrë monotone, nën-dispersioni është i konfirmuar dhe forma e tij
-- është lineare (pra rregullohet me një pjerrësi të vetme).
-- Nëse gabimi luan pa rregull, atëherë problemi s'është pjerrësia — mos e prek B.
SELECT ntile(10) OVER (ORDER BY tot_pritur)                    AS decili,
       count(*)                                                AS n,
       round(min(tot_pritur), 2)                               AS lam_nga,
       round(max(tot_pritur), 2)                               AS lam_deri,
       round(avg(tot_pritur), 3)                               AS lam_mes,
       round(avg(tot_real::float8)::numeric, 3)                AS real_mes,
       round((avg(tot_pritur) - avg(tot_real::float8))::numeric, 3) AS gabimi
FROM v_analiza_rreze
WHERE tot_pritur IS NOT NULL
GROUP BY decili
ORDER BY decili;
-- ⚠️ ntile() me GROUP BY nuk lejohet drejtpërdrejt në disa versione. Nëse
--    Postgres ankohet, përdor variantin e mëposhtëm (i njëjti rezultat):
--
-- WITH d AS (
--     SELECT tot_pritur, tot_real, ntile(10) OVER (ORDER BY tot_pritur) AS decili
--     FROM v_analiza_rreze WHERE tot_pritur IS NOT NULL
-- )
-- SELECT decili, count(*) AS n,
--        round(min(tot_pritur),2) AS lam_nga, round(max(tot_pritur),2) AS lam_deri,
--        round(avg(tot_pritur),3) AS lam_mes,
--        round(avg(tot_real::float8)::numeric,3) AS real_mes,
--        round((avg(tot_pritur) - avg(tot_real::float8))::numeric,3) AS gabimi
-- FROM d GROUP BY decili ORDER BY decili;


-- ══════════════════════════════════════════════════════════
-- PYETJA C — McNEMAR PËR SECILIN GRUP TË RREGULLIT
-- ══════════════════════════════════════════════════════════
-- Testi i përgjithshëm doli chi2 = 0.319 (p ≈ 0.57) — pra GJITHSEJ shtresat
-- s'kanë efekt të matshëm. Por ndarja tregoi diçka tjetër: te grupi 'vendas'
-- argmax-i goditi 15.74% kundrejt 12.65% të publikuarit (+3.09 pikë).
-- Kjo pyetësi thotë nëse ajo diferencë brenda grupit është reale apo zhurmë.
--
--   chi2 > 3.84 → p < 0.05   |   chi2 > 2.71 → p < 0.10   |   nën 2.71 → asgjë
SELECT coalesce(rregulli, 'pa kuota')                          AS grupi,
       count(*)                                                AS n,
       count(*) FILTER (WHERE goditi_pub  AND NOT goditi_amax) AS vetem_pub,
       count(*) FILTER (WHERE goditi_amax AND NOT goditi_pub)  AS vetem_amax,
       count(*) FILTER (WHERE goditi_pub  AND NOT goditi_amax)
     + count(*) FILTER (WHERE goditi_amax AND NOT goditi_pub)  AS diskordante,
       CASE WHEN (count(*) FILTER (WHERE goditi_pub  AND NOT goditi_amax)
                + count(*) FILTER (WHERE goditi_amax AND NOT goditi_pub)) > 0
            THEN round(power(abs(count(*) FILTER (WHERE goditi_pub  AND NOT goditi_amax)
                               - count(*) FILTER (WHERE goditi_amax AND NOT goditi_pub))::numeric - 1, 2)
                       / (count(*) FILTER (WHERE goditi_pub  AND NOT goditi_amax)
                        + count(*) FILTER (WHERE goditi_amax AND NOT goditi_pub)), 3)
       END                                                     AS chi2
FROM v_analiza_rreze
WHERE brenda_rreze
GROUP BY 1
ORDER BY 1;


-- ══════════════════════════════════════════════════════════
-- PYETJA D — E njëjta ndarje, por sipas TOTALIT TË PRITUR
-- ══════════════════════════════════════════════════════════
-- PYETJA 4 tregoi se shtresat DËMTOJNË te totalet e ulëta (13.51% kundrejt
-- 24.32%) dhe NDIHMOJNË te ato të larta (9.76% kundrejt 7.32%). Kjo e teston
-- atë me McNemar, sepse nëse qëndron, zgjidhja e lirë është t'i kushtëzojmë
-- shtresat me `tot_pritur` — pa prekur fare λ.
SELECT CASE WHEN tot_pritur < 2.6 THEN 'a) i ulet  (< 2.6)'
            WHEN tot_pritur < 3.0 THEN 'b) mesatar (2.6-3.0)'
            ELSE                       'c) i larte (>= 3.0)' END          AS brezi,
       count(*)                                                AS n,
       round(100.0*count(*) FILTER (WHERE goditi_pub)/count(*), 2)  AS gpub_pct,
       round(100.0*count(*) FILTER (WHERE goditi_amax)/count(*), 2) AS gmax_pct,
       count(*) FILTER (WHERE goditi_pub  AND NOT goditi_amax) AS vetem_pub,
       count(*) FILTER (WHERE goditi_amax AND NOT goditi_pub)  AS vetem_amax,
       CASE WHEN (count(*) FILTER (WHERE goditi_pub  AND NOT goditi_amax)
                + count(*) FILTER (WHERE goditi_amax AND NOT goditi_pub)) > 0
            THEN round(power(abs(count(*) FILTER (WHERE goditi_pub  AND NOT goditi_amax)
                               - count(*) FILTER (WHERE goditi_amax AND NOT goditi_pub))::numeric - 1, 2)
                       / (count(*) FILTER (WHERE goditi_pub  AND NOT goditi_amax)
                        + count(*) FILTER (WHERE goditi_amax AND NOT goditi_pub)), 3)
       END                                                     AS chi2
FROM v_analiza_rreze
WHERE brenda_rreze AND tot_pritur IS NOT NULL
GROUP BY 1
ORDER BY 1;


-- ══════════════════════════════════════════════════════════
-- PYETJA E — SHËNDETI (kjo mbeti pa ekzekutuar; duhet)
-- ══════════════════════════════════════════════════════════
-- Pa `mesat_devijim_1x2` nën 0.05, kolona `rregulli` — dhe rrjedhimisht i gjithë
-- konkluzioni për grupin 'vendas' — s'ka bazë. Ekzekutoje.
SELECT count(*)                                                        AS ndeshje,
       count(*) FILTER (WHERE n_skore <= 20)                           AS epoka_15,
       count(*) FILTER (WHERE n_skore >  20)                           AS epoka_40,
       round(avg(masa_ruajtur), 4)                                     AS masa_mes,
       count(*) FILTER (WHERE mc_p1 IS NULL)                           AS pa_kuota,
       round(avg(abs(mc_p1 - d_p1)) FILTER (WHERE mc_p1 IS NOT NULL), 4) AS mesat_devijim_1x2,
       count(*) FILTER (WHERE mc_p1 < -0.02 OR mc_p1 > 1.02
                        OR mc_px < -0.02 OR mc_px > 1.02)              AS mc_jashte_kufijve
FROM v_analiza_rreze;
