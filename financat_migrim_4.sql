-- ==========================================================================
-- FINANCAT — migrimi 4: bizneset (P&L, pika e barazimit, terheqjet)
-- ==========================================================================
-- Ekzekutohet NJE HERE ne SQL Editor te Supabase. I sigurt te ri-ekzekutohet.
--
-- Biznesi mbahet NJESI ME VETE, jo kategori shpenzimesh. Arsyeja eshte
-- praktike: me para te perziera nuk kuptohet dot nese biznesi ecen apo jo.
-- Ura e vetme mes biznesit dhe teje eshte TERHEQJA — dhe vetem ajo shfaqet
-- si e ardhur personale.
-- ==========================================================================

-- ── 1. BIZNESET ───────────────────────────────────────────────────────────
create table if not exists fin_bizneset (
    id              bigserial primary key,
    user_id         text        not null default 'une',
    emri            text        not null,
    pershkrimi      text,
    monedha         text        not null default 'EUR',
    data_fillimit   date,
    -- Sa terheq per vete cdo muaj nga ky biznes. Krahasohet me fitimin:
    -- nese e kalon, po ha kapitalin, dhe kjo duhet thene.
    terheqje_mujore numeric(16,2) not null default 0,
    -- Llogaria e biznesit, nese e mban te ndare (rekomandohet).
    llogaria_id     bigint      references fin_llogarite(id) on delete set null,
    -- Emri i njesise qe shet: abonent, klient, ora, produkt. Perdoret ne
    -- tekstin e pikes se barazimit qe te lexohet si shqip, jo si formule.
    njesia          text        not null default 'njesi',
    aktiv           boolean     not null default true,
    shenime         text,
    krijuar_me      timestamptz not null default now()
);
create index if not exists idx_fin_bizneset_user on fin_bizneset(user_id, aktiv);

-- ── 2. ZERAT E BIZNESIT ───────────────────────────────────────────────────
-- Nje tabele e vetme me tre role, sepse te tre hyjne ne te njejten llogari
-- fitimi dhe ndryshojne vetem nga menyra si llogariten.
create table if not exists fin_biznes_zerat (
    id              bigserial primary key,
    user_id         text        not null default 'une',
    biznesi_id      bigint      not null references fin_bizneset(id) on delete cascade,
    emri            text        not null,
    -- te_ardhur | kosto_fikse | kosto_variabile
    lloji           text        not null default 'kosto_fikse',
    monedha         text        not null default 'EUR',
    -- Shuma e sheshte (kosto fikse, ose e ardhur pa njesi).
    shuma           numeric(16,2) not null default 0,
    -- Te ardhura me njesi: cmimi x sasia (p.sh. 12 EUR x 47 abonente).
    cmimi_njesi     numeric(16,4) not null default 0,
    sasia           numeric(16,2) not null default 0,
    -- Kosto variabile: ose per njesi, ose si perqindje e te ardhurave
    -- (komisionet e pagesave jane tipike per te dyten).
    kosto_per_njesi numeric(16,4) not null default 0,
    perqindja       numeric(6,3)  not null default 0,
    -- mujore | vjetore  (gjithcka sillet ne muaj per krahasim)
    frekuenca       text        not null default 'mujore',
    kategoria       text        not null default 'tjeter',
    dita_pageses    int,
    aktiv           boolean     not null default true,
    shenime         text,
    krijuar_me      timestamptz not null default now()
);
create index if not exists idx_fin_biznes_zerat on fin_biznes_zerat(user_id, biznesi_id, lloji);

alter table fin_biznes_zerat
    add constraint fin_biznes_zerat_dita_check
    check (dita_pageses is null or (dita_pageses between 1 and 31)) not valid;

-- ── 3. Lidhja e transaksioneve me biznesin ────────────────────────────────
-- Nje shpenzim i biznesit nuk duhet te ndoti shpenzimet personale, dhe nje
-- e ardhur e biznesit nuk eshte e ardhur jotja derisa ta terheqesh.
alter table fin_transaksionet
    add column if not exists biznesi_id bigint;
create index if not exists idx_fin_trx_biznes
    on fin_transaksionet(user_id, biznesi_id, data desc);

-- ── 4. RLS — si gjithe tabelat e tjera fin_* ──────────────────────────────
alter table fin_bizneset     enable row level security;
alter table fin_biznes_zerat enable row level security;
