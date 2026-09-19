-- ========================================================================
-- 1) KUSH I GJENEROI — vula e versionit per cdo dite
-- Ekzekutoje VETEM kete skedar.
-- ========================================================================
-- `training_data.build` u shtua me 15/09. Ndeshjet e gjeneruara para saj e kane
-- bosh. Kjo eshte pyetja e PARE sepse pa te, cdo gjykim mbi filtrin eshte i verber:
-- nuk dime nese po masim kodin e ri apo ate te vjetrin.
--
-- LEXIMI:
--   2026-09-16-maja-e-vertete / -historiku-i-plote  -> filtri i RREGULLUAR
--   2026-09-15-vula ose me e vjeter                 -> filtri i VJETER (me defekt)
--   (pa vule)                                       -> para 15 shtatorit

SELECT
  data,
  COALESCE(NULLIF(training_data->>'build', ''), '(pa vule)') AS build,
  count(*)                                   AS ndeshje,
  count(*) FILTER (WHERE is_premium)         AS premium,
  count(*) FILTER (WHERE statusi IN ('FT','AET','PEN','AWD','WO')) AS mbaruar,
  min(ora) AS e_para,
  max(ora) AS e_fundit
FROM predictions
WHERE data IN ('2026-09-16', '2026-09-17')
GROUP BY data, COALESCE(NULLIF(training_data->>'build', ''), '(pa vule)')
ORDER BY data, build;
