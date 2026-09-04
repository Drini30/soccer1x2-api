-- ==========================================================
-- RIPARAMETRIZIMI (TOTAL, SUPREMACI)
-- ==========================================================
-- PYETJA A e provoi nën-dispersionin: pjerrësia e totalit 1.5172 ± 0.1566
-- (3.30 sigma nga 1.0), ndërsa secila anë veç e veç është e kalibruar
-- (1.0626 dhe 1.0237 — të padallueshme nga 1.0).
--
-- Nga devijimet standarde del mekanizmi:
--     korr(λ_home, λ_away)      = −0.713
--     korr(gola_home, gola_away) = −0.044
-- Modeli imponon një shkëmbim mes dy anëve që realiteti nuk e ka. Ai e ndan
-- një total gati të fiksuar, në vend që ta parashikojë atë.
--
-- Pasoja algjebrike: një hartë affine për secilën anë do të duhej B = 1.0626
-- për vendasin dhe B = 1.5172 për totalin — i njëjti parametër në dy vlera.
-- Pra `B_HOME`/`B_AWAY` (rreshtat 7122/7124) NUK e rregullojnë dot totalin,
-- sado të kalibrohen. Duhet riparametrizim te (total, supremaci).
--
-- Këto pyetje japin numrat që duhen për ta shkruar atë ndryshim.
-- ⚠️ KËRKON VIEW-n `v_analiza_rreze`.
-- ==========================================================


-- ══════════════════════════════════════════════════════════
-- PYETJA F — PJERRËSITË NË BAZËN E RE (kjo jep parametrat)
-- ══════════════════════════════════════════════════════════
-- `TOTALI` e dimë: 1.5172. Këtu na duhet `SUPREMACIA`.
--
--   B_supremaci ≈ 1.0  → ana "kush fiton" është në rregull; prek vetëm totalin.
--   B_supremaci < 1.0  → supremacia është e ekzagjeruar (modeli i bën favoritët
--                        më të fortë nga ç'janë) — atëherë duhet shtrënguar.
--   B_supremaci > 1.0  → edhe supremacia është e ngjeshur.
--
-- `A` dhe `B` e secilit rresht janë pikërisht parametrat e hartës së re:
--     T' = A_total + B_total · (λ_h + λ_a)
--     S' = A_suprem + B_suprem · (λ_h − λ_a)
SELECT 'TOTALI  (λh + λa)'::text                                          AS madhesia,
       count(*)                                                           AS n,
       round(regr_slope((r1+r2)::float8, (xg1+xg2)::float8)::numeric, 4)     AS b_pjerresia,
       round(regr_intercept((r1+r2)::float8, (xg1+xg2)::float8)::numeric, 4) AS a_konstanta,
       round((sqrt((1 - regr_r2((r1+r2)::float8, (xg1+xg2)::float8))
                   / (count(*) - 2)::float8)
              * stddev_samp((r1+r2)::float8)
              / stddev_samp((xg1+xg2)::float8))::numeric, 4)              AS se_b,
       round(regr_r2((r1+r2)::float8, (xg1+xg2)::float8)::numeric, 4)     AS r2,
       round(stddev_samp((xg1+xg2)::float8)::numeric, 3)                  AS sd_parashikuar,
       round(stddev_samp((r1+r2)::float8)::numeric, 3)                    AS sd_real
FROM v_analiza_rreze WHERE xg1 IS NOT NULL

UNION ALL

SELECT 'SUPREMACIA (λh − λa)',
       count(*),
       round(regr_slope((r1-r2)::float8, (xg1-xg2)::float8)::numeric, 4),
       round(regr_intercept((r1-r2)::float8, (xg1-xg2)::float8)::numeric, 4),
       round((sqrt((1 - regr_r2((r1-r2)::float8, (xg1-xg2)::float8)) / (count(*) - 2)::float8)
              * stddev_samp((r1-r2)::float8) / stddev_samp((xg1-xg2)::float8))::numeric, 4),
       round(regr_r2((r1-r2)::float8, (xg1-xg2)::float8)::numeric, 4),
       round(stddev_samp((xg1-xg2)::float8)::numeric, 3),
       round(stddev_samp((r1-r2)::float8)::numeric, 3)
FROM v_analiza_rreze WHERE xg1 IS NOT NULL;


-- ══════════════════════════════════════════════════════════
-- PYETJA G — KORRELACIONI (prova e mekanizmit, një rresht)
-- ══════════════════════════════════════════════════════════
-- E llogarita nga devijimet standarde; kjo e mat drejtpërdrejt.
-- PRITET: korr_lambda ≈ −0.71, korr_reale ≈ −0.04.
--
-- Nëse dalin ashtu, shkaku është i konfirmuar dhe s'ka nevojë për hetim tjetër:
-- modeli po shpërndan një total fiks në vend që ta parashikojë.
SELECT count(*)                                                  AS n,
       round(corr(xg1::float8, xg2::float8)::numeric, 4)         AS korr_lambda,
       round(corr(r1::float8, r2::float8)::numeric, 4)           AS korr_reale,
       round(corr((xg1+xg2)::float8, (r1+r2)::float8)::numeric, 4) AS korr_total_parashikim,
       round(corr((xg1-xg2)::float8, (r1-r2)::float8)::numeric, 4) AS korr_suprem_parashikim
FROM v_analiza_rreze WHERE xg1 IS NOT NULL;


-- ══════════════════════════════════════════════════════════
-- PYETJA H — KURBA E KALIBRIMIT SIPAS DECILEVE (rregulluar)
-- ══════════════════════════════════════════════════════════
-- ⚠️ Versioni i mëparshëm dështoi: `window functions are not allowed in GROUP BY`.
--    Postgres e ndalon ntile() drejtpërdrejt te GROUP BY — decili duhet
--    llogaritur në një CTE më vete dhe grupimi bëhet mbi rezultatin e tij.
--
-- Kjo e teston nën-dispersionin PA supozuar se lidhja është lineare.
-- PRITET, nëse pjerrësia 1.5172 është e saktë: `gabimi` kalon nga POZITIV te
-- decilet e ulëta drejt NEGATIV te ato të larta, në mënyrë monotone.
-- `pas_rregullimit` tregon sa do të mbetej gabimi po ta zbatonim hartën e re —
-- duhet të bjerë afër zeros në të gjitha decilet.
WITH d AS (
    SELECT tot_pritur,
           tot_real,
           ntile(10) OVER (ORDER BY tot_pritur) AS decili
    FROM v_analiza_rreze
    WHERE tot_pritur IS NOT NULL
)
SELECT decili,
       count(*)                                                   AS n,
       round(min(tot_pritur), 2)                                  AS lam_nga,
       round(max(tot_pritur), 2)                                  AS lam_deri,
       round(avg(tot_pritur), 3)                                  AS lam_mes,
       round(avg(tot_real::float8)::numeric, 3)                   AS real_mes,
       round((avg(tot_pritur) - avg(tot_real::float8))::numeric, 3) AS gabimi,
       round((-1.3623 + 1.5172*avg(tot_pritur)
              - avg(tot_real::float8))::numeric, 3)               AS pas_rregullimit
FROM d
GROUP BY decili
ORDER BY decili;


-- ══════════════════════════════════════════════════════════
-- PYETJA I — SA DO TA ZGJERONTE DIAPAZONIN?
-- ══════════════════════════════════════════════════════════
-- Zbaton hartën e re mbi çdo ndeshje dhe numëron sa prej tyre do të kalonin në
-- secilin brez totali — pa e prekur kodin.
--
-- KJO ËSHTË PËRGJIGJJA E KËRKESËS TËNDE PËR 3-1 DHE 2-2:
-- ato skore kërkojnë λ_total > 3.6. Kolona `tani` tregon sa ndeshje e arrijnë
-- atë sot; `pas_rregullimit` tregon sa do ta arrinin. Nëse `tani` është afër
-- zeros dhe `pas` jo, diapazoni hapet vetvetiu, pa asnjë prag të ri.
--
-- `reale` është kontrolli: sa ndeshje e patën VËRTET atë total.
WITH x AS (
    SELECT tot_pritur                                   AS lam_tani,
           (-1.3623 + 1.5172*tot_pritur)                AS lam_pas,
           tot_real
    FROM v_analiza_rreze WHERE tot_pritur IS NOT NULL
),
brez AS (
    SELECT unnest(ARRAY['a) < 1.5','b) 1.5-2.5','c) 2.5-3.0',
                        'd) 3.0-3.6','e) >= 3.6']) AS brezi,
           unnest(ARRAY[-99.0, 1.5, 2.5, 3.0, 3.6])  AS nga,
           unnest(ARRAY[1.5, 2.5, 3.0, 3.6, 99.0])   AS deri
)
SELECT b.brezi,
       (SELECT count(*) FROM x WHERE x.lam_tani >= b.nga AND x.lam_tani < b.deri) AS tani,
       (SELECT count(*) FROM x WHERE x.lam_pas  >= b.nga AND x.lam_pas  < b.deri) AS pas_rregullimit,
       (SELECT count(*) FROM x WHERE x.tot_real >= b.nga AND x.tot_real < b.deri) AS reale
FROM brez b
ORDER BY b.brezi;


-- ══════════════════════════════════════════════════════════
-- PYETJA J — RREZIKU: a i prish rregullimi tregjet O/U?
-- ══════════════════════════════════════════════════════════
-- ⚠️ Ky ndryshim NUK prek vetëm skorin. Tregjet Over/Under dalin nga e njëjta
--    rrjetë H, ndaj ridispersimi i λ i lëviz TË GJITHA ato. Është sipërfaqja
--    më e madhe e rrezikut te ky ndryshim — dhe ndoshta edhe fitimi më i madh.
--
-- Kjo mat kalibrimin aktual të Over 2.5 sipas brezit të λ. Nëse nën-dispersioni
-- është real, pritet ky model: te totalet e ulëta modeli PREMTON më shumë Over
-- se sa ndodh, dhe te ato të larta premton më pak.
--
--   `premtuar` = probabiliteti mesatar që nxori modeli
--   `ndodhi`   = sa herë doli vërtet Over 2.5
--   `gabimi`   = premtuar − ndodhi. Nëse ndryshon shenjë nga brezi i ulët te i
--                larti, ridispersimi do ta ndreqë edhe këtë njëherësh.
SELECT CASE WHEN v.tot_pritur < 2.5 THEN 'a) lam < 2.5'
            WHEN v.tot_pritur < 3.0 THEN 'b) lam 2.5-3.0'
            ELSE                         'c) lam >= 3.0' END               AS brezi,
       count(*)                                                            AS n,
       round(avg((a.tregjet_full::jsonb ->> 'Over 2.5')::numeric), 4)      AS premtuar,
       round(avg(CASE WHEN v.tot_real > 2.5 THEN 1.0 ELSE 0.0 END), 4)     AS ndodhi,
       round(avg((a.tregjet_full::jsonb ->> 'Over 2.5')::numeric)
             - avg(CASE WHEN v.tot_real > 2.5 THEN 1.0 ELSE 0.0 END), 4)   AS gabimi
FROM v_analiza_rreze v
JOIN arkiv_rezultatesh a ON a.match_id = v.match_id
WHERE v.tot_pritur IS NOT NULL
  AND a.tregjet_full::jsonb ? 'Over 2.5'
GROUP BY 1
ORDER BY 1;
