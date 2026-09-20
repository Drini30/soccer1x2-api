-- ========================================================================
-- 1) A KA NJOHURI MODELI YNE TE PJESA E PARE? — matja e pare ndonjehere
-- Ekzekutoje VETEM kete skedar.
-- ========================================================================
-- Pjesa e pare simulohet E PAVARUR, 40,000 here, dhe skori i saj ruhet prej
-- muajsh. Por nuk e kemi matur kurre. Kjo pyetje e mat.
--
-- PSE MUND TE JETE ME E MIRE SE FT:
--   • λ e gjysmes se pare eshte ~44% e asaj te ndeshjes -> shperndarje shume me
--     e perqendruar -> moda mban shume me shume probabilitet
--   • HT/FT ka vetem 9 rezultate te mundshme, jo 20+
--
-- BAZAT PER KRAHASIM (pa to numrat s'kane kuptim):
--   skori HT   : skori me i shpeshte HT eshte 0-0, rreth 30% e ndeshjeve
--   HT/FT      : hamendje e verber = 11.1% (1 nga 9); qelia me e shpeshte "1/1" ~20%

WITH b AS (
  SELECT
    to_char(data::date,'YYYY-MM')                        AS muaji,
    replace(rezultati_ht,' ','')                         AS ht_real,
    replace(parashikimi_ht,' ','')                       AS ht_yne,
    goditi_ht,
    replace(rezultati_ft,' ','')                         AS ft_real,
    parashikimi                                          AS ft_yne,
    tregjet_full->'ht_ft'                                AS htft,
    (tregjet_full->>'skor_ht')                           AS skor_ht
  FROM arkiv_rezultatesh
  WHERE rezultati_ht IS NOT NULL
    AND replace(rezultati_ht,' ','') ~ '^[0-9]+-[0-9]+$'
    AND replace(rezultati_ft,' ','') ~ '^[0-9]+-[0-9]+$'
),
z AS (
  SELECT b.*,
    -- shenjat reale
    CASE WHEN split_part(ht_real,'-',1)::int > split_part(ht_real,'-',2)::int THEN '1'
         WHEN split_part(ht_real,'-',1)::int < split_part(ht_real,'-',2)::int THEN '2'
         ELSE 'X' END                                    AS sht,
    CASE WHEN split_part(ft_real,'-',1)::int > split_part(ft_real,'-',2)::int THEN '1'
         WHEN split_part(ft_real,'-',1)::int < split_part(ft_real,'-',2)::int THEN '2'
         ELSE 'X' END                                    AS sft,
    -- qelia HT/FT qe i japim probabilitetin me te larte
    (SELECT e.k FROM jsonb_each_text(b.htft) AS e(k,v)
      WHERE e.k LIKE '%/%' ORDER BY e.v::numeric DESC LIMIT 1) AS qelia_jone,
    (SELECT max(e.v::numeric) FROM jsonb_each_text(b.htft) AS e(k,v)
      WHERE e.k LIKE '%/%')                              AS prob_qelise
  FROM b WHERE b.htft IS NOT NULL
)
SELECT
  muaji,
  count(*)                                                        AS ndeshje,
  -- SKORI I SAKTE I GJYSMES SE PARE
  count(*) FILTER (WHERE goditi_ht)                               AS ht_skor_ok,
  round(100.0*count(*) FILTER (WHERE goditi_ht)/count(*),1)       AS ht_skor_pct,
  -- per krahasim, skori FT
  count(*) FILTER (WHERE ft_yne = ft_real)                        AS ft_skor_ok,
  round(100.0*count(*) FILTER (WHERE ft_yne = ft_real)/count(*),1) AS ft_skor_pct,
  -- HT/FT me 9 qeliza
  count(*) FILTER (WHERE qelia_jone = sht || '/' || sft)          AS htft_ok,
  round(100.0*count(*) FILTER (WHERE qelia_jone = sht||'/'||sft)/count(*),1) AS htft_pct,
  round(100.0*avg(prob_qelise),1)                                 AS htft_premtuar,
  -- baza: sa shpesh del qelia me e shpeshte ne realitet
  round(100.0*count(*) FILTER (WHERE sht||'/'||sft = '1/1')/count(*),1) AS baza_1_1,
  round(100.0*count(*) FILTER (WHERE sht = 'X')/count(*),1)       AS ht_barazim_pct,
  round(100.0*count(*) FILTER (WHERE ht_real='0-0')/count(*),1)   AS ht_0_0_pct
FROM z
GROUP BY muaji
ORDER BY muaji;
