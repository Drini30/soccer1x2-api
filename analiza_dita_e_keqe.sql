-- ############################################################################
-- ANALIZA E NJE DITE TE KEQE
-- ############################################################################
--
-- KURTHI QE DUHET SHMANGUR:
-- Me 12% norme goditjeje dhe ~30 ndeshje, pritja eshte 3.6 goditje me devijim
-- standard ±1.8. Ditet me 1 goditje jane NORMALE. Ditet me 0 ndodhin rregullisht.
-- Nese e gjykojme diten nga goditjet, do te "zbulojme" prishje qe s'ekzistojne
-- dhe do te ndryshojme kod pa arsye — gabimi me i shtrenjte i mundshem.
--
-- MATESI I DUHUR: RENDI I REZULTATIT REAL NE SHPERNDARJEN TONE.
-- Skori i vertete doli i 2-ti ne listen tone? Ishim afer, patem fat te keq.
-- Doli i 14-ti? Lambda jone ishte e gabuar per ate ndeshje.
-- Ky mates perdor GJITHE shperndarjen, jo nje bit goditi/s'goditi, ndaj ka fuqi
-- statistikore edhe me 30 ndeshje — ndersa goditjet nuk kane.
-- ############################################################################


-- ==================== PYETJA 1 — SA E PAMUNDSHME ISHTE KJO DITE? ====================
-- Pergjigjja e drejtperdrejte per "skandal": llogarit probabiliteten EKZAKTE
-- binomiale te te pasurit kaq pak goditje ose me pak, duke marre si baze normen
-- tone historike (jo nje numer te sajuar — nxirret nga arkivi ne vend).
--
-- `p_kete_ose_me_keq` eshte gjykimi:
--     mbi 0.20  -> dite krejt e zakonshme. S'ka asgje per te analizuar.
--     0.05-0.20 -> e keqe, por brenda pritjes. Nje here ne 5-20 dite.
--     nen 0.01  -> vertet e jashtezakonshme. Vlen te kerkojme shkakun.
-- Kujto: me 30 dite ne muaj, nje dite me p = 0.03 pritet TE NDODHE cdo muaj.
WITH baza AS (
    SELECT avg(goditi_skor::int)::float8 AS p_skor,
           avg(goditi_1x2::int)::float8  AS p_1x2,
           count(*)                      AS n_baza
    FROM arkiv_rezultatesh
    WHERE goditi_skor IS NOT NULL AND goditi_1x2 IS NOT NULL
),
sot AS (
    SELECT count(*)::int AS n,
           count(*) FILTER (
               WHERE regexp_replace(rezultati_sakt, '\s', '', 'g')
                   = regexp_replace(rezultati,      '\s', '', 'g'))::int AS gd_skor,
           count(*) FILTER (
               WHERE sign((regexp_match(rezultati_sakt, '(\d+)\D+(\d+)'))[1]::int
                        - (regexp_match(rezultati_sakt, '(\d+)\D+(\d+)'))[2]::int)
                   = sign((regexp_match(rezultati, '(\d+)\D+(\d+)'))[1]::int
                        - (regexp_match(rezultati, '(\d+)\D+(\d+)'))[2]::int))::int AS gd_1x2
    FROM predictions
    WHERE data::date = current_date
      AND statusi IN ('FT','AET','PEN','AWD','WO')
      AND rezultati      ~ '\d+\D+\d+'
      AND rezultati_sakt ~ '\d+\D+\d+'
),
b2 AS (
    SELECT sum( (factorial(s.n) / (factorial(i) * factorial(s.n - i)))
                * power(b.p_skor::numeric, i)
                * power((1 - b.p_skor)::numeric, s.n - i) ) AS p_skor_ose_me_keq
    FROM sot s CROSS JOIN baza b
    CROSS JOIN LATERAL generate_series(0, s.gd_skor) AS i
)
SELECT s.n                                                   AS ndeshje_mbaruar,
       s.gd_skor                                             AS goditje_skor,
       s.gd_1x2                                              AS goditje_1x2,
       round((100.0 * b.p_skor)::numeric, 2)                 AS norma_historike_skor_pct,
       round((s.n * b.p_skor)::numeric, 2)                   AS pritej_skor,
       round((sqrt(s.n * b.p_skor * (1 - b.p_skor)))::numeric, 2) AS sd_pritur,
       round(((s.gd_skor - s.n * b.p_skor)
              / NULLIF(sqrt(s.n * b.p_skor * (1 - b.p_skor)), 0))::numeric, 2) AS sigma_skor,
       round(b2.p_skor_ose_me_keq, 4)                        AS p_kete_ose_me_keq,
       round((100.0 * b.p_1x2)::numeric, 2)                  AS norma_historike_1x2_pct,
       round((s.n * b.p_1x2)::numeric, 2)                    AS pritej_1x2,
       b.n_baza                                              AS ndeshje_ne_baze
FROM sot s CROSS JOIN baza b CROSS JOIN b2;


-- ==================== PYETJA 2 — NDESHJE PER NDESHJE, ME RENDIN E REALIT ====================
-- Detaji i plote. Kolona qe ka me shume rendesi eshte `rendi_real`: ne cilen
-- pozicion e kishim skorin e vertete ne listen tone te 50,000 simulimeve.
--
--   rendi_real 1     -> e patem ne krye dhe... goditem (ose skori u shkrua ndryshe)
--   rendi_real 2-4   -> ishim shume afer. Fat i keq, jo defekt.
--   rendi_real 5-10  -> brenda rrezes, por lambda ishte e zhvendosur
--   rendi_real > 12  -> ndeshje qe NUK e kishim fare. Ketu kerkohet shkaku.
--
-- `p_real` eshte probabiliteti qe i dhame skorit qe ndodhi vertet. Nese eshte
-- nen 1%, ajo ndeshje ishte jashte modelit tone.
--
-- `gabimi_totali` = totali real - totali yne (xg_1+xg_2). Nese te gjitha jane
-- POZITIVE, kemi nenvleresuar golat sot — kjo eshte nje anshmeri, jo fat.
WITH p AS (
    SELECT id, ndeshja, liga_emri, ora_sakte, rezultati_sakt, rezultati,
           besueshmeria, koef_rez_sakt, is_premium, koef_1, koef_x, koef_2,
           dist_gola::jsonb                                    AS dg,
           regexp_replace(rezultati_sakt, '\s', '', 'g')       AS skor_pub,
           regexp_replace(rezultati,      '\s', '', 'g')       AS skor_real,
           (regexp_match(rezultati_sakt, '(\d+)\D+(\d+)'))[1]::int AS ph,
           (regexp_match(rezultati_sakt, '(\d+)\D+(\d+)'))[2]::int AS pa,
           (regexp_match(rezultati,      '(\d+)\D+(\d+)'))[1]::int AS gh,
           (regexp_match(rezultati,      '(\d+)\D+(\d+)'))[2]::int AS ga,
           (training_data::jsonb ->> 'xg_1')::numeric          AS xg1,
           (training_data::jsonb ->> 'xg_2')::numeric          AS xg2,
           (training_data::jsonb ? 'elo_vlen')                 AS kodi_i_ri
    FROM predictions
    WHERE data::date = current_date
      AND statusi IN ('FT','AET','PEN','AWD','WO')
      AND rezultati      ~ '\d+\D+\d+'
      AND rezultati_sakt ~ '\d+\D+\d+'
      AND dist_gola IS NOT NULL AND dist_gola::jsonb <> '{}'::jsonb
),
x AS (
    SELECT p.id, p.skor_real, e.k AS skori, e.v::numeric AS cnt,
           row_number() OVER (PARTITION BY p.id ORDER BY e.v::numeric DESC) AS rendi
    FROM p, LATERAL jsonb_each_text(p.dg) AS e(k, v)
),
rk AS (
    SELECT id,
           min(rendi)  FILTER (WHERE skori = skor_real) AS rendi_real,
           max(cnt)    FILTER (WHERE skori = skor_real) AS cnt_real
    FROM x GROUP BY id
)
SELECT p.ora_sakte                                        AS ora,
       p.ndeshja,
       p.liga_emri                                        AS liga,
       p.rezultati_sakt                                   AS publikuam,
       p.rezultati                                        AS ndodhi,
       CASE WHEN p.skor_pub = p.skor_real THEN '✔' ELSE '' END AS goditi,
       COALESCE(rk.rendi_real::text, '>50')               AS rendi_real,
       round(100.0 * COALESCE(rk.cnt_real, 0) / 50000.0, 2) AS p_real_pct,
       abs(p.ph - p.gh) + abs(p.pa - p.ga)                AS gabimi_gola,
       (p.gh + p.ga) - (p.ph + p.pa)                      AS gabimi_totali_ndaj_pub,
       round((p.gh + p.ga) - (p.xg1 + p.xg2), 2)          AS gabimi_totali_ndaj_xg,
       CASE WHEN sign(p.ph - p.pa) = sign(p.gh - p.ga) THEN 'drejtim OK'
            ELSE 'DREJTIM GABIM' END                      AS drejtimi,
       round(p.xg1, 2)                                    AS xg1,
       round(p.xg2, 2)                                    AS xg2,
       p.besueshmeria                                     AS besu,
       p.koef_rez_sakt                                    AS koef,
       p.koef_1, p.koef_2,
       CASE WHEN p.is_premium THEN 'PPM' ELSE '' END      AS ppm,
       CASE WHEN p.kodi_i_ri THEN 'i ri' ELSE 'I VJETER' END AS versioni
FROM p LEFT JOIN rk ON rk.id = p.id
ORDER BY COALESCE(rk.rendi_real, 999) DESC, p.ora_sakte;


-- ==================== PYETJA 3 — RENDI MESATAR: SOT KUNDREJT HISTORIKUT ====================
-- Testi vendimtar. Nese renditja mesatare e skorit real eshte sot ~e njejte me
-- historikun, atehere modeli punoi njesoj si gjithmone dhe dita ishte thjesht e
-- pafat. Nese renditja eshte dukshem me e keqe, dicka ndryshoi.
--
-- Ky mates ka fuqi me 30 ndeshje sepse eshte i vazhdueshem, jo binar.
-- Shiko `sigma`: nen 2.0 eshte zhurme, mbi 3.0 eshte sinjal.
WITH b AS (
    SELECT a.match_id, a.data::date AS dita,
           regexp_replace(a.rezultati_ft, '\s', '', 'g') AS skor_real,
           a.dist_gola::jsonb AS dg
    FROM arkiv_rezultatesh a
    WHERE a.dist_gola IS NOT NULL AND a.dist_gola::jsonb <> '{}'::jsonb
      AND a.rezultati_ft ~ '\d+\D+\d+'
    UNION ALL
    SELECT p.id, p.data::date,
           regexp_replace(p.rezultati, '\s', '', 'g'),
           p.dist_gola::jsonb
    FROM predictions p
    WHERE p.data::date = current_date
      AND p.statusi IN ('FT','AET','PEN','AWD','WO')
      AND p.rezultati ~ '\d+\D+\d+'
      AND p.dist_gola IS NOT NULL AND p.dist_gola::jsonb <> '{}'::jsonb
      AND NOT EXISTS (SELECT 1 FROM arkiv_rezultatesh a2 WHERE a2.match_id = p.id)
),
x AS (
    SELECT b.match_id, b.dita, b.skor_real, e.k AS skori,
           row_number() OVER (PARTITION BY b.match_id ORDER BY e.v::numeric DESC) AS rendi,
           e.v::numeric AS cnt
    FROM b, LATERAL jsonb_each_text(b.dg) AS e(k, v)
),
rk AS (
    SELECT match_id, dita,
           COALESCE(min(rendi) FILTER (WHERE skori = skor_real), 60) AS rendi_real,
           COALESCE(max(cnt)   FILTER (WHERE skori = skor_real), 0) / 50000.0 AS p_real
    FROM x GROUP BY match_id, dita
),
g AS (
    SELECT CASE WHEN dita = current_date THEN 'a) SOT'
                ELSE 'b) i gjithe historiku' END AS grupi,
           rendi_real, p_real
    FROM rk
)
SELECT grupi,
       count(*)                                   AS ndeshje,
       round(avg(rendi_real)::numeric, 2)         AS rendi_mes,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY rendi_real))::numeric, 1) AS rendi_mesor,
       round((100.0 * avg(p_real))::numeric, 2)   AS p_real_mes_pct,
       round(100.0*count(*) FILTER (WHERE rendi_real = 1)/count(*), 1)  AS ishte_i_pari_pct,
       round(100.0*count(*) FILTER (WHERE rendi_real <= 3)/count(*), 1) AS ne_top3_pct,
       round(100.0*count(*) FILTER (WHERE rendi_real <= 5)/count(*), 1) AS ne_top5_pct,
       round(100.0*count(*) FILTER (WHERE rendi_real > 12)/count(*), 1) AS jashte_modelit_pct,
       round((stddev_samp(rendi_real)/sqrt(count(*)))::numeric, 3)      AS se_rendi
FROM g
GROUP BY grupi
ORDER BY grupi;


-- ==================== PYETJA 4 — KU ESHTE GABIMI: DREJTIMI APO TOTALI? ====================
-- Nje skor gabon ne dy menyra te pavarura: e humbem se KUSH fitoi, ose e humbem
-- se SA gola u shenuan. Ky zberthim tregon cilen.
--
-- Nese sot 'drejtimi OK, totali gabim' dominon, problemi eshte lambda totale.
-- Nese 'DREJTIM GABIM' eshte i larte kundrejt historikut, problemi eshte
-- supremacia — dhe atehere WINNER_PRAG=0.10 duhet rishikuar.
WITH b AS (
    SELECT 'a) SOT'::text AS grupi,
           (regexp_match(rezultati_sakt, '(\d+)\D+(\d+)'))[1]::int AS ph,
           (regexp_match(rezultati_sakt, '(\d+)\D+(\d+)'))[2]::int AS pa,
           (regexp_match(rezultati,      '(\d+)\D+(\d+)'))[1]::int AS gh,
           (regexp_match(rezultati,      '(\d+)\D+(\d+)'))[2]::int AS ga
    FROM predictions
    WHERE data::date = current_date
      AND statusi IN ('FT','AET','PEN','AWD','WO')
      AND rezultati ~ '\d+\D+\d+' AND rezultati_sakt ~ '\d+\D+\d+'
    UNION ALL
    SELECT 'b) historiku',
           (regexp_match(parashikimi,  '(\d+)\D+(\d+)'))[1]::int,
           (regexp_match(parashikimi,  '(\d+)\D+(\d+)'))[2]::int,
           (regexp_match(rezultati_ft, '(\d+)\D+(\d+)'))[1]::int,
           (regexp_match(rezultati_ft, '(\d+)\D+(\d+)'))[2]::int
    FROM arkiv_rezultatesh
    WHERE rezultati_ft ~ '\d+\D+\d+' AND parashikimi ~ '\d+\D+\d+'
)
SELECT grupi,
       count(*)                                                        AS n,
       round(100.0*count(*) FILTER (WHERE ph = gh AND pa = ga)/count(*), 2) AS skor_i_plote_pct,
       round(100.0*count(*) FILTER (WHERE sign(ph-pa) = sign(gh-ga))/count(*), 1) AS drejtim_ok_pct,
       round(100.0*count(*) FILTER (WHERE sign(ph-pa) = sign(gh-ga)
                                      AND (ph+pa) = (gh+ga))/count(*), 1) AS drejtim_dhe_total_ok_pct,
       round(100.0*count(*) FILTER (WHERE (ph+pa) = (gh+ga))/count(*), 1) AS total_ok_pct,
       round(avg(gh+ga)::numeric, 2)                                   AS totali_real_mes,
       round(avg(ph+pa)::numeric, 2)                                   AS totali_pub_mes,
       round(avg((gh+ga) - (ph+pa))::numeric, 2)                       AS anshmeria_totalit,
       round(avg(abs(ph-gh) + abs(pa-ga))::numeric, 2)                 AS gabimi_gola_mes
FROM b
GROUP BY grupi
ORDER BY grupi;


-- ==================== PYETJA 5 — DITA SOT NE KONTEKST: 30 DITET E FUNDIT ====================
-- Kjo e mbyll debatin vizualisht. Shiko kolonen `goditje_pct` per 30 ditet e
-- fundit. Nese luhatet nga 0% deri 30% rregullisht, atehere sot nuk eshte
-- "skandal" — eshte thjesht nje pike ne nje shperndarje qe eshte gjithmone kaq
-- e gjere.
--
-- `rendi_mes` eshte matesi i vertete: nese ai qendron ~i njejte cdo dite ndersa
-- goditjet kercejne, atehere modeli eshte i qendrueshem dhe goditjet jane fat.
WITH b AS (
    SELECT a.match_id, a.data::date AS dita,
           regexp_replace(a.rezultati_ft, '\s', '', 'g') AS skor_real,
           regexp_replace(a.parashikimi,  '\s', '', 'g') AS skor_pub,
           a.dist_gola::jsonb AS dg
    FROM arkiv_rezultatesh a
    WHERE a.data::date >= current_date - 30
      AND a.rezultati_ft ~ '\d+\D+\d+' AND a.parashikimi ~ '\d+\D+\d+'
      AND a.dist_gola IS NOT NULL AND a.dist_gola::jsonb <> '{}'::jsonb
    UNION ALL
    SELECT p.id, p.data::date,
           regexp_replace(p.rezultati,      '\s', '', 'g'),
           regexp_replace(p.rezultati_sakt, '\s', '', 'g'),
           p.dist_gola::jsonb
    FROM predictions p
    WHERE p.data::date >= current_date - 30
      AND p.statusi IN ('FT','AET','PEN','AWD','WO')
      AND p.rezultati ~ '\d+\D+\d+' AND p.rezultati_sakt ~ '\d+\D+\d+'
      AND p.dist_gola IS NOT NULL AND p.dist_gola::jsonb <> '{}'::jsonb
      AND NOT EXISTS (SELECT 1 FROM arkiv_rezultatesh a2 WHERE a2.match_id = p.id)
),
x AS (
    SELECT b.match_id, b.dita, b.skor_real, b.skor_pub, e.k AS skori,
           row_number() OVER (PARTITION BY b.match_id ORDER BY e.v::numeric DESC) AS rendi
    FROM b, LATERAL jsonb_each_text(b.dg) AS e(k, v)
),
rk AS (
    SELECT match_id, dita, bool_or(skor_pub = skor_real) AS goditi,
           COALESCE(min(rendi) FILTER (WHERE skori = skor_real), 60) AS rendi_real
    FROM x GROUP BY match_id, dita
)
SELECT dita,
       count(*)                                                  AS ndeshje,
       count(*) FILTER (WHERE goditi)                            AS goditje,
       round(100.0*count(*) FILTER (WHERE goditi)/count(*), 1)   AS goditje_pct,
       round(avg(rendi_real)::numeric, 2)                        AS rendi_mes,
       round(100.0*count(*) FILTER (WHERE rendi_real <= 3)/count(*), 1) AS ne_top3_pct,
       CASE WHEN dita = current_date THEN '  <<< SOT' ELSE '' END AS shenim
FROM rk
GROUP BY dita
ORDER BY dita DESC;
