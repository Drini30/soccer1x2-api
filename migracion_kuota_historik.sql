-- ==========================================================
-- FAZA 1: HISTORIKU I KUOTAVE (mbledhje, pa njoftime)
-- ==========================================================
-- Ekzekuto NJË HERË te Supabase → SQL Editor.
--
-- PSE URGJENT: lëvizja e kuotave është i vetmi sinjal që NUK mbushet dot
-- prapaveprimisht. Goditjet, moti, formacionet — të gjitha nxirren nga historiku
-- kur të duash. Historiku i çmimeve jo: nëse s'e ruan sot, ka humbur përgjithmonë.
-- Prandaj kjo fazë mbledh dhe asgjë tjetër. Matja vjen pas 4-8 javësh.
--
-- ÇFARË MATET MË VONË: a e parashikon lëvizja e linjës rezultatin? Konkretisht,
-- kur kuota lëviz ndjeshëm drejt njërës anë mes T-6h dhe mbylljes, a del ajo anë
-- më shpesh nga sa thotë vetë kuota përfundimtare? Kjo është e falsifikueshme.
-- ==========================================================

CREATE TABLE IF NOT EXISTS kuota_historik (
    id              BIGSERIAL PRIMARY KEY,
    fixture_id      BIGINT      NOT NULL,
    marre_ne        TIMESTAMPTZ NOT NULL DEFAULT now(),
    koha_ndeshjes   TIMESTAMPTZ,
    -- Minuta deri në fillim. Kjo është boshti i vërtetë i analizës: krahasimi
    -- bëhet gjithmonë "T-360 kundrejt T-30", jo sipas orës së murit.
    minuta_para     INTEGER,
    -- `marre_ne` i rrumbullakosur te minuta, i dërguar GATI nga backend-i.
    -- Nuk përdoret date_trunc() në indeks: mbi timestamptz ajo është STABLE (varet
    -- nga TimeZone i sesionit), dhe Postgres kërkon IMMUTABLE në shprehje indeksi.
    marre_minute    TIMESTAMPTZ,
    bookmaker       SMALLINT,
    liga_emri       TEXT,
    ndeshja         TEXT,

    k1              NUMERIC,
    kx              NUMERIC,
    k2              NUMERIC,
    ou25_over       NUMERIC,
    ou25_under      NUMERIC,
    gg              NUMERIC,
    ng              NUMERIC,
    ah_line         NUMERIC,
    ah_home         NUMERIC,
    ah_away         NUMERIC
);

-- Pyetja mbizotëruese është "gjithë fotografitë e një ndeshjeje, sipas kohës".
CREATE INDEX IF NOT EXISTS idx_kuota_hist_fixture
    ON kuota_historik (fixture_id, marre_ne);

-- Për pastrim periodik dhe për zgjedhjen e dritares së matjes.
CREATE INDEX IF NOT EXISTS idx_kuota_hist_koha
    ON kuota_historik (koha_ndeshjes);

-- Mbrojtje nga fotografitë e dyfishta kur cron-i ekzekutohet dy herë brenda të
-- njëjtit minutë (p.sh. ri-provë pas timeout-i). Kolonë e thjeshtë, pa funksion —
-- ndaj indeksi është i vlefshëm. Nevojitet edhe që `Prefer: resolution=
-- ignore-duplicates` te backend-i të ketë efekt: pa kufizim unik ai s'bën asgjë.
CREATE UNIQUE INDEX IF NOT EXISTS idx_kuota_hist_unik
    ON kuota_historik (fixture_id, bookmaker, marre_minute);


-- ── PASTRIM (opsional, ekzekutoje herë pas here) ──
-- Fotografitë e ndeshjeve që kanë kaluar prej mbi 90 ditësh s'kanë më vlerë
-- analitike përveç asaj përmbledhëse. Hiqi që tabela të mos rritet pa kufi.
--
-- DELETE FROM kuota_historik WHERE koha_ndeshjes < now() - interval '90 days';


-- ── VERIFIKIM ──
-- Pas ekzekutimit të parë të /api/cron/kuotat, kjo duhet të kthejë rreshta:
--
-- SELECT count(*) AS fotografi,
--        count(DISTINCT fixture_id) AS ndeshje,
--        min(minuta_para) AS min_para,
--        max(minuta_para) AS max_para
-- FROM kuota_historik;
--
-- Dhe kjo tregon lëvizjen për një ndeshje:
--
-- SELECT minuta_para, k1, kx, k2, ou25_over
-- FROM kuota_historik WHERE fixture_id = <ID> ORDER BY marre_ne;
