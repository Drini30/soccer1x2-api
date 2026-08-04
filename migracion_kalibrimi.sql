-- ════════════════════════════════════════════════════════════════════════
-- MIGRACIONI PËR AUTO-KALIBRIMIN E MODELIT
-- Ekzekutoje NJË HERË në Supabase → SQL Editor.
-- I sigurt për t'u ri-ekzekutuar (IF NOT EXISTS kudo).
-- ════════════════════════════════════════════════════════════════════════

-- 1) Parametrat e modelit të lexuar në runtime nga _konf().
--    Pa këtë tabelë kodi punon njësoj (bie te env-var → default i koduar),
--    thjesht nuk ka auto-kalibrim.
CREATE TABLE IF NOT EXISTS model_config (
    celes        text PRIMARY KEY,
    vlera        double precision NOT NULL,
    mostra       integer,
    perditesuar  timestamptz DEFAULT now()
);

-- Vetëm service-role duhet ta shkruajë; askush publik s'duhet ta lexojë.
ALTER TABLE model_config ENABLE ROW LEVEL SECURITY;

-- 2) Nota e gjysmës së parë. parashikimi_ht ruhej prej kohësh por s'notohej kurrë.
ALTER TABLE arkiv_rezultatesh ADD COLUMN IF NOT EXISTS goditi_ht boolean;

-- ────────────────────────────────────────────────────────────────────────
-- KONTROLLI PAS EKZEKUTIMIT
-- ────────────────────────────────────────────────────────────────────────
-- Prova e thatë (nuk shkruan asgjë) — pritet A_HOME≈0.08, B_HOME≈0.87,
--                                              A_AWAY≈-0.02, B_AWAY≈0.97:
--   GET /api/admin/kalibro?secret=<B2B_ADMIN_SECRET>&dry=1
--
-- Shkrimi real:
--   GET /api/admin/kalibro?secret=<B2B_ADMIN_SECRET>&dry=0
--
-- Konfirmimi se motori i mori (brenda 1 ore, ose menjehere pas shkrimit):
--   GET /api/status   →  konfigurimi.*  dhe  kalibrimi.celesa_aktive
--
-- Kthimi mbrapsht i çdo parametri (motori bie te default-i i koduar):
--   DELETE FROM model_config WHERE celes = 'XG_NORM_B_HOME';
-- Kthimi i plotë:
--   TRUNCATE model_config;
