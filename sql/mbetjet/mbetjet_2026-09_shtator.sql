-- ========================================================================
-- MBETJET: 2026-09 (shtator) — cdo ndeshje me TE GJITHA sinjalet e ruajtura
-- Ekzekutoje VETEM kete skedar, pastaj Export -> CSV.
-- ========================================================================
-- Qellimi: JO te matim nese mesatarja perputhet — ate e kalibrojme vete cdo
-- nate, ndaj kalon gjithmone. Qellimi eshte MBETJA: (reali - parashikimi) per
-- cdo ndeshje, dhe pyetja nese ajo mbetje parashikohet nga dicka qe e dinim
-- PARA ndeshjes.
--
-- Mbetja s'kalibrohet dot. Mesataren e saj mund ta cosh ne zero — e bejme — por
-- nuk e ben dot te PAKORRELUAR me gjithcka, vecse duke e ndrequr vertet modelin.
--
-- PROTOKOLLI (i vendosur PARA se te shihen numrat):
--   korrik + gusht = zbulim    (aty lejohemi te kerkojme gjithcka)
--   shtator        = konfirmim (aty nuk lejohemi te kerkojme asgje)
-- Nje gjetje vlen vetem nese del ne te paren DHE ridel ne te dyten me te njejten
-- shenje. Pese heret qe u mashtruam kishin te njejten forme: nje model i gjetur
-- ne te dhena qe i kishim pare tashme.

WITH b AS (
  SELECT
    data, liga, ndeshja, is_premium,
    koef_1::numeric AS k1, koef_x::numeric AS kx, koef_2::numeric AS k2,
    parashikimi, rezultati_ft,
    split_part(replace(rezultati_ft,' ',''),'-',1)::int AS gola_vendas,
    split_part(replace(rezultati_ft,' ',''),'-',2)::int AS gola_mysafir,
    training_data AS td
  FROM arkiv_rezultatesh
  WHERE data >= '2026-09-01' AND data < (date '2026-09-01' + interval '1 month')
    AND koef_1 IS NOT NULL AND koef_x IS NOT NULL AND koef_2 IS NOT NULL
    AND koef_1::numeric > 1 AND koef_x::numeric > 1 AND koef_2::numeric > 1
    AND training_data->>'xg_1' IS NOT NULL
    AND parashikimi ~ '^[0-9]+-[0-9]+$'
    AND replace(rezultati_ft,' ','') ~ '^[0-9]+-[0-9]+$'
)
SELECT
  data, liga, ndeshja, is_premium,
  k1 AS koef_1, kx AS koef_x, k2 AS koef_2,
  round(((1/k1)/((1/k1)+(1/kx)+(1/k2)))::numeric,4) AS p1,
  round(((1/kx)/((1/k1)+(1/kx)+(1/k2)))::numeric,4) AS px,
  round(((1/k2)/((1/k1)+(1/kx)+(1/k2)))::numeric,4) AS p2,
  gola_vendas, gola_mysafir,
  (gola_vendas + gola_mysafir)                                      AS totali_real,
  parashikimi,
  (split_part(parashikimi,'-',1)::int
 + split_part(parashikimi,'-',2)::int)                              AS totali_publikuar,
  NULLIF(td->>'xg_1','')::numeric AS xg_1,
  NULLIF(td->>'xg_2','')::numeric AS xg_2,
  NULLIF(td->>'elo_1','')::numeric AS elo_1,
  NULLIF(td->>'elo_2','')::numeric AS elo_2,
  NULLIF(td->>'p_market_1','')::numeric AS p_market_1,
  NULLIF(td->>'p_market_2','')::numeric AS p_market_2,
  NULLIF(td->>'p_market_x','')::numeric AS p_market_x,
  NULLIF(td->>'modulator_1','')::numeric AS modulator_1,
  NULLIF(td->>'modulator_2','')::numeric AS modulator_2,
  NULLIF(td->>'clutch_1','')::numeric AS clutch_1,
  NULLIF(td->>'clutch_2','')::numeric AS clutch_2,
  NULLIF(td->>'draw_aff_1','')::numeric AS draw_aff_1,
  NULLIF(td->>'draw_aff_2','')::numeric AS draw_aff_2,
  NULLIF(td->>'desp_1','')::numeric AS desp_1,
  NULLIF(td->>'desp_2','')::numeric AS desp_2,
  NULLIF(td->>'vol_1','')::numeric AS vol_1,
  NULLIF(td->>'vol_2','')::numeric AS vol_2,
  NULLIF(td->>'kaos_liges','')::numeric AS kaos_liges,
  NULLIF(td->>'frac_ht_1','')::numeric AS frac_ht_1,
  NULLIF(td->>'frac_ht_2','')::numeric AS frac_ht_2,
  NULLIF(td->>'home_avg_scored','')::numeric AS home_avg_scored,
  NULLIF(td->>'home_avg_conceded','')::numeric AS home_avg_conceded,
  NULLIF(td->>'away_avg_scored','')::numeric AS away_avg_scored,
  NULLIF(td->>'away_avg_conceded','')::numeric AS away_avg_conceded,
  NULLIF(td->>'home_scored_home','')::numeric AS home_scored_home,
  NULLIF(td->>'home_conceded_home','')::numeric AS home_conceded_home,
  NULLIF(td->>'away_scored_away','')::numeric AS away_scored_away,
  NULLIF(td->>'away_conceded_away','')::numeric AS away_conceded_away,
  NULLIF(td->>'home_forma_pts','')::numeric AS home_forma_pts,
  NULLIF(td->>'away_forma_pts','')::numeric AS away_forma_pts,
  NULLIF(td->>'home_volatility','')::numeric AS home_volatility,
  NULLIF(td->>'away_volatility','')::numeric AS away_volatility,
  NULLIF(td->>'home_rest_days','')::numeric AS home_rest_days,
  NULLIF(td->>'away_rest_days','')::numeric AS away_rest_days,
  NULLIF(td->>'home_win_rate','')::numeric AS home_win_rate,
  NULLIF(td->>'away_win_rate','')::numeric AS away_win_rate,
  NULLIF(td->>'pozicion_1','')::numeric AS pozicion_1,
  NULLIF(td->>'pozicion_2','')::numeric AS pozicion_2,
  NULLIF(td->>'pike_1','')::numeric AS pike_1,
  NULLIF(td->>'pike_2','')::numeric AS pike_2,
  NULLIF(td->>'diferenca_golash_1','')::numeric AS diferenca_golash_1,
  NULLIF(td->>'diferenca_golash_2','')::numeric AS diferenca_golash_2,
  NULLIF(td->>'ndeshje_luajtura_1','')::numeric AS ndeshje_luajtura_1,
  NULLIF(td->>'ndeshje_luajtura_2','')::numeric AS ndeshje_luajtura_2,
  NULLIF(td->>'total_ekipe_liga','')::numeric AS total_ekipe_liga,
  NULLIF(td->>'ah_line','')::numeric AS ah_line,
  NULLIF(td->>'ah_home_odds','')::numeric AS ah_home_odds,
  NULLIF(td->>'ah_away_odds','')::numeric AS ah_away_odds,
  NULLIF(td->>'ou_over_odds','')::numeric AS ou_over_odds,
  NULLIF(td->>'ou_under_odds','')::numeric AS ou_under_odds,
  NULLIF(td->>'streak_1','')::numeric AS streak_1,
  NULLIF(td->>'streak_2','')::numeric AS streak_2,
  NULLIF(td->>'kongjestion_1','')::numeric AS kongjestion_1,
  NULLIF(td->>'kongjestion_2','')::numeric AS kongjestion_2,
  NULLIF(td->>'lendime_1','')::numeric AS lendime_1,
  NULLIF(td->>'lendime_2','')::numeric AS lendime_2,
  NULLIF(td->>'total_form','')::numeric AS total_form,
  NULLIF(td->>'total_target','')::numeric AS total_target,
  (td->>'elo_vlen') AS elo_vlen,
  (td->>'is_derbi') AS is_derbi,
  (td->>'build') AS build,
  (td->>'burimi_xg') AS burimi_xg,
  (td->>'tipi_ndeshjes') AS tipi_ndeshjes,
  NULLIF(td->'prob_1x2_mc'->>'p1','')::numeric AS mc_p1,
  NULLIF(td->'prob_1x2_mc'->>'px','')::numeric AS mc_px,
  NULLIF(td->'prob_1x2_mc'->>'p2','')::numeric AS mc_p2,
  'x'                                                               AS fund
FROM b
ORDER BY data, ndeshja;
