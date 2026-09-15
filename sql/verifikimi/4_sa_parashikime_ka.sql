-- ========================================================================
-- SA PARASHIKIME KA per 14-16 shtator
-- Ekzekutoje VETEM kete skedar. Supabase kthen vetem rezultatin e
-- pyetjes se FUNDIT kur i jep disa njeheresh — prandaj jane te ndara.
-- ========================================================================

-- ── 4) A KA FARE PARASHIKIME PER 16 SHTATORIN ───────────────────────────
SELECT
  data,
  count(*)                                              AS gjithsej,
  count(*) FILTER (WHERE rezultati_sakt IS NOT NULL)    AS me_skor,
  count(*) FILTER (WHERE tregjet IS NOT NULL)           AS me_tregje,
  count(*) FILTER (WHERE is_premium)                    AS premium,
  min(ora) AS e_para, max(ora) AS e_fundit
FROM predictions
WHERE data IN ('2026-09-14', '2026-09-15', '2026-09-16')
GROUP BY data
ORDER BY data;
