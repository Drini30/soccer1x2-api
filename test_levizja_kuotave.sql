-- ############################################################################
-- LEVIZJA E KUOTAVE — burimi i fundit i patestuar
-- ############################################################################
--
-- PSE KY TEST ESHTE I NDRYSHEM NGA TE GJITHE TE TJERET:
-- Cdo gje qe kemi provuar deri tani (forma, ELO, volatiliteti, pushimi, gjurma e
-- skuadres, tipi i ndeshjes) ishte informacion QE TREGU E KA TASHME kur cakton
-- kuoten. Prandaj s'gjeti gje: nuk mund t'ia kalosh tregut me te dhenat e tregut.
--
-- Levizja e kuotave eshte e vetmja gje qe prodhohet PASI linja hapet — pra mbart
-- informacionin qe hyri ne treg pas hapjes (formacionet, demtimet, paret e medha).
-- Nese ka ndonje gje qe s'e kemi, eshte ketu.
--
-- ⚠️⚠️ KUJDES ME MADHESINE E MOSTRES — KJO NDRYSHON RREGULLAT E LEXIMIT ⚠️⚠️
-- historik_trajnimi kishte 40,000-55,000 rreshta. Atje |r| = 0.03 ishte e matshme
-- dhe prapeseprape e padobishme.
-- Ketu kemi 702 ndeshje, dhe vetem nje pjese e tyre kane mbaruar e jane arkivuar.
-- Me n = 500:  gabimi standard i nje korrelacioni eshte 1/sqrt(500) = 0.045.
--     |r| < 0.09  -> BRENDA 2 SIGMA NGA ZEROJA. Nuk eshte gjetje. Nuk eshte asgje.
--     |r| 0.09-0.13 -> e dyshimte; do te duhej dyfishi i te dhenave per ta besuar
--     |r| > 0.13  -> gjetje reale me kete mostre
-- Pra ketu NUK mund te zbulojme sinjale te dobet. Mund te zbulojme vetem te forte.
-- Nese nuk del asgje, perfundimi i sakte s'eshte "s'ka sinjal" por "nese ka, eshte
-- me i vogel se 0.13 dhe na duhen 3-4 muaj te tjere te dhena per ta pare".
-- ############################################################################


-- ==================== PYETJA 1 — SA TE DHENA KEMI VERTET? ====================
-- Perpara cdo testi: sa ndeshje kane fotografi TE PERDORSHME dhe kane mbaruar?
--
-- Nje "levizje" ka kuptim vetem nese dritarja midis fotografise se pare dhe te
-- fundit eshte e gjere. Nese te 38 fotografite jane brenda 40 minutash, s'ka
-- levizje per te matur — ka thjesht zhurme te te njejtes linje.
--
-- Kolonat kyce:
--   `ne_arkiv`      — vetem keto mund te notohen. Nese eshte nen 300, cdo test me
--                     poshte eshte tregues, jo prove.
--   `dritare_mes`   — minutat mes fotografise se pare dhe te fundit
--   `mbyllja_mes`   — sa minuta para ndeshjes eshte fotografia e fundit
SELECT count(*)                                                        AS ndeshje_me_kuota,
       count(*) FILTER (WHERE ne_arkiv)                                AS ne_arkiv,
       count(*) FILTER (WHERE ne_arkiv AND dritarja >= 180)            AS te_perdorshme,
       round(avg(n_foto), 1)                                           AS fotografi_mes,
       round(avg(dritarja), 0)                                         AS dritare_mes,
       round(avg(hapja), 0)                                            AS hapja_min_para,
       round(avg(mbyllja), 0)                                          AS mbyllja_min_para,
       count(*) FILTER (WHERE mbyllja <= 60)                           AS mbyllen_nen_60min,
       count(*) FILTER (WHERE dritarja < 180)                          AS dritare_e_ngushte
FROM (
    SELECT h.fixture_id,
           count(*)                                   AS n_foto,
           max(h.minuta_para)                         AS hapja,
           min(h.minuta_para)                         AS mbyllja,
           max(h.minuta_para) - min(h.minuta_para)    AS dritarja,
           bool_or(a.match_id IS NOT NULL)            AS ne_arkiv
    FROM kuota_historik h
    LEFT JOIN arkiv_rezultatesh a ON a.match_id = h.fixture_id::text
    WHERE h.k1 > 1 AND h.kx > 1 AND h.k2 > 1
    GROUP BY h.fixture_id
) t;


-- ==================== PYETJA 2 — A KEMBENGUL LEVIZJA? ====================
-- Testi me i lire dhe me i rendesishem, sepse NUK kerkon rezultate — pra e ka
-- gjithe mostren prej 702 ndeshjesh, jo vetem te arkivuarat.
--
-- Pyetja: nese linja levizi nga X ne Y ne gjysmen e pare te dritares, a vazhdon
-- ne te njejtin drejtim ne gjysmen e dyte?
--
--   korr > +0.10  -> MOMENTUM: paraja vazhdon te vije nga e njejta ane. Do te
--                    thote se cmimi qe ne perdorim ne gjenerim eshte SISTEMATIKISHT
--                    prapa cmimit te mbylljes, dhe mund ta ekstrapolojme.
--   korr ~ 0      -> ecuri e rastesishme. Cmimi aktual eshte parashikimi me i mire
--                    i cmimit te mbylljes. S'ka cfare te nxjerrim nga levizja.
--   korr < -0.10  -> mbikundervepr im: linja kercen dhe kthehet. Levizja eshte
--                    zhurme e librarit, jo informacion.
--
-- `pjerresia` te thote sa: nese eshte 0.30, atehere pas nje levizjeje prej 0.02
-- ne p1, prit edhe 0.006 te tjera perpara ndeshjes.
WITH s AS (
    SELECT fixture_id, minuta_para,
           (1.0/k1) / ((1.0/k1)+(1.0/kx)+(1.0/k2)) AS p1,
           (1.0/k2) / ((1.0/k1)+(1.0/kx)+(1.0/k2)) AS p2
    FROM kuota_historik
    WHERE k1 > 1 AND kx > 1 AND k2 > 1
),
g AS (
    SELECT fixture_id,
           count(*)::int                                     AS n,
           array_agg(p1 ORDER BY minuta_para DESC)            AS ap1,
           array_agg(p2 ORDER BY minuta_para DESC)            AS ap2,
           max(minuta_para) - min(minuta_para)                AS dritarja
    FROM s GROUP BY fixture_id
),
t AS (
    SELECT fixture_id, n, dritarja,
           ap1[(n+1)/2] - ap1[1]  AS lev1_a,   -- gjysma e pare  (hapje -> mes)
           ap1[n] - ap1[(n+1)/2]  AS lev1_b,   -- gjysma e dyte  (mes  -> mbyllje)
           ap2[(n+1)/2] - ap2[1]  AS lev2_a,
           ap2[n] - ap2[(n+1)/2]  AS lev2_b,
           ap1[n] - ap1[1]        AS lev1_plot
    FROM g
    WHERE n >= 6 AND dritarja >= 180
)
SELECT count(*)                                                   AS ndeshje,
       round(avg(n), 1)                                           AS fotografi_mes,
       round((avg(abs(lev1_plot)) * 100)::numeric, 2)             AS levizja_mes_pikperqindje,
       round((stddev_samp(lev1_plot) * 100)::numeric, 2)          AS sd_levizja,
       round(corr(lev1_b, lev1_a)::numeric, 4)                    AS korr_kembengulja_1,
       round(regr_slope(lev1_b, lev1_a)::numeric, 4)              AS pjerresia_1,
       round(corr(lev2_b, lev2_a)::numeric, 4)                    AS korr_kembengulja_2,
       round((1.0/sqrt(count(*)))::numeric, 4)                    AS se_afersisht
FROM t;


-- ==================== PYETJA 3 — A PARASHIKON LEVIZJA REZULTATIN 1X2? ====================
-- Testi klasik i efiçiences. Marrim CMIMIN E MBYLLJES si baze — pra gjithcka qe
-- tregu di ne fund — dhe pyesim nese levizja qe e solli aty shton dicka.
--
--   mbetja = (ndodhi vertet?) - (probabiliteti i mbylljes)
--
-- Nese tregu eshte i kalibruar, mbetja ka mesatare zero dhe s'ka lidhje me asgje.
--   korr(mbetja, levizja) > +0.10 -> tregu KA NENKUNDERVEPRUAR: duhej te kishte
--        levizur me shume. Ne mund t'i shtojme levizjes nje shumefishues.
--   korr ~ 0 -> cmimi i mbylljes e ka thithur gjithe informacionin. Kjo eshte
--        pergjigjja e pritur nga literatura, dhe do te thote se levizja s'na jep
--        gje PERTEJ mbylljes — por prapeseprape na jep dicka perballe cmimit qe
--        PERDORIM ne gjenerim (shih pyetjen 2).
--
-- Bonus: `korr_mbetja_hapja` — e njejta perballe cmimit te HAPJES. Nese kjo del
-- shume me e larte se e mbylljes, ajo vertetohet se mbyllja eshte me e mire se
-- hapja, dhe se duhet te gjenerojme sa me vone.
WITH s AS (
    SELECT fixture_id, minuta_para,
           (1.0/k1) / ((1.0/k1)+(1.0/kx)+(1.0/k2)) AS p1,
           (1.0/k2) / ((1.0/k1)+(1.0/kx)+(1.0/k2)) AS p2
    FROM kuota_historik
    WHERE k1 > 1 AND kx > 1 AND k2 > 1
),
g AS (
    SELECT fixture_id, count(*)::int AS n,
           array_agg(p1 ORDER BY minuta_para DESC) AS ap1,
           array_agg(p2 ORDER BY minuta_para DESC) AS ap2,
           max(minuta_para) - min(minuta_para)     AS dritarja
    FROM s GROUP BY fixture_id
),
m AS (
    SELECT fixture_id,
           ap1[1] AS p1_hap, ap1[n] AS p1_mby,
           ap2[1] AS p2_hap, ap2[n] AS p2_mby
    FROM g WHERE n >= 4 AND dritarja >= 180
),
r AS (
    SELECT m.*,
           (regexp_match(a.rezultati_ft, '(\d+)\D+(\d+)'))[1]::int AS gh,
           (regexp_match(a.rezultati_ft, '(\d+)\D+(\d+)'))[2]::int AS ga
    FROM m JOIN arkiv_rezultatesh a ON a.match_id = m.fixture_id::text
    WHERE a.rezultati_ft ~ '\d+\D+\d+'
),
z AS (
    SELECT (gh > ga)::int::float8 - p1_mby AS mbetja_1,
           (ga > gh)::int::float8 - p2_mby AS mbetja_2,
           (gh > ga)::int::float8 - p1_hap AS mbetja_1_hap,
           p1_mby - p1_hap                 AS lev_1,
           p2_mby - p2_hap                 AS lev_2
    FROM r
)
SELECT count(*)                                              AS ndeshje,
       round(avg(mbetja_1)::numeric, 4)                      AS anshmeria_1,
       round(avg(mbetja_2)::numeric, 4)                      AS anshmeria_2,
       round(corr(mbetja_1, lev_1)::numeric, 4)              AS korr_1,
       round(corr(mbetja_2, lev_2)::numeric, 4)              AS korr_2,
       round(regr_slope(mbetja_1, lev_1)::numeric, 3)        AS pjerresia_1,
       round(corr(mbetja_1_hap, lev_1)::numeric, 4)          AS korr_mbetja_hapja,
       round((1.0/sqrt(count(*)))::numeric, 4)               AS se_afersisht
FROM z;


-- ==================== PYETJA 4 — LEVIZJA E TOTALIT (O/U 2.5) ====================
-- Ketu qendron interesi yne me i madh: totali eshte aty ku modeli yne eshte me i
-- ngushte (MAE 1.317 kundrejt dyshemese 1.232), dhe skori i sakte varet nga ai.
--
-- Tri pyetje njeheresh:
--   `korr_mbetja_tregu`  — a parashikon levizja e O/U totalin PERTEJ cmimit te
--                          mbylljes? (efiçienca e tregut)
--   `korr_mbetja_modeli` — a parashikon levizja e O/U gabimin E MODELIT TONE?
--                          Kjo eshte pyetja praktike: nese po, kemi cfare shtojme.
--   `korr_modeli_tregu`  — sa larg jemi ne nga tregu ne total, si kontroll.
--
-- Nese `korr_mbetja_modeli` > 0.13, atehere levizja e O/U duhet te hyje si
-- modifikues i lambda-s totale. Nese eshte nen 0.09, s'ka gje.
WITH s AS (
    SELECT fixture_id, minuta_para,
           (1.0/ou25_over) / ((1.0/ou25_over)+(1.0/ou25_under)) AS p_over
    FROM kuota_historik
    WHERE ou25_over > 1 AND ou25_under > 1
),
g AS (
    SELECT fixture_id, count(*)::int AS n,
           array_agg(p_over ORDER BY minuta_para DESC) AS ao,
           max(minuta_para) - min(minuta_para)         AS dritarja
    FROM s GROUP BY fixture_id
),
m AS (
    SELECT fixture_id, ao[1] AS po_hap, ao[n] AS po_mby
    FROM g WHERE n >= 4 AND dritarja >= 180
),
r AS (
    SELECT m.*,
           ((regexp_match(a.rezultati_ft, '(\d+)\D+(\d+)'))[1]::int
          + (regexp_match(a.rezultati_ft, '(\d+)\D+(\d+)'))[2]::int)::float8 AS tot_real,
           ((a.training_data::jsonb ->> 'xg_1')::float8
          + (a.training_data::jsonb ->> 'xg_2')::float8)                     AS tot_modeli
    FROM m JOIN arkiv_rezultatesh a ON a.match_id = m.fixture_id::text
    WHERE a.rezultati_ft ~ '\d+\D+\d+'
      AND a.training_data IS NOT NULL
      AND (a.training_data::jsonb ->> 'xg_1') IS NOT NULL
      AND (a.training_data::jsonb ->> 'xg_2') IS NOT NULL
),
koef AS (SELECT regr_slope(tot_real, po_mby) AS bb, regr_intercept(tot_real, po_mby) AS aa FROM r),
z AS (
    SELECT r.*,
           r.tot_real - (k.aa + k.bb * r.po_mby) AS mbetja_tregu,
           r.tot_real - r.tot_modeli             AS mbetja_modeli,
           r.po_mby - r.po_hap                   AS lev_o
    FROM r CROSS JOIN koef k
)
SELECT count(*)                                            AS ndeshje,
       round(avg(tot_real)::numeric, 3)                    AS totali_real,
       round(avg(tot_modeli)::numeric, 3)                  AS totali_modeli,
       round(avg(mbetja_modeli)::numeric, 3)               AS anshmeria_e_modelit,
       round((avg(abs(lev_o)) * 100)::numeric, 2)          AS levizja_over_pikperqindje,
       round(corr(mbetja_tregu, lev_o)::numeric, 4)        AS korr_mbetja_tregu,
       round(corr(mbetja_modeli, lev_o)::numeric, 4)       AS korr_mbetja_modeli,
       round(regr_slope(mbetja_modeli, lev_o)::numeric, 2) AS pjerresia_modeli,
       round(corr(tot_modeli, po_mby)::numeric, 4)         AS korr_modeli_tregu,
       round((1.0/sqrt(count(*)))::numeric, 4)             AS se_afersisht
FROM z;


-- ==================== PYETJA 5 — TESTI PRAKTIK: FILTER, JO MODEL ====================
-- Kjo eshte pyetja qe mund te japi dicka te perdorshme NESER, pa prekur asnje
-- formule: a i godasim me keq ndeshjet ku PARAJA LEVIZI KUNDER drejtimit qe
-- publikuam ne?
--
-- `drejtimi_yne` merret nga skori i publikuar (2-0 -> vendasi, 1-2 -> mysafiri).
-- `pro_nesh` eshte levizja e probabilitetit te ANES SONE: pozitive do te thote se
-- tregu levizi drejt nesh, negative se levizi kunder nesh.
--
-- LEXIMI: nese brezi 'a) kunder fort' ka goditje 1X2 dukshem me te ulet se
-- 'd) pro nesh fort', atehere kemi nje filter: mos e publiko ate ndeshje, ose
-- rishikoje drejtimin. Shiko `se` — me ~120 ndeshje per brez, nje ndryshim nen
-- 8 pikperqindje eshte zhurme.
WITH s AS (
    SELECT fixture_id, minuta_para,
           (1.0/k1) / ((1.0/k1)+(1.0/kx)+(1.0/k2)) AS p1,
           (1.0/k2) / ((1.0/k1)+(1.0/kx)+(1.0/k2)) AS p2
    FROM kuota_historik
    WHERE k1 > 1 AND kx > 1 AND k2 > 1
),
g AS (
    SELECT fixture_id, count(*)::int AS n,
           array_agg(p1 ORDER BY minuta_para DESC) AS ap1,
           array_agg(p2 ORDER BY minuta_para DESC) AS ap2,
           max(minuta_para) - min(minuta_para)     AS dritarja
    FROM s GROUP BY fixture_id
),
m AS (
    SELECT fixture_id, ap1[n] - ap1[1] AS lev_1, ap2[n] - ap2[1] AS lev_2
    FROM g WHERE n >= 4 AND dritarja >= 180
),
r AS (
    SELECT m.lev_1, m.lev_2, a.goditi_1x2, a.goditi_skor, a.besueshmeria,
           (regexp_match(a.parashikimi, '(\d+)\D+(\d+)'))[1]::int AS ph,
           (regexp_match(a.parashikimi, '(\d+)\D+(\d+)'))[2]::int AS pa
    FROM m JOIN arkiv_rezultatesh a ON a.match_id = m.fixture_id::text
    WHERE a.parashikimi ~ '\d+\D+\d+' AND a.goditi_1x2 IS NOT NULL
),
d AS (
    SELECT r.*,
           CASE WHEN ph > pa THEN lev_1
                WHEN pa > ph THEN lev_2
                ELSE 0 - (lev_1 + lev_2) / 2.0 END AS pro_nesh,
           CASE WHEN ph > pa THEN 'vendasi'
                WHEN pa > ph THEN 'mysafiri' ELSE 'barazim' END AS drejtimi_yne
    FROM r
),
b AS (
    SELECT d.*, ntile(4) OVER (ORDER BY pro_nesh) AS brezi FROM d
)
SELECT CASE brezi WHEN 1 THEN 'a) levizi KUNDER nesh fort'
                  WHEN 2 THEN 'b) kunder nesh pak'
                  WHEN 3 THEN 'c) pro nesh pak'
                  ELSE        'd) levizi PRO nesh fort' END       AS brezi,
       count(*)                                                   AS n,
       round((avg(pro_nesh) * 100)::numeric, 2)                   AS levizja_pikperqindje,
       round(100.0*count(*) FILTER (WHERE goditi_1x2)/count(*), 1) AS goditje_1x2_pct,
       round((100.0 * stddev_samp(goditi_1x2::int::float8)
              / sqrt(count(*)))::numeric, 1)                      AS se_1x2,
       round(100.0*count(*) FILTER (WHERE goditi_skor)/count(*), 1) AS goditje_skor_pct,
       round(avg(besueshmeria), 1)                                AS besu_mes
FROM b
GROUP BY brezi
ORDER BY brezi;
