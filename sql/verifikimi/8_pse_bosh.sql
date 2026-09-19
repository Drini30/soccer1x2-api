-- ========================================================================
-- PSE DOLI BOSH — diagnostike per analizen e filtrit
-- ========================================================================
-- Kur analiza kthen 0 ndeshje, fajin e ka njeri nga kushtet e saj. Kjo pyetje
-- i mat ato NJE NGA NJE, ne vend qe t'i hamendesojme.
--
--   A  sa rreshta mbeten pas secilit kusht, per daten e kerkuar
--   B  cilat data ekzistojne vertet ne baze (ne rast se data s'perputhet)
--   C  nje mostra e rreshtave te asaj dite, ashtu si jane
--
-- Ekzekutoje VETEM kete skedar.
-- ========================================================================

WITH parametrat AS (
  -- ▼▼ NDRYSHO VETEM KETU ▼▼
  SELECT DATE '2026-09-19' AS dita
),
d AS (
  SELECT p.* FROM predictions p, parametrat par WHERE p.data::date = par.dita
),
a AS (
  SELECT 'A · FILTRAT'::text AS seksioni, 1 AS rendi,
         '1) rreshta gjithsej ate dite'::text AS cfare,
         count(*)::text AS vlera FROM d
  UNION ALL SELECT 'A · FILTRAT', 2, '2) me best_bet jo bosh',
         count(*) FILTER (WHERE best_bet IS NOT NULL)::text FROM d
  UNION ALL SELECT 'A · FILTRAT', 3, '3) me best_bet->>tregu jo bosh',
         count(*) FILTER (WHERE best_bet->>'tregu' IS NOT NULL)::text FROM d
  UNION ALL SELECT 'A · FILTRAT', 4, '4) me rezultat te shenuar',
         count(*) FILTER (WHERE rezultati IS NOT NULL AND rezultati <> '')::text FROM d
  UNION ALL SELECT 'A · FILTRAT', 5, '5) rezultat ne formen 2-1  ← kushti i fundit',
         count(*) FILTER (WHERE rezultati ~ '^[0-9]+-[0-9]+$')::text FROM d
  UNION ALL SELECT 'A · FILTRAT', 6, '6) te gjitha kushtet bashke',
         count(*) FILTER (WHERE best_bet IS NOT NULL
                            AND best_bet->>'tregu' IS NOT NULL
                            AND rezultati ~ '^[0-9]+-[0-9]+$')::text FROM d
),
b AS (
  SELECT 'B · DATAT NE BAZE'::text, 10,
         'data ' || p.data::date::text,
         count(*)::text || ' ndeshje, ' ||
         count(*) FILTER (WHERE p.rezultati ~ '^[0-9]+-[0-9]+$')::text || ' me rezultat'
  FROM predictions p
  WHERE p.data::date >= (SELECT dita FROM parametrat) - 6
    AND p.data::date <= (SELECT dita FROM parametrat) + 1
  GROUP BY p.data::date
),
c AS (
  SELECT 'C · MOSTRA E DITES'::text, 20,
         COALESCE(ora, '--') || '  ' || COALESCE(ndeshja, '(pa emer)'),
         'rezultati=[' || COALESCE(rezultati, 'NULL') || ']'
         || '  statusi=[' || COALESCE(statusi, 'NULL') || ']'
         || '  tregu=[' || COALESCE(best_bet->>'tregu', 'NULL') || ']'
         || '  rez_sakt=[' || COALESCE(rezultati_sakt, 'NULL') || ']'
  FROM d
  ORDER BY ora
  LIMIT 12
)
SELECT seksioni, cfare, vlera
FROM (SELECT * FROM a UNION ALL SELECT * FROM b UNION ALL SELECT * FROM c) x
ORDER BY rendi, cfare;

-- LEXIMI:
--   • Nese rreshti 1 eshte 0 → data nuk perputhet. Shih seksionin B: aty jane
--     datat qe ekzistojne vertet. Mund te jete date tjeter, ose kolona 'data'
--     mban kohe/zone tjeter.
--   • Nese 1 eshte > 0 por 4 eshte 0 → ndeshjet jane aty, por REZULTATET nuk
--     jane shkruar ende ne kolonen 'rezultati'. Ekzekuto rifreskimin e
--     rezultateve dhe provoje perseri; analiza nuk gjykon dot pa to.
--   • Nese 4 > 0 por 5 eshte 0 → rezultati ruhet ne forme tjeter nga '2-1'.
--     Shih seksionin C se si duket vertet, dhe me thuaj.
--   • Nese 2 eshte 0 → ato ndeshje s'kane best_bet fare (nuk jane gjeneruar
--     me kete rruge), ndaj s'ka filtro per te analizuar.
