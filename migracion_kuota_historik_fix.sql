-- ==========================================================
-- RREGULLIM: indeksi unik i kuota_historik
-- ==========================================================
-- Ekzekutoje VETËM nëse ke provuar tashmë migracion_kuota_historik.sql dhe
-- komanda e fundit dështoi me:
--     ERROR: 42P17: functions in index expression must be marked IMMUTABLE
--
-- Shkaku: date_trunc('minute', <timestamptz>) është STABLE, jo IMMUTABLE — sepse
-- rezultati varet nga parametri TimeZone i sesionit. Postgres nuk pranon funksione
-- jo-IMMUTABLE në shprehje indeksi.
--
-- Zgjidhja: minuta llogaritet në backend dhe dërgohet gati, ndaj indeksi bie mbi
-- një kolonë të thjeshtë dhe s'ka fare funksion brenda.
--
-- Tabela dhe dy indekset e para janë krijuar tashmë me sukses — kjo vetëm i shton
-- kolonën që mungon dhe krijon indeksin unik.
-- ==========================================================

ALTER TABLE kuota_historik
    ADD COLUMN IF NOT EXISTS marre_minute TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS idx_kuota_hist_unik
    ON kuota_historik (fixture_id, bookmaker, marre_minute);


-- ── VERIFIKIM ──
-- Duhet të kthejë 3 rreshta: idx_kuota_hist_fixture, idx_kuota_hist_koha,
-- idx_kuota_hist_unik.
--
-- SELECT indexname FROM pg_indexes WHERE tablename = 'kuota_historik';
