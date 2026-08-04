-- ==========================================================
-- VERIFIKIM I PLOTË — pas deploy-it, migrimeve dhe nisjes së kuotave
-- ==========================================================
-- Ekzekutoji një nga një te Supabase → SQL Editor.
-- Te secili është shkruar ÇFARË PRITET; nëse del ndryshe, ai është problemi.
-- ==========================================================


-- ══════════════════════════════════════════════════════════
-- 1. A ekzistojnë të tre indekset e kuota_historik?
-- ══════════════════════════════════════════════════════════
-- PRITET: 3 rreshta — idx_kuota_hist_fixture, idx_kuota_hist_koha,
--         idx_kuota_hist_unik. Nëse mungon `_unik`, rregullimi s'u ekzekutua
--         dhe fotografitë e dyfishta s'bllokohen.
SELECT indexname FROM pg_indexes
WHERE tablename = 'kuota_historik' ORDER BY indexname;


-- ══════════════════════════════════════════════════════════
-- 2. A po mbërrijnë fotografitë?
-- ══════════════════════════════════════════════════════════
-- PRITET: fotografi > 0. Nëse 0, cron-i s'ka rënë ende ose kthen gabim —
--         provo me dorë /api/cron/kuotat?secret=... dhe shiko përgjigjen.
-- `minuta_para` duhet të jetë brenda 0-1440 (dritarja 24-orëshe).
SELECT count(*)                         AS fotografi,
       count(DISTINCT fixture_id)       AS ndeshje,
       count(DISTINCT marre_minute)     AS ekzekutime,
       min(marre_ne)                    AS e_para,
       max(marre_ne)                    AS e_fundit,
       min(minuta_para)                 AS min_para,
       max(minuta_para)                 AS max_para
FROM kuota_historik;


-- ══════════════════════════════════════════════════════════
-- 3. A po kapet LËVIZJA? (kjo është pyetja e vërtetë)
-- ══════════════════════════════════════════════════════════
-- Një fotografi për ndeshje s'tregon lëvizje. Duhen ≥2.
-- PRITET pas disa ekzekutimeve: shumica e ndeshjeve me 2+ fotografi.
-- Nëse TË GJITHA kanë vetëm 1, cron-i po ekzekutohet një herë të vetme —
--         kontrollo planifikimin (duhet çdo 30 min).
SELECT fotografi_per_ndeshje, count(*) AS sa_ndeshje
FROM (
    SELECT fixture_id, count(*) AS fotografi_per_ndeshje
    FROM kuota_historik GROUP BY fixture_id
) t
GROUP BY fotografi_per_ndeshje ORDER BY fotografi_per_ndeshje;


-- ══════════════════════════════════════════════════════════
-- 4. Lëvizjet më të mëdha të kapura deri tani
-- ══════════════════════════════════════════════════════════
-- Kjo është ajo që do të ushqejë matjen pas 4-8 javësh.
-- Në fillim do të jetë bosh ose me lëvizje ~0 — normale.
SELECT ndeshja, liga_emri,
       count(*)                            AS fotografi,
       min(minuta_para)                    AS me_afer,
       max(minuta_para)                    AS me_larg,
       round(min(k1)::numeric, 2)          AS k1_min,
       round(max(k1)::numeric, 2)          AS k1_max,
       round((max(k1) - min(k1))::numeric, 2) AS levizja_k1
FROM kuota_historik
GROUP BY ndeshja, liga_emri
HAVING count(*) >= 2
ORDER BY (max(k1) - min(k1)) DESC NULLS LAST
LIMIT 15;


-- ══════════════════════════════════════════════════════════
-- 5. A ka fotografi të dyfishta? (indeksi unik duhet t'i ketë bllokuar)
-- ══════════════════════════════════════════════════════════
-- PRITET: 0 rreshta.
SELECT fixture_id, bookmaker, marre_minute, count(*)
FROM kuota_historik
GROUP BY fixture_id, bookmaker, marre_minute
HAVING count(*) > 1;


-- ══════════════════════════════════════════════════════════
-- 6. TUBACIONI `api` — sa kolona i shkruan vërtet?
-- ══════════════════════════════════════════════════════════
-- count(kolonë) numëron vetëm jo-NULL-et.
-- Eksperimenti tregoi 0.0% mbulim; kjo pyetje thotë SAKTËSISHT cilat mungojnë,
-- që rregullimi të dijë ku të prekë.
SELECT count(*)                  AS gjithsej,
       count(home_forma_pts)     AS forma,
       count(home_avg_scored)    AS gola_mes,
       count(home_avg_scored_home) AS gola_vendas,
       count(home_avg_yellow)    AS kartona,
       count(home_volatility)    AS volatility,
       count(home_rest_days)     AS rest_days,
       count(odd_home)           AS kuota_1x2,
       count(ah_line)            AS ah,
       count(ou25_over)          AS ou25,
       count(tipi_ndeshjes)      AS tipi,
       count(gola_home)          AS rezultat_ft,
       count(gola_home_ht)       AS rezultat_ht
FROM historik_trajnimi WHERE burimi = 'api';


-- ══════════════════════════════════════════════════════════
-- 7. A shkruan ENDE tubacioni `api`?
-- ══════════════════════════════════════════════════════════
-- Data maksimale ishte 2026-03-31 ndërsa sot jemi në gusht 2026.
-- Nëse mbetet 2026-03-31, tubacioni ka NDALUAR prej ~4 muajsh — problem
-- tjetër nga ai i veçorive bosh, dhe më i rëndësishëm.
SELECT burimi,
       count(*)              AS rreshta,
       min(data_ndeshjes)    AS nga,
       max(data_ndeshjes)    AS deri,
       count(*) FILTER (WHERE data_ndeshjes > now() - interval '30 days') AS muajin_e_fundit
FROM historik_trajnimi GROUP BY burimi;


-- ══════════════════════════════════════════════════════════
-- 8. Një rresht `api` i plotë — për ta parë me sy
-- ══════════════════════════════════════════════════════════
-- Tregon çfarë POPULLOHET vërtet (match_id, ekipet, liga...) kundrejt asaj
-- që mbetet bosh. Nga kjo del se ku duhet ndrequr shkrimi.
SELECT * FROM historik_trajnimi
WHERE burimi = 'api' ORDER BY data_ndeshjes DESC LIMIT 1;


-- ══════════════════════════════════════════════════════════
-- 9. Kontroll i shëndetit të importit CSV (duhet të jetë i paprekur)
-- ══════════════════════════════════════════════════════════
-- PRITET: 55835 / 55835 / ~17% / ~15%
SELECT count(*)                                            AS gjithsej,
       count(DISTINCT match_id)                            AS unike,
       round(100.0*count(*) FILTER (WHERE home_avg_sot IS NULL)/count(*), 1)   AS sot_null_pct,
       round(100.0*count(*) FILTER (WHERE h2h_avg_gola IS NULL)/count(*), 1)   AS h2h_null_pct
FROM historik_trajnimi WHERE burimi = 'csv';
