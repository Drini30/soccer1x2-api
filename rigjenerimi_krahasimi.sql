-- ==========================================================
-- RIGJENERIM I NDESHJEVE TE PALUAJTURA + KRAHASIM PARA/PAS
-- ==========================================================
-- Qellimi: te shohim si e ndryshoi parashikimet formula e re (ELO i fikur kur
-- mungon, besueshmeria v3, WINNER_PRAG 0.10, W_ELO 0.05) dhe — pasi ndeshjet te
-- luhen — cila prej dy versioneve goditi me shume.
--
-- ⚠️ RENDI KA RENDESI. Hapi 1 duhet ekzekutuar PARA fshirjes, perndryshe s'ka
--    me me cfare te krahasohet dhe nuk kthehet mbrapsht.
--
-- ⚠️ PROVABLY FAIR. Hash-i eshte premtim publik. Nese nje commitment i eshte
--    shfaqur tashme nje perdoruesi dhe parashikimi rigjenerohet, premtimi i
--    publikuar nuk perputhet me te riun. Hapi 3 fshin VETEM rreshtat 'kycur'
--    (te pazbuluar); ato 'zbuluar' jane prova publike dhe MBETEN.
--
-- ⚠️ DISKRIMINUESI eshte `statusi`, JO `rezultati IS NULL`. Kolona `rezultati`
--    mban "0 - 0" per ndeshjet e paluajtura, kurre NULL — nje kusht i tille nuk
--    perputhet kurre dhe nuk do te fshinte asgje.
-- ==========================================================


-- ==================== HAPI 1 — FOTOGRAFIA (ekzekuto i pari) ====================
DROP TABLE IF EXISTS snapshot_para_rigjenerimit;

CREATE TABLE snapshot_para_rigjenerimit AS
SELECT p.id,
       p.ndeshja,
       p.data,
       p.ora,
       p.liga_emri,
       p.statusi,
       p.rezultati_sakt                                          AS skori_vjeter,
       p.koef_rez_sakt                                           AS koef_vjeter,
       p.besueshmeria                                            AS besu_vjeter,
       round((p.training_data::jsonb ->> 'xg_1')::numeric, 3)     AS xg1_vjeter,
       round((p.training_data::jsonb ->> 'xg_2')::numeric, 3)     AS xg2_vjeter,
       round((p.tregjet::jsonb ->> '1')::numeric, 4)              AS p1_vjeter,
       round((p.tregjet::jsonb ->> 'X')::numeric, 4)              AS px_vjeter,
       round((p.tregjet::jsonb ->> '2')::numeric, 4)              AS p2_vjeter,
       (p.training_data::jsonb ->> 'elo_1')                       AS elo1_vjeter,
       (p.training_data::jsonb ->> 'elo_2')                       AS elo2_vjeter,
       now()                                                      AS marre_ne
FROM predictions p
WHERE p.statusi IS NULL
   OR p.statusi NOT IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD');

SELECT count(*) AS ruajtur, min(data) AS nga, max(data) AS deri
FROM snapshot_para_rigjenerimit;


-- ==================== HAPI 2 — SHIKO PARA SE TE FSHISH ====================
SELECT count(*) FILTER (WHERE statusi IS NULL
                        OR statusi NOT IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD'))
         AS do_fshihen,
       count(*) FILTER (WHERE statusi IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD'))
         AS mbetet_arkivi,
       count(*) AS gjithsej
FROM predictions;


-- ==================== HAPI 3 — FSHI ====================
DELETE FROM provably_fair WHERE statusi = 'kycur';

DELETE FROM predictions
WHERE statusi IS NULL
   OR statusi NOT IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD');


-- ==================== HAPI 4 — VERIFIKO QE ARKIVI S'U PREK ====================
-- `mbetet_arkivi` duhet te jete SAKTESISHT i njejti numer si te hapi 2.
SELECT count(*) FILTER (WHERE statusi IS NULL
                        OR statusi NOT IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD'))
         AS mbetet_te_paluajtura,
       count(*) FILTER (WHERE statusi IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD'))
         AS mbetet_arkivi
FROM predictions;

SELECT statusi, count(*) FROM provably_fair GROUP BY statusi;


-- ==================== HAPI 5 — RIGJENERO (jo SQL) ====================
-- Thirri ne shfletues, nje per dite. Zgjat nje-dy minuta secila.
--
--   https://soccer1x2-api.onrender.com/api/cron/gjenero?date=2026-09-04
--   https://soccer1x2-api.onrender.com/api/cron/gjenero?date=2026-09-05
--
-- Parametri ?date= e detyron punen e rende menjehere, pa throttle.


-- ==================== HAPI 6 — KRAHASIMI (pas rigjenerimit) ====================
SELECT s.data,
       s.ora,
       s.ndeshja,
       s.skori_vjeter,
       p.rezultati_sakt                                       AS skori_ri,
       (s.skori_vjeter IS DISTINCT FROM p.rezultati_sakt)      AS ndryshoi,
       s.xg1_vjeter, round((p.training_data::jsonb ->> 'xg_1')::numeric, 3) AS xg1_ri,
       s.xg2_vjeter, round((p.training_data::jsonb ->> 'xg_2')::numeric, 3) AS xg2_ri,
       s.besu_vjeter, p.besueshmeria                           AS besu_ri,
       round(p.besueshmeria - s.besu_vjeter, 1)                AS besu_diferenca,
       (p.training_data::jsonb ->> 'elo_vlen')                 AS elo_vlen,
       s.elo1_vjeter, s.elo2_vjeter,
       s.koef_vjeter, p.koef_rez_sakt                          AS koef_ri
FROM snapshot_para_rigjenerimit s
JOIN predictions p
  ON p.ndeshja = s.ndeshja AND p.data = s.data
ORDER BY s.data, s.ora;


-- ==================== HAPI 7 — PERMBLEDHJA E NDRYSHIMEVE ====================
SELECT count(*)                                                        AS ndeshje,
       count(*) FILTER (WHERE s.skori_vjeter IS DISTINCT FROM p.rezultati_sakt) AS ndryshuan,
       round(100.0*count(*) FILTER (WHERE s.skori_vjeter IS DISTINCT FROM p.rezultati_sakt)
             /NULLIF(count(*),0), 1)                                   AS ndryshuan_pct,
       count(*) FILTER (WHERE (p.training_data::jsonb ->> 'elo_vlen') = 'false') AS elo_i_fikur,
       count(*) FILTER (WHERE (p.training_data::jsonb ->> 'elo_vlen') = 'false'
                          AND s.skori_vjeter IS DISTINCT FROM p.rezultati_sakt) AS ndryshuan_ku_elo_u_fik,
       round(avg(p.besueshmeria - s.besu_vjeter), 2)                   AS besu_zhvendosja_mes,
       round(avg(abs((p.training_data::jsonb ->> 'xg_1')::numeric - s.xg1_vjeter)), 3) AS xg1_levizja_mes,
       round(avg(abs((p.training_data::jsonb ->> 'xg_2')::numeric - s.xg2_vjeter)), 3) AS xg2_levizja_mes
FROM snapshot_para_rigjenerimit s
JOIN predictions p
  ON p.ndeshja = s.ndeshja AND p.data = s.data;


-- ==================== HAPI 8 — KUSH GODITI (pasi te luhen) ====================
-- Ekzekutoje pas 2-3 ditesh, kur ndeshjet te kene mbaruar.
-- `barazim` = te dy versionet e njejte, pra nuk ndajne asgje.
WITH k AS (
    SELECT s.ndeshja, s.data,
           s.skori_vjeter,
           p.rezultati_sakt AS skori_ri,
           p.rezultati      AS reale
    FROM snapshot_para_rigjenerimit s
    JOIN predictions p ON p.ndeshja = s.ndeshja AND p.data = s.data
    WHERE p.statusi IN ('FT','AET','PEN')
)
SELECT count(*)                                                          AS ndeshje_te_luajtura,
       count(*) FILTER (WHERE skori_vjeter = skori_ri)                   AS barazim,
       count(*) FILTER (WHERE skori_vjeter IS DISTINCT FROM skori_ri)    AS ndryshuan,
       count(*) FILTER (WHERE skori_vjeter IS DISTINCT FROM skori_ri
                          AND replace(skori_vjeter,' ','') = replace(reale,' ','')) AS goditi_VETEM_i_vjetri,
       count(*) FILTER (WHERE skori_vjeter IS DISTINCT FROM skori_ri
                          AND replace(skori_ri,' ','') = replace(reale,' ',''))     AS goditi_VETEM_i_riu
FROM k;
