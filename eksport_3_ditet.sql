-- ############################################################################
-- EKSPORT: 3 DITET E FUNDIT + TE GJITHA NDESHJET NS
-- Zinxhiri i plote i parashikimit, nga forma deri te perzgjedhja.
-- ############################################################################
--
-- PERFSHIN: cdo ndeshje te 3 diteve te fundit (te mbaruar ose jo) DHE cdo
-- parashikim qe ende s'ka luajtur, pavaresisht dates.
-- Per ndeshjet NS kolonat e rezultatit dalin bosh; e gjithe ana e parashikimit
-- (xG, moduluesit, tregu, shperndarja, perzgjedhja) eshte e plote.
--
-- SHENIME PER LEXIMIN:
--   • `xg_1_para/xg_2_para` ruhen PARA normalizimit XG_NORM.
--     `xg1_norm/xg2_norm` jane ato qe vertet simuluan dhe zgjodhen.
--   • `tregjet` dhe `prob_1x2_mc` jane PAS perzierjes me tregun (W_MKT_FINAL=0.35).
--     `p1_mc/px_mc/p2_mc` e kthejne mbrapsht ate perzierje — keto pa rregulli
--     i fituesit.
--   • `p_tot_*` jane masa e probabilitetit qe shperndarja jone i jep secilit
--     total. Nese `p_tot_4plus` eshte i larte por `tot_pub` eshte 2 ose 3, po
--     publikojme brenda brezit te ngushte qe u tregua fatal me 4-5 shtator.
--   • Konstantet e supozuara: XG_NORM 0.08/0.87 (vendas), -0.02/0.97 (mysafir),
--     XG_FLOOR 0.10, W_MKT_FINAL 0.35. Nese /api/cron/kalibro i ka rishkruar,
--     kontrollo /api/status dhe ma thuaj — rikrijimi ndryshon.
-- ############################################################################
WITH p AS (
    SELECT id, data, ora, ora_sakte, ndeshja, liga_emri, statusi, minuta,
           rezultati_sakt, rezultati, besueshmeria, koef_rez_sakt,
           is_premium, is_value, is_bllof, koef_1, koef_x, koef_2,
           dist_gola::jsonb     AS dg,
           tregjet::jsonb       AS tg,
           training_data::jsonb AS td,
           regexp_replace(rezultati_sakt, '\s','','g')             AS skor_pub,
           regexp_replace(rezultati,      '\s','','g')             AS skor_real,
           (regexp_match(rezultati_sakt,'(\d+)\D+(\d+)'))[1]::int  AS ph,
           (regexp_match(rezultati_sakt,'(\d+)\D+(\d+)'))[2]::int  AS pa,
           (regexp_match(rezultati,     '(\d+)\D+(\d+)'))[1]::int  AS gh,
           (regexp_match(rezultati,     '(\d+)\D+(\d+)'))[2]::int  AS ga
    FROM predictions
    WHERE dist_gola IS NOT NULL AND dist_gola::jsonb <> '{}'::jsonb
      AND training_data IS NOT NULL
      AND rezultati_sakt ~ '\d+\D+\d+'
      AND ( data::date >= current_date - 2                       -- 3 ditet e fundit
            OR statusi IS NULL
            OR statusi NOT IN ('FT','AET','PEN','AWD','WO',      -- + gjithcka ende e paluajtur
                               'CANC','PST','ABD') )
),
x AS (
    SELECT p.id, p.skor_real, p.skor_pub, e.k AS skori, e.v::numeric AS cnt,
           split_part(e.k,'-',1)::int + split_part(e.k,'-',2)::int AS tot_skori,
           row_number() OVER (PARTITION BY p.id ORDER BY e.v::numeric DESC) AS rendi
    FROM p, LATERAL jsonb_each_text(p.dg) AS e(k, v)
),
rk AS (
    SELECT id,
           min(skori) FILTER (WHERE rendi = 1)          AS argmax_skori,
           max(cnt)   FILTER (WHERE rendi = 1)          AS cnt_argmax,
           min(rendi) FILTER (WHERE skori = skor_pub)   AS rendi_pub,
           max(cnt)   FILTER (WHERE skori = skor_pub)   AS cnt_pub,
           min(rendi) FILTER (WHERE skori = skor_real)  AS rendi_real,
           max(cnt)   FILTER (WHERE skori = skor_real)  AS cnt_real,
           sum(cnt)   FILTER (WHERE rendi <= 5)         AS cnt_top5,
           sum(cnt)                                     AS cnt_gjithsej,
           -- masa e probabilitetit sipas TOTALIT (brezi i ngushte 2-3 kundrejt 4+)
           sum(cnt) FILTER (WHERE tot_skori <= 1)       AS c_t01,
           sum(cnt) FILTER (WHERE tot_skori  = 2)       AS c_t2,
           sum(cnt) FILTER (WHERE tot_skori  = 3)       AS c_t3,
           sum(cnt) FILTER (WHERE tot_skori >= 4)       AS c_t4,
           string_agg(skori || ' ' || round(100.0*cnt/50000.0,1) || '%',
                      ' | ' ORDER BY cnt DESC) FILTER (WHERE rendi <= 5) AS top5_jona
    FROM x GROUP BY id
),
c AS (
    SELECT p.*, rk.argmax_skori, rk.cnt_argmax, rk.rendi_pub, rk.cnt_pub,
           rk.rendi_real, rk.cnt_real, rk.cnt_top5, rk.cnt_gjithsej, rk.top5_jona,
           rk.c_t01, rk.c_t2, rk.c_t3, rk.c_t4,
           LEAST(5.00, GREATEST(0.10,  0.08 + 0.87 * (p.td->>'xg_1')::numeric)) AS xg1_norm,
           LEAST(5.00, GREATEST(0.10, -0.02 + 0.97 * (p.td->>'xg_2')::numeric)) AS xg2_norm,
           NULLIF( (p.td->>'p_market_1')::numeric
                 + (p.td->>'p_market_x')::numeric
                 + (p.td->>'p_market_2')::numeric, 0)                           AS sm
    FROM p JOIN rk ON rk.id = p.id
),
w AS (
    SELECT c.*,
           CASE WHEN sm IS NULL THEN (tg->>'1')::numeric
                ELSE ((tg->>'1')::numeric - 0.35*(td->>'p_market_1')::numeric/sm)/0.65 END AS p1_mc,
           CASE WHEN sm IS NULL THEN (tg->>'X')::numeric
                ELSE ((tg->>'X')::numeric - 0.35*(td->>'p_market_x')::numeric/sm)/0.65 END AS px_mc,
           CASE WHEN sm IS NULL THEN (tg->>'2')::numeric
                ELSE ((tg->>'2')::numeric - 0.35*(td->>'p_market_2')::numeric/sm)/0.65 END AS p2_mc
    FROM c
)
SELECT
  -- ═══ IDENTITETI ═══
  CASE WHEN (td ? 'elo_vlen') THEN 'I RI' ELSE 'i vjeter' END AS versioni,
  CASE WHEN statusi IN ('FT','AET','PEN','AWD','WO') THEN 'mbaroi'
       WHEN statusi IN ('CANC','PST','ABD')          THEN 'anulua'
       ELSE                                               'NS/live' END AS gjendja,
  data, ora_sakte AS ora, statusi, minuta, ndeshja, liga_emri AS liga,
  (td->>'tipi_ndeshjes')::int                       AS tipi_ndeshjes,

  -- ═══ 1. INPUTET E FORMES ═══
  (td->>'home_avg_scored')::numeric                 AS f_shenuar_1,
  (td->>'home_avg_conceded')::numeric               AS f_pesuar_1,
  (td->>'away_avg_scored')::numeric                 AS f_shenuar_2,
  (td->>'away_avg_conceded')::numeric               AS f_pesuar_2,
  (td->>'home_scored_home')::numeric                AS f_shenuar_1_shtepi,
  (td->>'home_conceded_home')::numeric              AS f_pesuar_1_shtepi,
  (td->>'away_scored_away')::numeric                AS f_shenuar_2_jashte,
  (td->>'away_conceded_away')::numeric              AS f_pesuar_2_jashte,
  (td->>'home_forma_pts')::numeric                  AS pike_forma_1,
  (td->>'away_forma_pts')::numeric                  AS pike_forma_2,
  (td->>'home_win_rate')::numeric                   AS wr_1,
  (td->>'away_win_rate')::numeric                   AS wr_2,
  (td->>'home_volatility')::numeric                 AS volat_1,
  (td->>'away_volatility')::numeric                 AS volat_2,
  (td->>'home_rest_days')::numeric                  AS pushim_1,
  (td->>'away_rest_days')::numeric                  AS pushim_2,
  (td->>'streak_1')::int  AS streak_1,  (td->>'streak_2')::int  AS streak_2,
  (td->>'kongjestion_1')::int AS kongj_1, (td->>'kongjestion_2')::int AS kongj_2,
  (td->>'lendime_1')::int AS lendime_1, (td->>'lendime_2')::int AS lendime_2,
  (td->>'pozicion_1')::int AS pozicion_1, (td->>'pozicion_2')::int AS pozicion_2,

  -- ═══ 2. ELO ═══
  (td->>'elo_1')::numeric AS elo_1, (td->>'elo_2')::numeric AS elo_2,
  (td->>'elo_vlen')::boolean AS elo_vlen, (td->>'is_derbi')::boolean AS is_derbi,

  -- ═══ 3. TREGU ═══
  koef_1, koef_x, koef_2,
  (td->>'p_market_1')::numeric AS pm_1,
  (td->>'p_market_x')::numeric AS pm_x,
  (td->>'p_market_2')::numeric AS pm_2,
  round(sm, 4)                 AS overround_1x2,
  (td->>'ou_over_odds')::numeric  AS ou_over,
  (td->>'ou_under_odds')::numeric AS ou_under,
  round( (1.0/NULLIF((td->>'ou_over_odds')::numeric,0))
       / NULLIF((1.0/NULLIF((td->>'ou_over_odds')::numeric,0))
              + (1.0/NULLIF((td->>'ou_under_odds')::numeric,0)),0), 4) AS p_over_tregu,
  (td->>'ah_line')::numeric AS ah_line,

  -- ═══ 4. xG PARA NORMALIZIMIT ═══
  round((td->>'xg_1')::numeric, 3) AS xg_1_para,
  round((td->>'xg_2')::numeric, 3) AS xg_2_para,
  round((td->>'xg_1')::numeric + (td->>'xg_2')::numeric, 3) AS total_para,
  td->>'burimi_xg' AS burimi_xg,

  -- ═══ 5. MODULUESIT ═══
  (td->>'modulator_1')::numeric AS modulator_1, (td->>'modulator_2')::numeric AS modulator_2,
  (td->>'clutch_1')::numeric AS clutch_1, (td->>'clutch_2')::numeric AS clutch_2,
  (td->>'desp_1')::numeric AS desp_1, (td->>'desp_2')::numeric AS desp_2,
  (td->>'draw_aff_1')::numeric AS draw_aff_1, (td->>'draw_aff_2')::numeric AS draw_aff_2,
  (td->>'vol_1')::numeric AS dna_vol_1, (td->>'vol_2')::numeric AS dna_vol_2,
  (td->>'kaos_liges')::numeric AS kaos_liges,
  (td->>'total_form')::numeric AS total_form,
  (td->>'total_target')::numeric AS total_target,

  -- ═══ 6. xG PAS NORMALIZIMIT — KJO SIMULOI ═══
  round(xg1_norm, 3) AS xg1_norm, round(xg2_norm, 3) AS xg2_norm,
  round(xg1_norm + xg2_norm, 3) AS total_pritur,
  round(xg1_norm - xg2_norm, 3) AS supremacia_norm,

  -- ═══ 7. PROBABILITETET ═══
  (tg->>'1')::numeric AS p1_blend, (tg->>'X')::numeric AS px_blend, (tg->>'2')::numeric AS p2_blend,
  round(p1_mc, 4) AS p1_mc, round(px_mc, 4) AS px_mc, round(p2_mc, 4) AS p2_mc,
  round(GREATEST(p1_mc, p2_mc) - px_mc, 4) AS hendeku_ndaj_x,
  CASE WHEN p1_mc >= p2_mc AND (p1_mc - px_mc) > 0.15 THEN 'vetem 1'
       WHEN p2_mc >  p1_mc AND (p2_mc - px_mc) > 0.15 THEN 'vetem 2'
       ELSE 'i lire' END AS winner_me_0_15,
  CASE WHEN p1_mc >= p2_mc AND (p1_mc - px_mc) > 0.10 THEN 'vetem 1'
       WHEN p2_mc >  p1_mc AND (p2_mc - px_mc) > 0.10 THEN 'vetem 2'
       ELSE 'i lire' END AS winner_me_0_10,

  -- ═══ 8. SHPERNDARJA SIPAS TOTALIT (brezi i ngushte kundrejt 4+) ═══
  round(100.0*c_t01/50000.0, 1) AS p_tot_0_1,
  round(100.0*c_t2 /50000.0, 1) AS p_tot_2,
  round(100.0*c_t3 /50000.0, 1) AS p_tot_3,
  round(100.0*c_t4 /50000.0, 1) AS p_tot_4plus,
  round(100.0*(c_t2+c_t3)/50000.0, 1) AS p_tot_2_ose_3,
  round(100.0*cnt_gjithsej/50000.0, 1) AS mbulimi_i_ruajtur_pct,

  -- ═══ 9. PERZGJEDHJA ═══
  argmax_skori AS argmax_yne,
  round(100.0*cnt_argmax/50000.0, 2) AS p_argmax_pct,
  rezultati_sakt AS publikuam,
  (ph + pa) AS tot_pub,
  COALESCE(rendi_pub, 99) AS rendi_i_publikuar,
  round(100.0*COALESCE(cnt_pub,0)/50000.0, 2) AS p_pub_pct,
  (skor_pub <> argmax_skori) AS shtresat_e_zhvendosen,
  (abs(xg1_norm - xg2_norm) >= 0.30) AS lean_i_mundshem,
  round(100.0*cnt_top5/50000.0, 1) AS mbulimi_top5_pct,
  top5_jona,

  -- ═══ 10. REZULTATI (bosh per NS) ═══
  rezultati AS ndodhi,
  CASE WHEN skor_real IS NULL THEN NULL ELSE (skor_pub = skor_real) END AS goditi,
  CASE WHEN skor_real IS NULL THEN NULL ELSE COALESCE(rendi_real, 99) END AS rendi_i_realit,
  CASE WHEN skor_real IS NULL THEN NULL
       ELSE round(100.0*COALESCE(cnt_real,0)/50000.0, 2) END AS p_real_pct,
  CASE WHEN gh IS NULL THEN NULL
       WHEN sign(ph-pa) = sign(gh-ga) THEN 1 ELSE 0 END AS drejtimi_ok,
  CASE WHEN gh IS NULL THEN NULL ELSE abs(ph-gh) + abs(pa-ga) END AS gabimi_gola,
  (gh + ga) AS totali_real,
  CASE WHEN gh IS NULL THEN NULL
       ELSE round((gh+ga) - (xg1_norm + xg2_norm), 2) END AS gabimi_totali,

  -- ═══ 11. PUBLIKIMI ═══
  besueshmeria, koef_rez_sakt, is_premium, is_value, is_bllof, id
FROM w
ORDER BY gjendja, data, ora_sakte, ndeshja;
