-- ========================================================================
-- ZINXHIRI I PLOTE per Instituto / Daejeon / Rayo Vallecano
-- Ekzekutoje VETEM kete skedar. Supabase kthen vetem rezultatin e
-- pyetjes se FUNDIT kur i jep disa njeheresh — prandaj jane te ndara.
-- ========================================================================

-- ── 3) ZINXHIRI I PLOTE PER TRI NDESHJET NE PYETJE ──────────────────────
-- Pse doli pikerisht ai skor: xG -> totali i pritur -> skori i zgjedhur.
SELECT
  p.data, p.ora, p.ndeshja, p.liga_emri,
  p.koef_1, p.koef_x, p.koef_2,
  -- tregu i devigosur
  round(((1/p.koef_1::numeric) / ((1/p.koef_1::numeric)+(1/p.koef_x::numeric)+(1/p.koef_2::numeric)))::numeric, 3) AS p1_treg,
  round(((1/p.koef_x::numeric) / ((1/p.koef_1::numeric)+(1/p.koef_x::numeric)+(1/p.koef_2::numeric)))::numeric, 3) AS px_treg,
  round(((1/p.koef_2::numeric) / ((1/p.koef_1::numeric)+(1/p.koef_x::numeric)+(1/p.koef_2::numeric)))::numeric, 3) AS p2_treg,
  -- xG-ja qe prodhoi skorin
  (p.training_data->>'xg_1')::numeric                                   AS xg_1,
  (p.training_data->>'xg_2')::numeric                                   AS xg_2,
  round(((p.training_data->>'xg_1')::numeric + (p.training_data->>'xg_2')::numeric), 2) AS totali_i_pritur,
  p.training_data->>'burimi_xg'                                         AS burimi_xg,
  -- 1X2 i modelit pas blendit me tregun
  p.training_data->'prob_1x2_mc'                                        AS prob_1x2_pas_blendit,
  -- outputi
  p.rezultati_sakt                                                      AS skori_yne,
  p.koef_rez_sakt                                                       AS koefi_i_skorit,
  p.rezultati                                                           AS reali,
  (split_part(p.rezultati_sakt,'-',1)::int + split_part(p.rezultati_sakt,'-',2)::int) AS totali_yne,
  p.besueshmeria
FROM parashikimet p
WHERE p.ndeshja ILIKE '%Rayo Vallecano%'
   OR p.ndeshja ILIKE '%Instituto%'
   OR p.ndeshja ILIKE '%Daejeon%'
ORDER BY p.data DESC, p.ora;
