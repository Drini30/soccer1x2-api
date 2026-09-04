-- ==========================================================
-- ANALIZË: REZULTATET BRENDA RREZES
-- ==========================================================
-- Qëllimi: të matim, VETËM mbi ndeshjet ku totali real ≤ 4 (ato që modeli mund
-- t'i kapte), sa kushton përzgjedhja pas Monte Carlo-s kundrejt marrjes së
-- thjeshtë të skorit më të mundshëm (argmax i `dist_gola`).
--
-- ⚠️ KORRIGJIM I RËNDËSISHËM ndaj analizës që të dhashë më parë:
--    Thashë se tregu ushqen rregullin e fituesit. E VERIFIKOVA te kodi dhe NUK
--    është ashtu. Rregulli te rreshti 5545 përdor `prob_1x2` të llogaritur te
--    rreshti 5499 — pra probabilitetet e PAPËRZIERA të Monte Carlo-s. Përzierja
--    me tregun (`W_MKT_FINAL`) ndodh te rreshti 5961, PAS kthimit të funksionit.
--    Tregu hyn te përzgjedhja e skorit vetëm te dega e fallback-ut (rreshti
--    6045-6050), që ndizet rrallë (total ≤1 dhe xG > 3.20).
--    Pra: pesha e tregut te zgjedhja e skorit është shumë më e vogël nga sa
--    thashë. Konkluzioni për λ mbetet — por arsyeja "tregu po pret rrjetën"
--    ishte e gabuar. Kjo pyetësi e mat gjendjen reale.
--
-- ⚠️ Kolonat `prob_1/prob_x/prob_2` te arkivi janë PAS përzierjes (rreshti 5968).
--    Prandaj probabilitetet e vërteta që panë rregullin i rikthejmë me algjebër:
--        p_mc = (p_arkiv − 0.35 · p_treg) / 0.65
--    ku p_treg = (1/koef) i normalizuar. Pyetja 1 e verifikon këtë kthim.
--
-- ⚠️ Trunkimi: rreshtat e vjetër kanë vetëm 15 skore te `dist_gola` (~88% e
--    masës), të rinjtë 40 (~99.7%). Brenda rrezes (≤4 gola) efekti është i vogël
--    — pikërisht prandaj kjo analizë bëhet BRENDA rrezes. Pyetja 1 tregon sa
--    rreshta i përkasin secilës epokë.
--
-- EKZEKUTOJI ME RADHË. Vetëm PYETJA 0 shkruan diçka (një VIEW), dhe PYETJA 7
-- e fshin atë. Asnjë të dhënë nuk preket.
-- ==========================================================


-- ══════════════════════════════════════════════════════════
-- PYETJA 0 — Krijo VIEW-n (ekzekutoje një herë, para të tjerave)
-- ══════════════════════════════════════════════════════════
CREATE OR REPLACE VIEW v_analiza_rreze AS
WITH b AS (
    SELECT
        a.match_id,
        a.ndeshja,
        a.liga,
        a.data,
        a.besueshmeria,
        a.parashikimi,
        a.rezultati_ft,
        a.prob_1, a.prob_x, a.prob_2,
        a.koef_1, a.koef_x, a.koef_2,
        a.dist_gola::jsonb                                        AS dg,
        NULLIF(a.training_data::jsonb ->> 'xg_1', '')::numeric    AS xg1,
        NULLIF(a.training_data::jsonb ->> 'xg_2', '')::numeric    AS xg2,
        (regexp_match(a.rezultati_ft, '(\d+)\D+(\d+)'))[1]::int   AS r1,
        (regexp_match(a.rezultati_ft, '(\d+)\D+(\d+)'))[2]::int   AS r2,
        (regexp_match(a.parashikimi , '(\d+)\D+(\d+)'))[1]::int   AS p1g,
        (regexp_match(a.parashikimi , '(\d+)\D+(\d+)'))[2]::int   AS p2g
    FROM arkiv_rezultatesh a
    WHERE a.rezultati_ft ~ '\d+\D+\d+'
      AND a.parashikimi  ~ '\d+\D+\d+'
      AND a.dist_gola IS NOT NULL
      AND a.dist_gola::jsonb <> '{}'::jsonb
),
-- Probabilitetet e tregut nga kuotat (të normalizuara, si te rreshti 5784)
m AS (
    SELECT b.*,
           CASE WHEN b.koef_1 > 1 AND b.koef_x > 1 AND b.koef_2 > 1
                THEN (1.0/b.koef_1) / (1.0/b.koef_1 + 1.0/b.koef_x + 1.0/b.koef_2)
           END AS pm_1,
           CASE WHEN b.koef_1 > 1 AND b.koef_x > 1 AND b.koef_2 > 1
                THEN (1.0/b.koef_x) / (1.0/b.koef_1 + 1.0/b.koef_x + 1.0/b.koef_2)
           END AS pm_x,
           CASE WHEN b.koef_1 > 1 AND b.koef_x > 1 AND b.koef_2 > 1
                THEN (1.0/b.koef_2) / (1.0/b.koef_1 + 1.0/b.koef_x + 1.0/b.koef_2)
           END AS pm_2
    FROM b
),
-- Masa e ruajtur te dist_gola + 1X2 i llogaritur DREJTPËRDREJT prej saj
agg AS (
    SELECT m.match_id,
           count(*)                                                     AS n_skore,
           sum(e.v::numeric)                                            AS f_tot,
           sum(e.v::numeric) FILTER (WHERE split_part(e.k,'-',1)::int
                                         > split_part(e.k,'-',2)::int)  AS f_1,
           sum(e.v::numeric) FILTER (WHERE split_part(e.k,'-',1)::int
                                         = split_part(e.k,'-',2)::int)  AS f_x,
           sum(e.v::numeric) FILTER (WHERE split_part(e.k,'-',1)::int
                                         < split_part(e.k,'-',2)::int)  AS f_2
    FROM m, LATERAL jsonb_each_text(m.dg) AS e(k, v)
    GROUP BY m.match_id
),
-- Skori me frekuencën më të lartë = ZGJEDHJA E PAPËRPUNUAR (pa aff, pa filtër, pa lean)
amax AS (
    SELECT m.match_id,
           (SELECT e.k
              FROM jsonb_each_text(m.dg) AS e(k, v)
             ORDER BY e.v::numeric DESC, e.k ASC
             LIMIT 1) AS skor_amax
    FROM m
)
SELECT
    m.match_id, m.ndeshja, m.liga, m.data, m.besueshmeria,
    m.parashikimi, m.rezultati_ft,
    m.r1, m.r2, m.p1g, m.p2g,
    m.r1 + m.r2                                       AS tot_real,
    round((m.xg1 + m.xg2)::numeric, 3)                AS tot_pritur,
    round(m.xg1::numeric, 3)                          AS xg1,
    round(m.xg2::numeric, 3)                          AS xg2,
    (m.r1 + m.r2) <= 4                                AS brenda_rreze,

    -- ZGJEDHJA E PAPËRPUNUAR
    a.skor_amax,
    split_part(a.skor_amax, '-', 1)::int              AS a1,
    split_part(a.skor_amax, '-', 2)::int              AS a2,

    -- GODITJET
    (m.p1g = m.r1 AND m.p2g = m.r2)                   AS goditi_pub,
    (split_part(a.skor_amax,'-',1)::int = m.r1
     AND split_part(a.skor_amax,'-',2)::int = m.r2)   AS goditi_amax,
    (m.p1g || '-' || m.p2g) IS DISTINCT FROM a.skor_amax AS ndryshoi,

    -- MASA E RUAJTUR (epoka e trunkimit). 50000 = MC_ITERACIONE (rreshti 5028);
    -- frekuencat te dist_gola janë numërime nga aq përsëritje.
    g.n_skore,
    round((g.f_tot / 50000.0)::numeric, 4)            AS masa_ruajtur,

    -- 1X2 nga vetë dist_gola (i trunkuar, por i pavarur nga çdo përzierje)
    round((g.f_1 / NULLIF(g.f_tot,0))::numeric, 4)    AS d_p1,
    round((g.f_x / NULLIF(g.f_tot,0))::numeric, 4)    AS d_px,
    round((g.f_2 / NULLIF(g.f_tot,0))::numeric, 4)    AS d_p2,

    -- 1X2 i tregut
    round(m.pm_1::numeric, 4)                         AS pm_1,
    round(m.pm_x::numeric, 4)                         AS pm_x,
    round(m.pm_2::numeric, 4)                         AS pm_2,

    -- 1X2 i MONTE CARLO-s, i rikthyer duke zbritur përzierjen (W_MKT_FINAL = 0.35)
    -- KJO është ajo që pa vërtet rregulli i fituesit.
    round(((m.prob_1 - 0.35*m.pm_1)/0.65)::numeric, 4) AS mc_p1,
    round(((m.prob_x - 0.35*m.pm_x)/0.65)::numeric, 4) AS mc_px,
    round(((m.prob_2 - 0.35*m.pm_2)/0.65)::numeric, 4) AS mc_p2,

    -- A U NDEZ RREGULLI I FITUESIT? (WINNER_PRAG = 0.15, mbi mc_*)
    CASE
        WHEN m.pm_1 IS NULL OR m.prob_1 IS NULL THEN NULL
        WHEN ((m.prob_1 - 0.35*m.pm_1)/0.65) >= ((m.prob_2 - 0.35*m.pm_2)/0.65)
             AND (((m.prob_1 - 0.35*m.pm_1)/0.65) - ((m.prob_x - 0.35*m.pm_x)/0.65)) > 0.15
             THEN 'vendas'
        WHEN ((m.prob_2 - 0.35*m.pm_2)/0.65) >  ((m.prob_1 - 0.35*m.pm_1)/0.65)
             AND (((m.prob_2 - 0.35*m.pm_2)/0.65) - ((m.prob_x - 0.35*m.pm_x)/0.65)) > 0.15
             THEN 'mysafir'
        ELSE 'jo'
    END AS rregulli,

    -- A ISHTE BARAZIM ZGJEDHJA E PAPËRPUNUAR? (kandidati që rregulli fshin)
    (split_part(a.skor_amax,'-',1)::int
     = split_part(a.skor_amax,'-',2)::int)            AS amax_barazim

FROM m
JOIN agg  g ON g.match_id = m.match_id
JOIN amax a ON a.match_id = m.match_id;


-- ══════════════════════════════════════════════════════════
-- PYETJA 1 — SHËNDETI I TË DHËNAVE (ekzekutoje para gjithçkaje)
-- ══════════════════════════════════════════════════════════
-- Pa këtë, çdo numër më poshtë është i pabesueshëm. Kontrollo tri gjëra:
--
--   a) `epoka_15` kundrejt `epoka_40` — sa rreshta i përkasin secilit trunkim.
--   b) `mesat_devijim_1x2` — sa larg bie 1X2 i rikthyer (mc_p1) nga ai i
--      llogaritur drejtpërdrejt prej dist_gola (d_p1). PRITET < 0.05.
--      Nëse del > 0.12, ose W_MKT_FINAL s'ka qenë 0.35 në atë periudhë, ose
--      kuotat e arkivuara s'janë ato që u përdorën — atëherë kolona `rregulli`
--      s'vlen dhe duhet përdorur `d_p1/d_px/d_p2` në vend të saj.
--   c) `mc_jashte_kufijve` — sa rreshta japin probabilitet negativ ose > 1 pas
--      kthimit. Duhet të jetë ~0; çdo numër i madh do të thotë që formula e
--      kthimit s'i përshtatet asaj periudhe.
SELECT
    count(*)                                                        AS ndeshje,
    count(*) FILTER (WHERE n_skore <= 20)                           AS epoka_15,
    count(*) FILTER (WHERE n_skore >  20)                           AS epoka_40,
    round(avg(masa_ruajtur), 4)                                     AS masa_mes,
    count(*) FILTER (WHERE brenda_rreze)                            AS brenda_rreze,
    round(100.0*count(*) FILTER (WHERE brenda_rreze)/count(*), 1)   AS brenda_pct,
    count(*) FILTER (WHERE mc_p1 IS NULL)                           AS pa_kuota,
    round(avg(abs(mc_p1 - d_p1)) FILTER (WHERE mc_p1 IS NOT NULL), 4) AS mesat_devijim_1x2,
    count(*) FILTER (WHERE mc_p1 < -0.02 OR mc_p1 > 1.02
                        OR mc_px < -0.02 OR mc_px > 1.02)           AS mc_jashte_kufijve
FROM v_analiza_rreze;


-- ══════════════════════════════════════════════════════════
-- PYETJA 2 — MATJA KRYESORE: i publikuari kundrejt argmax-it
-- ══════════════════════════════════════════════════════════
-- VETËM ndeshjet brenda rrezes (total real ≤ 4).
-- `gpub` = goditja e skorit të publikuar (me aff + rregull + lean).
-- `gmax` = goditja e skorit thjesht më të mundshëm (pa asnjë shtresë).
--
-- SI TA LEXOSH:
--   • Rreshti 'GJITHSEJ' është përgjigjja. Nëse `gmax_pct` > `gpub_pct`, shtresat
--     po kushtojnë; nëse është anasjelltas, ato po fitojnë diçka.
--   • `ndryshoi` = sa herë shtresat vendosën ndryshe nga argmax. Nëse ky numër
--     është i vogël, atëherë shtresat janë praktikisht inerte dhe s'ka ç'të
--     rregullohet aty — që është pikërisht ajo që parashikova për `aff`.
--   • Ndarja sipas `rregulli` tregon KU ndodh diferenca.
SELECT
    CASE WHEN GROUPING(rregulli) = 1 THEN 'GJITHSEJ'
         ELSE coalesce(rregulli, 'pa kuota') END                         AS grupi,
    count(*)                                                             AS n,
    count(*) FILTER (WHERE ndryshoi)                                     AS ndryshoi,
    round(100.0*count(*) FILTER (WHERE ndryshoi)/count(*), 1)            AS ndryshoi_pct,
    count(*) FILTER (WHERE goditi_pub)                                   AS gpub,
    round(100.0*count(*) FILTER (WHERE goditi_pub)/count(*), 2)          AS gpub_pct,
    count(*) FILTER (WHERE goditi_amax)                                  AS gmax,
    round(100.0*count(*) FILTER (WHERE goditi_amax)/count(*), 2)         AS gmax_pct,
    round(100.0*(count(*) FILTER (WHERE goditi_amax)
               - count(*) FILTER (WHERE goditi_pub))/count(*), 2)        AS fitim_amax_pp
FROM v_analiza_rreze
WHERE brenda_rreze
GROUP BY ROLLUP (rregulli)
ORDER BY GROUPING(rregulli), rregulli;


-- ══════════════════════════════════════════════════════════
-- PYETJA 3 — TESTI I ÇIFTUAR (McNemar) — a është diferenca reale?
-- ══════════════════════════════════════════════════════════
-- Numërohen VETËM ndeshjet ku dy rregullat zgjodhën ndryshe DHE njëri goditi.
-- Kjo e bën testin shumë më të fuqishëm se krahasimi i dy përqindjeve.
--
--   `chi2` > 3.84  → p < 0.05  (diferenca është reale)
--   `chi2` > 2.71  → p < 0.10  (sinjal i dobët)
--   `chi2` < 2.71  → nuk provohet gjë; mos e prek kodin mbi këtë bazë.
--
-- `vetem_pub` = pub goditi, argmax jo.  `vetem_amax` = e kundërta.
WITH d AS (
    SELECT
        count(*) FILTER (WHERE goditi_pub  AND NOT goditi_amax) AS vetem_pub,
        count(*) FILTER (WHERE goditi_amax AND NOT goditi_pub)  AS vetem_amax,
        count(*)                                                AS n_brenda
    FROM v_analiza_rreze
    WHERE brenda_rreze
)
SELECT n_brenda, vetem_pub, vetem_amax,
       (vetem_pub + vetem_amax)                                  AS diskordante,
       round(100.0*(vetem_amax - vetem_pub)/n_brenda, 2)         AS diferenca_pp,
       CASE WHEN (vetem_pub + vetem_amax) > 0
            THEN round((power(abs(vetem_pub - vetem_amax)::numeric - 1, 2)
                        / (vetem_pub + vetem_amax)), 3)
       END                                                       AS chi2
FROM d;


-- ══════════════════════════════════════════════════════════
-- PYETJA 4 — LEVA E VËRTETË: goditja sipas TOTALIT TË PRITUR
-- ══════════════════════════════════════════════════════════
-- Teoria thotë që tavani bie nga ~18% (total 1.8) në ~8% (total 4.0) — një
-- hendek 2.2-fish, shumë më i madh se çdo gjë që fiton rregullimi i shtresave.
-- Kjo pyetësi e mat atë mbi të dhënat e tua reale.
--
-- Nëse `gpub_pct` bie monotonisht me totalin, filtri i publikimit duhet të jetë
-- mbi `tot_pritur` — jo mbi besueshmërinë, jo mbi P(mode), të cilat dështuan.
-- `brenda_pct` tregon edhe sa shpesh ndeshja bie fare brenda rrezes.
SELECT
    CASE WHEN tot_pritur <  2.2 THEN 'a) < 2.2'
         WHEN tot_pritur <  2.6 THEN 'b) 2.2-2.6'
         WHEN tot_pritur <  3.0 THEN 'c) 2.6-3.0'
         WHEN tot_pritur <  3.4 THEN 'd) 3.0-3.4'
         ELSE                        'e) >= 3.4' END              AS brez_totali,
    count(*)                                                      AS n,
    round(avg(tot_pritur), 2)                                     AS tot_pritur_mes,
    round(avg(tot_real), 2)                                       AS tot_real_mes,
    round(100.0*count(*) FILTER (WHERE brenda_rreze)/count(*), 1) AS brenda_pct,
    count(*) FILTER (WHERE goditi_pub)                            AS gpub,
    round(100.0*count(*) FILTER (WHERE goditi_pub)/count(*), 2)   AS gpub_pct,
    round(100.0*count(*) FILTER (WHERE goditi_amax)/count(*), 2)  AS gmax_pct
FROM v_analiza_rreze
WHERE tot_pritur IS NOT NULL
GROUP BY 1
ORDER BY 1;


-- ══════════════════════════════════════════════════════════
-- PYETJA 5 — KU E ÇON SHTRESA ZGJEDHJEN? (zëvendësimet konkrete)
-- ══════════════════════════════════════════════════════════
-- Vetëm ndeshjet ku shtresat vendosën NDRYSHE nga argmax.
-- Kjo tregon nëse zëvendësimi është sistematik (p.sh. gjithnjë 1-1 → 2-1, që do
-- ishte rregulli i fituesit duke fshirë barazimin) apo i rastësishëm.
--
-- `neto` = sa herë fitoi publikimi minus sa herë fitoi argmax për atë çift.
-- Negative = ai zëvendësim po humb.
SELECT
    skor_amax                                                     AS nga_argmax,
    (p1g || '-' || p2g)                                           AS te_publikuari,
    count(*)                                                      AS here,
    count(*) FILTER (WHERE goditi_pub)                            AS gpub,
    count(*) FILTER (WHERE goditi_amax)                           AS gmax,
    count(*) FILTER (WHERE goditi_pub) - count(*) FILTER (WHERE goditi_amax) AS neto
FROM v_analiza_rreze
WHERE brenda_rreze AND ndryshoi
GROUP BY 1, 2
HAVING count(*) >= 3
ORDER BY here DESC
LIMIT 25;


-- ══════════════════════════════════════════════════════════
-- PYETJA 6 — DIAPAZONI: çfarë publikon modeli kundrejt asaj që ndodh
-- ══════════════════════════════════════════════════════════
-- Kjo i përgjigjet drejtpërdrejt kërkesës për 3-0 dhe 3-1.
-- `pub_pct` = sa shpesh e publikojmë atë skor. `real_pct` = sa shpesh ndodh.
-- `amax_pct` = sa shpesh do ta zgjidhte argmax-i i papërpunuar.
--
-- PRITET (nga teoria): 3-0 dhe 3-1 pothuajse s'shfaqen fare te `pub_pct` dhe
-- `amax_pct`, ndërsa te `real_pct` janë ~4-5% secili. Nëse del ashtu, kjo është
-- prova që diapazoni s'zgjerohet dot me pragje — vetëm me λ.
WITH x AS (
    SELECT (p1g || '-' || p2g) AS s_pub,
           (r1  || '-' || r2 ) AS s_real,
           skor_amax           AS s_amax
    FROM v_analiza_rreze
    WHERE brenda_rreze
),
t AS (SELECT count(*)::numeric AS n FROM x),
k AS (
    SELECT s_real AS skor FROM x
    UNION SELECT s_pub  FROM x
    UNION SELECT s_amax FROM x
)
SELECT k.skor,
       round(100.0 * (SELECT count(*) FROM x WHERE x.s_pub  = k.skor) / t.n, 2) AS pub_pct,
       round(100.0 * (SELECT count(*) FROM x WHERE x.s_amax = k.skor) / t.n, 2) AS amax_pct,
       round(100.0 * (SELECT count(*) FROM x WHERE x.s_real = k.skor) / t.n, 2) AS real_pct,
       round(100.0 * ((SELECT count(*) FROM x WHERE x.s_pub  = k.skor)
                    - (SELECT count(*) FROM x WHERE x.s_real = k.skor)) / t.n, 2) AS diferenca_pp
FROM k CROSS JOIN t
ORDER BY real_pct DESC NULLS LAST
LIMIT 20;


-- ══════════════════════════════════════════════════════════
-- PYETJA 7 — PASTRIM (ekzekutoje kur të mbarosh)
-- ══════════════════════════════════════════════════════════
-- DROP VIEW IF EXISTS v_analiza_rreze;
