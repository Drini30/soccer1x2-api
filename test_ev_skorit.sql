-- ==================== PYETJA 1 — GODITJE KUNDREJT FITIMI ====================
-- Ndryshimi i objektivit: deri tani kemi zgjedhur argmax(p). Pyetja tani eshte
-- nese argmax(p x kuota) sjell kthim me te mire.
--
-- KTHIMI eshte metrika e vetme qe ka rendesi:
--     kthimi = mesatarja e (kuota nese goditi, 0 nese jo)
--     1.00 = barazim   |   nen 1.00 = humbje   |   mbi 1.00 = fitim
--
-- Krahasohen kater strategji mbi TE NJEJTAT ndeshje:
--   pub     — skori qe publikuam vertet (me shtresat aff/fitues/LEAN)
--   maxP    — skori me probabilitet me te larte nga dist_gola
--   maxEV   — skori me p x kuota me te larte
--   maxEV2  — i njejti, por vetem kur EV > 1.0 (perndryshe s'luhet fare)
--
-- `overround` eshte marzhi i bukmejkerit te tregu CS: shuma e 1/kuota mbi te
-- gjitha skoret e listuara. Nese del 1.25, bukmejkeri mban 25% dhe cdo strategji
-- niset me ate handikap.
WITH b AS (
    SELECT a.match_id, a.rezultati_ft, a.parashikimi,
           a.dist_gola::jsonb            AS dg,
           a.odds_reale::jsonb -> 'CS'   AS cs
    FROM arkiv_rezultatesh a
    WHERE a.dist_gola IS NOT NULL AND a.dist_gola::jsonb <> '{}'::jsonb
      AND a.odds_reale::jsonb ? 'CS'
      AND a.rezultati_ft ~ '\d+\D+\d+'
      AND a.parashikimi  ~ '\d+\D+\d+'
),
r AS (
    SELECT b.*,
           (regexp_match(b.rezultati_ft, '(\d+)\D+(\d+)'))[1] || '-' ||
           (regexp_match(b.rezultati_ft, '(\d+)\D+(\d+)'))[2]  AS skor_real,
           replace(b.parashikimi, ' ', '')                     AS skor_pub
    FROM b
),
x AS (
    SELECT r.match_id, r.skor_real, r.skor_pub,
           e.k                              AS skori,
           e.v::numeric / 50000.0           AS p,
           (r.cs ->> e.k)::numeric          AS koef
    FROM r, LATERAL jsonb_each_text(r.dg) AS e(k, v)
    WHERE (r.cs ->> e.k) ~ '^[0-9.]+$'
      AND (r.cs ->> e.k)::numeric > 1
),
z AS (
    SELECT match_id, skor_real, skor_pub,
           (array_agg(skori ORDER BY p DESC))[1]           AS s_p,
           (array_agg(koef  ORDER BY p DESC))[1]           AS k_p,
           (array_agg(skori ORDER BY p*koef DESC))[1]      AS s_ev,
           (array_agg(koef  ORDER BY p*koef DESC))[1]      AS k_ev,
           (array_agg(p*koef ORDER BY p*koef DESC))[1]     AS ev_max,
           max(koef) FILTER (WHERE skori = skor_pub)       AS k_pub,
           sum(1.0/koef)                                   AS overround,
           count(*)                                        AS skore_me_kuote
    FROM x
    GROUP BY match_id, skor_real, skor_pub
)
SELECT count(*)                                                          AS ndeshje,
       round(avg(overround), 3)                                          AS overround_mes,
       round(avg(skore_me_kuote), 1)                                     AS skore_me_kuote_mes,

       round(100.0*count(*) FILTER (WHERE skor_pub = skor_real)/count(*), 2)  AS pub_goditje_pct,
       round(avg(CASE WHEN skor_pub = skor_real THEN k_pub ELSE 0 END), 4)    AS pub_kthimi,
       round(avg(k_pub), 2)                                              AS pub_koef_mes,

       round(100.0*count(*) FILTER (WHERE s_p = skor_real)/count(*), 2)       AS maxP_goditje_pct,
       round(avg(CASE WHEN s_p = skor_real THEN k_p ELSE 0 END), 4)           AS maxP_kthimi,
       round(avg(k_p), 2)                                                AS maxP_koef_mes,

       round(100.0*count(*) FILTER (WHERE s_ev = skor_real)/count(*), 2)      AS maxEV_goditje_pct,
       round(avg(CASE WHEN s_ev = skor_real THEN k_ev ELSE 0 END), 4)         AS maxEV_kthimi,
       round(avg(k_ev), 2)                                               AS maxEV_koef_mes,
       round(avg(ev_max), 3)                                             AS ev_i_premtuar,

       count(*) FILTER (WHERE ev_max > 1.0)                              AS n_me_ev_mbi_1,
       round(avg(CASE WHEN s_ev = skor_real THEN k_ev ELSE 0 END)
             FILTER (WHERE ev_max > 1.0), 4)                             AS maxEV2_kthimi
FROM z;


-- ==================== PYETJA 2 — A PARASHIKON EV-JA KTHIMIN? ====================
-- Nese EV-ja e llogaritur eshte e vertete, atehere ndeshjet me EV te premtuar me
-- te larte duhet te japin kthim me te larte. Nese kurba eshte e sheshte, EV-ja
-- jone eshte thjesht zhurme e shumezuar me kuota.
--
-- `ev_i_premtuar` kundrejt `kthimi_real` eshte testi i kalibrimit: nese premtojme
-- 1.15 dhe realizojme 0.90, probabilitetet tona jane te fryra ndaj tregut.
WITH b AS (
    SELECT a.match_id, a.rezultati_ft,
           a.dist_gola::jsonb            AS dg,
           a.odds_reale::jsonb -> 'CS'   AS cs
    FROM arkiv_rezultatesh a
    WHERE a.dist_gola IS NOT NULL AND a.dist_gola::jsonb <> '{}'::jsonb
      AND a.odds_reale::jsonb ? 'CS'
      AND a.rezultati_ft ~ '\d+\D+\d+'
),
r AS (
    SELECT b.*,
           (regexp_match(b.rezultati_ft, '(\d+)\D+(\d+)'))[1] || '-' ||
           (regexp_match(b.rezultati_ft, '(\d+)\D+(\d+)'))[2] AS skor_real
    FROM b
),
x AS (
    SELECT r.match_id, r.skor_real, e.k AS skori,
           e.v::numeric / 50000.0  AS p,
           (r.cs ->> e.k)::numeric AS koef
    FROM r, LATERAL jsonb_each_text(r.dg) AS e(k, v)
    WHERE (r.cs ->> e.k) ~ '^[0-9.]+$' AND (r.cs ->> e.k)::numeric > 1
),
z AS (
    SELECT match_id, skor_real,
           (array_agg(skori ORDER BY p*koef DESC))[1]   AS s_ev,
           (array_agg(koef  ORDER BY p*koef DESC))[1]   AS k_ev,
           (array_agg(p*koef ORDER BY p*koef DESC))[1]  AS ev_max
    FROM x GROUP BY match_id, skor_real
)
SELECT CASE WHEN ev_max < 0.90 THEN 'a) EV < 0.90'
            WHEN ev_max < 1.00 THEN 'b) EV 0.90-1.00'
            WHEN ev_max < 1.15 THEN 'c) EV 1.00-1.15'
            ELSE                    'd) EV >= 1.15' END       AS brezi,
       count(*)                                               AS n,
       round(avg(ev_max), 3)                                  AS ev_i_premtuar,
       round(avg(k_ev), 2)                                    AS koef_mes,
       round(100.0*count(*) FILTER (WHERE s_ev = skor_real)/count(*), 2) AS goditje_pct,
       round(avg(CASE WHEN s_ev = skor_real THEN k_ev ELSE 0 END), 4)    AS kthimi_real,
       round((stddev_samp(CASE WHEN s_ev = skor_real THEN k_ev ELSE 0 END)
              / sqrt(count(*)))::numeric, 4)                  AS se
FROM z
GROUP BY 1
ORDER BY 1;
