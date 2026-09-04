-- ==================== PYETJA 1 ====================
-- Sa nga ndeshjet aktive u llogaritën me kodin e ri?
-- `elo_vlen` shkruhet te training_data VETËM nga kodi i ri, ndaj mungesa e tij
-- e identifikon me siguri nje parashikim te prodhuar para deploy-it.
SELECT CASE WHEN (training_data::jsonb ? 'elo_vlen') THEN 'a) KODI I RI'
            ELSE                                          'b) kodi i vjeter' END AS versioni,
       count(*)                                    AS n,
       min(data)                                   AS nga,
       max(data)                                   AS deri,
       round(avg(besueshmeria), 1)                 AS besu_mes
FROM predictions
WHERE data::date >= current_date
  AND (statusi IS NULL
       OR statusi NOT IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD'))
  AND training_data IS NOT NULL
GROUP BY 1
ORDER BY 1;


-- ==================== PYETJA 2 ====================
-- Detaji per ndeshje: versioni, gjendja e ELO-s, dhe besueshmeria e ruajtur
-- kundrejt asaj qe do te jepte formula v3.
--
-- ⚠️ SKORI nuk rillogaritet dot ketu. Ai kerkon Monte Carlo mbi nje rrjete te
--    re, dhe rregullimi i ELO-s e zhvendos vete lambda-n. Vetem rigjenerimi e
--    tregon skorin e ri. Kjo pyetesi tregon KUSH do te preket dhe SA.
WITH b AS (
    SELECT p.id, p.data, p.ora, p.ndeshja, p.liga_emri,
           p.rezultati_sakt, p.besueshmeria,
           (p.training_data::jsonb ? 'elo_vlen')                        AS kodi_i_ri,
           (p.training_data::jsonb ->> 'elo_1')::numeric                 AS elo1,
           (p.training_data::jsonb ->> 'elo_2')::numeric                 AS elo2,
           (p.training_data::jsonb ->> 'home_win_rate')::numeric         AS wr1,
           (p.training_data::jsonb ->> 'away_win_rate')::numeric         AS wr2,
           (p.tregjet::jsonb ->> '1')::numeric                           AS p1,
           (p.tregjet::jsonb ->> 'X')::numeric                           AS px,
           (p.tregjet::jsonb ->> '2')::numeric                           AS p2,
           round((p.training_data::jsonb ->> 'xg_1')::numeric, 2)        AS xg1,
           round((p.training_data::jsonb ->> 'xg_2')::numeric, 2)        AS xg2
    FROM predictions p
    WHERE p.data::date >= current_date
      AND (p.statusi IS NULL
           OR p.statusi NOT IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD'))
      AND p.training_data IS NOT NULL
      AND p.tregjet IS NOT NULL
),
c AS (
    SELECT b.*,
           ((GREATEST(p1, px, p2) - 0.33) / 0.67)                        AS sinjal,
           CASE WHEN p1 > p2 AND p1 > px THEN wr1
                WHEN p2 > p1 AND p2 > px THEN wr2
                ELSE 0.35 END                                            AS forma_score
    FROM b
)
SELECT data, ora, ndeshja, liga_emri,
       CASE WHEN kodi_i_ri THEN 'i ri' ELSE 'I VJETER' END               AS versioni,
       rezultati_sakt                                                    AS skori_aktual,
       xg1, xg2,
       elo1, elo2,
       CASE WHEN elo1 = 600 AND elo2 = 600 THEN 'te dy 600 -> ELO fiket + s''eshte derbi'
            WHEN elo1 = 600 OR  elo2 = 600 THEN 'njeri 600 -> ELO FIKET'
            ELSE                                'te dy reale -> pa ndryshim' END AS efekti_elo,
       besueshmeria                                                      AS besu_e_ruajtur,
       LEAST(92.0, GREATEST(55.0,
             round(66.7 + (0.75*sinjal + 0.25*forma_score) * 24.4, 1)))  AS besu_v3,
       round(LEAST(92.0, GREATEST(55.0,
             66.7 + (0.75*sinjal + 0.25*forma_score) * 24.4))
             - besueshmeria, 1)                                          AS besu_diferenca
FROM c
ORDER BY data, ora;


-- ==================== PYETJA 3 ====================
-- Permbledhja: sa ndeshje do te ndryshojne, dhe sa fort.
WITH b AS (
    SELECT (p.training_data::jsonb ? 'elo_vlen')                  AS kodi_i_ri,
           (p.training_data::jsonb ->> 'elo_1')::numeric           AS elo1,
           (p.training_data::jsonb ->> 'elo_2')::numeric           AS elo2,
           (p.training_data::jsonb ->> 'home_win_rate')::numeric   AS wr1,
           (p.training_data::jsonb ->> 'away_win_rate')::numeric   AS wr2,
           (p.tregjet::jsonb ->> '1')::numeric                     AS p1,
           (p.tregjet::jsonb ->> 'X')::numeric                     AS px,
           (p.tregjet::jsonb ->> '2')::numeric                     AS p2,
           p.besueshmeria
    FROM predictions p
    WHERE p.data::date >= current_date
      AND (p.statusi IS NULL
           OR p.statusi NOT IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD'))
      AND p.training_data IS NOT NULL
      AND p.tregjet IS NOT NULL
),
c AS (
    SELECT b.*,
           LEAST(92.0, GREATEST(55.0,
             66.7 + (0.75*((GREATEST(p1, px, p2) - 0.33)/0.67)
                   + 0.25*(CASE WHEN p1 > p2 AND p1 > px THEN wr1
                                WHEN p2 > p1 AND p2 > px THEN wr2
                                ELSE 0.35 END)) * 24.4)) AS besu_v3
    FROM b
)
SELECT count(*)                                                       AS ndeshje_aktive,
       count(*) FILTER (WHERE kodi_i_ri)                              AS me_kodin_e_ri,
       count(*) FILTER (WHERE NOT kodi_i_ri)                          AS me_kodin_e_vjeter,
       count(*) FILTER (WHERE elo1 = 600 OR elo2 = 600)               AS elo_do_fiket,
       round(100.0*count(*) FILTER (WHERE elo1 = 600 OR elo2 = 600)
             /NULLIF(count(*),0), 1)                                  AS elo_do_fiket_pct,
       count(*) FILTER (WHERE elo1 = 600 AND elo2 = 600)              AS derbi_i_rreme,
       round(avg(besueshmeria), 1)                                    AS besu_mes_tani,
       round(avg(besu_v3), 1)                                         AS besu_mes_v3,
       round(avg(besu_v3 - besueshmeria), 2)                          AS zhvendosja_mes,
       round(max(abs(besu_v3 - besueshmeria)), 1)                     AS zhvendosja_max
FROM c;
