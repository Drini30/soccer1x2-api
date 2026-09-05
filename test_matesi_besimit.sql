-- ############################################################################
-- CILI MATES BESIMI PUNON VERTET?
-- ############################################################################
--
-- GJETJA QE TESTOHET (nga 104 ndeshjet e 4-5 shtatorit):
--   besueshmeria      -> 30 me te lartat goditen  0.0%, 30 me te ulatat 13.3%
--   p_pub (p jone)    -> 30 me te lartat goditen 13.3%, 30 me te ulatat  3.3%
-- Pra besueshmeria duket se punon MBRAPSHT si mates per skorin.
--
-- MEKANIZMI qe e parashikon kete:
--   besueshmeria v3 = 0.75*sinjal + 0.25*forma, ku sinjali eshte hendeku i
--   favoritit. Nje favorit i qarte nenkupton total me te larte (korr +0.38 me
--   total_pritur), dhe nje total me i larte prodhon shperndarje me te gjere
--   (korr -0.79 me p_argmax). Pra besueshmeria mat sigurine te DREJTIMI, ndersa
--   ne e perdorim per te zgjedhur SKORIN. Dy gjera qe levizin ne drejtim te
--   kundert.
--
-- Nese kjo qendron mbi 1,000+ ndeshje, atehere:
--   - PPM/VIP duhet te zgjedhin sipas p_pub, jo sipas besueshmerise
--   - besueshmeria e publikuar te faqja mashtron perdoruesin
-- Nese NUK qendron, ishte artefakt i dy diteve dhe s'preket asgje.
--
-- ⚠️ n ~ 1,000 -> gabimi standard i nje norme rreth 11% eshte ~1.0pp per grup
--    te plote, ~3pp per decil. Nje hendek nen 3pp mes decilit te pare dhe te
--    fundit eshte zhurme.
-- ############################################################################


-- ==================== PYETJA 1 — DECILET E TRE MATESVE ====================
-- I njejti grup ndeshjesh, tre renditje te ndryshme. Kolona `goditje_pct` duhet
-- te rritet monotonikisht nga decili 1 te 10 nese matesi punon.
WITH b AS (
    SELECT a.match_id, a.besueshmeria,
           regexp_replace(a.rezultati_ft, '\s','','g') AS skor_real,
           regexp_replace(a.parashikimi,  '\s','','g') AS skor_pub,
           a.dist_gola::jsonb AS dg
    FROM arkiv_rezultatesh a
    WHERE a.rezultati_ft ~ '\d+\D+\d+' AND a.parashikimi ~ '\d+\D+\d+'
      AND a.dist_gola IS NOT NULL AND a.dist_gola::jsonb <> '{}'::jsonb
      AND a.besueshmeria IS NOT NULL
),
x AS (
    SELECT b.*, e.k AS skori, e.v::numeric AS cnt,
           row_number() OVER (PARTITION BY b.match_id ORDER BY e.v::numeric DESC) AS rendi
    FROM b, LATERAL jsonb_each_text(b.dg) AS e(k, v)
),
m AS (
    SELECT match_id, besueshmeria,
           bool_or(skori = skor_real AND skori = skor_pub)     AS goditi,
           COALESCE(max(cnt) FILTER (WHERE skori = skor_pub), 0)/50000.0 AS p_pub,
           COALESCE(max(cnt) FILTER (WHERE rendi = 1), 0)/50000.0        AS p_argmax,
           COALESCE(sum(cnt) FILTER (WHERE rendi <= 5), 0)/50000.0       AS mbulimi5
    FROM x GROUP BY match_id, besueshmeria
),
q AS (
    SELECT m.*,
           ntile(10) OVER (ORDER BY besueshmeria) AS d_besu,
           ntile(10) OVER (ORDER BY p_pub)        AS d_ppub,
           ntile(10) OVER (ORDER BY p_argmax)     AS d_pmax,
           ntile(10) OVER (ORDER BY mbulimi5)     AS d_mb5
    FROM m
),
u AS (
    SELECT 'a) besueshmeria' AS matesi, d_besu AS decili, goditi FROM q
    UNION ALL SELECT 'b) p_pub',        d_ppub, goditi FROM q
    UNION ALL SELECT 'c) p_argmax',     d_pmax, goditi FROM q
    UNION ALL SELECT 'd) mbulimi_top5', d_mb5,  goditi FROM q
)
SELECT matesi, decili,
       count(*)                                                  AS n,
       count(*) FILTER (WHERE goditi)                            AS goditje,
       round(100.0*count(*) FILTER (WHERE goditi)/count(*), 2)   AS goditje_pct,
       round((100.0*sqrt((avg(goditi::int::float8)*(1-avg(goditi::int::float8)))
                         / count(*)))::numeric, 2)               AS se
FROM u
GROUP BY matesi, decili
ORDER BY matesi, decili;


-- ==================== PYETJA 2 — PERMBLEDHJA: KORRELACIONI DHE HENDEKU ====================
-- Nje rresht per mates. `korr` eshte lidhja me goditjen; `hendeku` eshte
-- diferenca mes 20% me te larteve dhe 20% me te uleteve.
--
-- Nese `korr_besueshmeria` del NEGATIV mbi 1,000 ndeshje, gjetja eshte e verifikuar
-- dhe besueshmeria duhet hequr nga cdo perzgjedhje skori.
WITH b AS (
    SELECT a.match_id, a.besueshmeria,
           regexp_replace(a.rezultati_ft, '\s','','g') AS skor_real,
           regexp_replace(a.parashikimi,  '\s','','g') AS skor_pub,
           a.dist_gola::jsonb AS dg,
           (a.training_data::jsonb ->> 'xg_1')::numeric
         + (a.training_data::jsonb ->> 'xg_2')::numeric AS total_xg
    FROM arkiv_rezultatesh a
    WHERE a.rezultati_ft ~ '\d+\D+\d+' AND a.parashikimi ~ '\d+\D+\d+'
      AND a.dist_gola IS NOT NULL AND a.dist_gola::jsonb <> '{}'::jsonb
      AND a.besueshmeria IS NOT NULL
),
x AS (
    SELECT b.*, e.k AS skori, e.v::numeric AS cnt,
           row_number() OVER (PARTITION BY b.match_id ORDER BY e.v::numeric DESC) AS rendi
    FROM b, LATERAL jsonb_each_text(b.dg) AS e(k, v)
),
m AS (
    SELECT match_id, besueshmeria, total_xg,
           (bool_or(skori = skor_real AND skori = skor_pub))::int::float8 AS goditi,
           COALESCE(max(cnt) FILTER (WHERE skori = skor_pub), 0)/50000.0 AS p_pub,
           COALESCE(max(cnt) FILTER (WHERE rendi = 1), 0)/50000.0        AS p_argmax,
           COALESCE(sum(cnt) FILTER (WHERE rendi <= 5), 0)/50000.0       AS mbulimi5
    FROM x GROUP BY match_id, besueshmeria, total_xg
)
SELECT count(*)                                              AS n,
       round(100.0*avg(goditi)::numeric, 2)                  AS goditje_pct,
       round(corr(goditi, besueshmeria)::numeric, 4)         AS korr_besueshmeria,
       round(corr(goditi, p_pub)::numeric, 4)                AS korr_p_pub,
       round(corr(goditi, p_argmax)::numeric, 4)             AS korr_p_argmax,
       round(corr(goditi, mbulimi5)::numeric, 4)             AS korr_mbulimi5,
       round((1.0/sqrt(count(*)))::numeric, 4)               AS se_korr,
       -- kontrolli i mekanizmit: a eshte besueshmeria vertet e lidhur me totalin?
       round(corr(besueshmeria, total_xg)::numeric, 4)       AS korr_besu_total,
       round(corr(p_argmax, total_xg)::numeric, 4)           AS korr_pmax_total,
       round(corr(besueshmeria, p_argmax)::numeric, 4)       AS korr_besu_pmax
FROM m
WHERE total_xg IS NOT NULL;


-- ==================== PYETJA 3 — KALIBRIMI: A E MBAN PREMTIMIN p_pub? ====================
-- Nese p_pub eshte probabilitet i vertete, atehere ndeshjet ku premtuam 15%
-- duhet te godasin ~15%. Kjo e mat drejtperdrejt mbivleresimin e modelit.
--
-- `raporti` nen 1.00 do te thote qe shperndarja jone eshte e fryre; sa me poshte,
-- aq me shume. Ky numer eshte gjithashtu tavani i cdo produkti me kuota.
WITH b AS (
    SELECT a.match_id,
           regexp_replace(a.rezultati_ft, '\s','','g') AS skor_real,
           regexp_replace(a.parashikimi,  '\s','','g') AS skor_pub,
           a.dist_gola::jsonb AS dg
    FROM arkiv_rezultatesh a
    WHERE a.rezultati_ft ~ '\d+\D+\d+' AND a.parashikimi ~ '\d+\D+\d+'
      AND a.dist_gola IS NOT NULL AND a.dist_gola::jsonb <> '{}'::jsonb
),
x AS (
    SELECT b.*, e.k AS skori, e.v::numeric AS cnt,
           row_number() OVER (PARTITION BY b.match_id ORDER BY e.v::numeric DESC) AS rendi
    FROM b, LATERAL jsonb_each_text(b.dg) AS e(k, v)
),
m AS (
    SELECT match_id,
           (bool_or(skori = skor_real AND skori = skor_pub))::int::float8 AS goditi,
           COALESCE(max(cnt) FILTER (WHERE skori = skor_pub), 0)/50000.0  AS p_pub
    FROM x GROUP BY match_id
),
q AS (SELECT m.*, ntile(5) OVER (ORDER BY p_pub) AS brezi FROM m)
SELECT brezi,
       count(*)                                          AS n,
       round(100.0*avg(p_pub)::numeric, 2)               AS premtuam_pct,
       round(100.0*avg(goditi)::numeric, 2)              AS goditem_pct,
       round((avg(goditi)/NULLIF(avg(p_pub),0))::numeric, 3) AS raporti,
       round((100.0*sqrt((avg(goditi)*(1-avg(goditi)))/count(*)))::numeric, 2) AS se
FROM q
GROUP BY brezi
ORDER BY brezi;


-- ==================== PYETJA 4 — A KUSHTOJNE SHTRESAT? ====================
-- Te 4-5 shtatorin: argmax goditi 9.1% (n=33), jo-argmax 2.8% (n=71), ndersa
-- premtimet ishin 12.99% dhe 9.45%. Pra jo-argmax ra shume me poshte premtimit.
-- Mostra ishte tepr e vogel; ky e mat mbi gjithe arkivin.
--
-- Nese `raporti` te jo-argmax eshte dukshem nen ate te argmax-it, shtresat
-- (aff/fitues/LEAN) po na largojne nga skore me te mira se sa mendojne.
WITH b AS (
    SELECT a.match_id,
           regexp_replace(a.rezultati_ft, '\s','','g') AS skor_real,
           regexp_replace(a.parashikimi,  '\s','','g') AS skor_pub,
           a.dist_gola::jsonb AS dg
    FROM arkiv_rezultatesh a
    WHERE a.rezultati_ft ~ '\d+\D+\d+' AND a.parashikimi ~ '\d+\D+\d+'
      AND a.dist_gola IS NOT NULL AND a.dist_gola::jsonb <> '{}'::jsonb
),
x AS (
    SELECT b.*, e.k AS skori, e.v::numeric AS cnt,
           row_number() OVER (PARTITION BY b.match_id ORDER BY e.v::numeric DESC) AS rendi
    FROM b, LATERAL jsonb_each_text(b.dg) AS e(k, v)
),
m AS (
    SELECT match_id,
           (bool_or(skori = skor_real AND skori = skor_pub))::int::float8 AS goditi,
           COALESCE(min(rendi) FILTER (WHERE skori = skor_pub), 99)       AS rendi_pub,
           COALESCE(max(cnt) FILTER (WHERE skori = skor_pub), 0)/50000.0  AS p_pub,
           COALESCE(max(cnt) FILTER (WHERE rendi = 1), 0)/50000.0         AS p_argmax,
           (bool_or(skori = skor_real AND rendi = 1))::int::float8        AS argmax_do_kishte_goditur
    FROM x GROUP BY match_id
)
SELECT CASE WHEN rendi_pub = 1 THEN 'a) publikuam argmax'
            WHEN rendi_pub <= 3 THEN 'b) publikuam rendin 2-3'
            ELSE                     'c) publikuam rendin 4+' END AS grupi,
       count(*)                                            AS n,
       round(100.0*avg(p_pub)::numeric, 2)                 AS premtuam_pct,
       round(100.0*avg(goditi)::numeric, 2)                AS goditem_pct,
       round((avg(goditi)/NULLIF(avg(p_pub),0))::numeric, 3) AS raporti,
       round(100.0*avg(argmax_do_kishte_goditur)::numeric, 2) AS argmax_do_goditte_pct,
       round(100.0*avg(p_argmax)::numeric, 2)              AS p_argmax_pct,
       round((100.0*sqrt((avg(goditi)*(1-avg(goditi)))/count(*)))::numeric, 2) AS se
FROM m
GROUP BY 1
ORDER BY 1;
