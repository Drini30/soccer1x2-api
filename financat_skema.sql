-- ==========================================================================
-- FINANCAT — skema e modulit personal te kontrollit financiar (Supabase)
-- ==========================================================================
-- Ekzekutohet nje here ne SQL Editor te Supabase.
-- Te gjitha tabelat kane prefiksin fin_ qe te mos perzihen me tabelat e
-- SOCCER1X2 (predictions, users, training_results, ...).
--
-- Modeli eshte NJE-PERDORUES: kolona user_id ekziston qe tani (default
-- 'une') qe kalimi ne shume perdorues me vone te mos kerkoje migrim te
-- dhenash — mjafton te mbushet dhe te ndizet RLS.
--
-- Shumat ruhen ne monedhen e rreshtit (kolona monedha); konvertimi ne
-- monedhen baze behet ne Python nga kurset te fin_cilesimet.
-- ==========================================================================

-- ── 1. LLOGARITE (ku rri paraja) ──────────────────────────────────────────
create table if not exists fin_llogarite (
    id              bigserial primary key,
    user_id         text        not null default 'une',
    emri            text        not null,
    -- cash | bank | kursim | kartekredit | investim | tjeter
    lloji           text        not null default 'bank',
    monedha         text        not null default 'EUR',
    bilanci_fillestar numeric(16,2) not null default 0,
    -- per kartat e kreditit: limiti (pozitiv). 0 = pa limit.
    limiti          numeric(16,2) not null default 0,
    -- a numerohet si likuiditet i menjehershem (per runway-in)
    likuide         boolean     not null default true,
    aktiv           boolean     not null default true,
    shenime         text,
    krijuar_me      timestamptz not null default now()
);
create index if not exists idx_fin_llogarite_user on fin_llogarite(user_id, aktiv);

-- ── 2. TRANSAKSIONET (levizjet reale te parase) ───────────────────────────
create table if not exists fin_transaksionet (
    id              bigserial primary key,
    user_id         text        not null default 'une',
    data            date        not null default current_date,
    llogaria_id     bigint      references fin_llogarite(id) on delete set null,
    -- hyrje | dalje | transfer
    lloji           text        not null default 'dalje',
    -- shuma gjithmone POZITIVE; drejtimin e jep 'lloji'
    shuma           numeric(16,2) not null,
    monedha         text        not null default 'EUR',
    kategoria       text        not null default 'tjeter',
    pershkrimi      text,
    -- lidhje opsionale me nje detyrim ose plan (kesti i paguar)
    detyrimi_id     bigint,
    plani_id        bigint,
    -- per transfer: llogaria ku shkon paraja
    llogaria_dest_id bigint     references fin_llogarite(id) on delete set null,
    etiketa         text[]      not null default '{}',
    krijuar_me      timestamptz not null default now()
);
create index if not exists idx_fin_trx_user_data on fin_transaksionet(user_id, data desc);
create index if not exists idx_fin_trx_llogaria  on fin_transaksionet(llogaria_id);

-- ── 3. DETYRIMET (borxhe qe kam + arketime qe pres) ───────────────────────
create table if not exists fin_detyrimet (
    id              bigserial primary key,
    user_id         text        not null default 'une',
    -- borxh   = un e detyrohem dikujt (kredi, kesti, para te marra hua)
    -- arketim = dikush m detyrohet mua (pagese qe pritet te merret)
    lloji           text        not null default 'borxh',
    pala            text        not null,              -- kush: banka, shoku, klienti
    pershkrimi      text,
    shuma_totale    numeric(16,2) not null,
    shuma_paguar    numeric(16,2) not null default 0,
    monedha         text        not null default 'EUR',
    interesi_vjetor numeric(6,3)  not null default 0,   -- ne perqindje, p.sh. 7.500
    kesti_mujor     numeric(16,2) not null default 0,   -- 0 = pa keste fikse
    afati           date,                               -- data e fundit e shlyerjes
    -- 1 = jetike (qira, kredi banke) … 5 = e shtyshme pa pasoje
    prioriteti      int         not null default 3,
    -- aktiv | shlyer | vonuar | dyshimtar (per arketimet: sa besohet)
    statusi         text        not null default 'aktiv',
    -- sa % e ketij arketimi e konsideron te sigurt (0-100). Per borxhet: 100.
    siguria         int         not null default 100,
    krijuar_me      timestamptz not null default now()
);
create index if not exists idx_fin_detyrimet_user on fin_detyrimet(user_id, statusi, afati);

-- ── 4. PLANET (shpenzime/te ardhura te pritshme, te perseritshme ose jo) ──
create table if not exists fin_planet (
    id              bigserial primary key,
    user_id         text        not null default 'une',
    emri            text        not null,
    -- dalje | hyrje
    drejtimi        text        not null default 'dalje',
    shuma           numeric(16,2) not null,
    monedha         text        not null default 'EUR',
    kategoria       text        not null default 'tjeter',
    -- nje_here | javore | dyjavore | mujore | tremujore | vjetore
    frekuenca       text        not null default 'mujore',
    data_fillimit   date        not null default current_date,
    data_mbarimit   date,
    -- urgjent (<1 muaj) | afatshkurter (1-6 muaj) | afatmesem (6-24 muaj) | afatgjate (24m+)
    horizonti       text        not null default 'afatshkurter',
    -- 1 = e domosdoshme (buke, qira) … 5 = luks i pastr
    domosdoshmeria  int         not null default 3,
    -- sa % gjasa ka te ndodhe vertet (per gjerat e paparashikuara)
    probabiliteti   int         not null default 100,
    aktiv           boolean     not null default true,
    shenime         text,
    krijuar_me      timestamptz not null default now()
);
create index if not exists idx_fin_planet_user on fin_planet(user_id, aktiv, horizonti);

-- ── 5. TE ARDHURAT (burimet e rregullta) ──────────────────────────────────
create table if not exists fin_te_ardhurat (
    id              bigserial primary key,
    user_id         text        not null default 'une',
    emri            text        not null,
    -- page | freelance | qira | biznes | dividend | tjeter
    lloji           text        not null default 'page',
    shuma_mujore    numeric(16,2) not null,
    monedha         text        not null default 'EUR',
    -- 1 = e pasigurt … 5 = e garantuar
    siguria         int         not null default 4,
    -- sa ore ne muaj te kushton (per te matur te ardhurat pasive)
    oret_mujore     numeric(8,1) not null default 0,
    aktiv           boolean     not null default true,
    krijuar_me      timestamptz not null default now()
);

-- ── 6. INVESTIMET ─────────────────────────────────────────────────────────
create table if not exists fin_investimet (
    id              bigserial primary key,
    user_id         text        not null default 'une',
    emri            text        not null,
    -- aksion | etf | krypto | prone | biznes | depozite | obligacion | tjeter
    lloji           text        not null default 'etf',
    simboli         text,                                -- p.sh. VWCE.DE, BTC
    sasia           numeric(20,8) not null default 0,
    cmimi_blerje    numeric(20,8) not null default 0,
    cmimi_aktual    numeric(20,8) not null default 0,
    monedha         text        not null default 'EUR',
    data_blerje     date,
    -- 1 = shume i sigurt … 5 = spekulativ
    rreziku         int         not null default 3,
    -- kthimi vjetor i pritshem ne % (vleresim yti ose i skanuar)
    kthimi_pritshem numeric(6,2) not null default 0,
    aktiv           boolean     not null default true,
    shenime         text,
    perditesuar_me  timestamptz not null default now(),
    krijuar_me      timestamptz not null default now()
);

-- ── 7. OBJEKTIVAT (ku dua te arrij) ───────────────────────────────────────
create table if not exists fin_objektivat (
    id              bigserial primary key,
    user_id         text        not null default 'une',
    emri            text        not null,
    shuma_synim     numeric(16,2) not null,
    shuma_aktuale   numeric(16,2) not null default 0,
    monedha         text        not null default 'EUR',
    afati           date,
    prioriteti      int         not null default 3,
    -- rezerve | blerje | investim | shlyerje_borxhi | te_ardhura | tjeter
    lloji           text        not null default 'tjeter',
    arritur         boolean     not null default false,
    krijuar_me      timestamptz not null default now()
);

-- ── 8. RAPORTET (analizat e ruajtura te keshilltarit me Claude) ───────────
create table if not exists fin_raportet (
    id              bigserial primary key,
    user_id         text        not null default 'une',
    -- keshilltar | skanim_opsionesh | rishikim_mujor
    lloji           text        not null default 'keshilltar',
    pyetja          text,
    gjendja         jsonb,          -- fotografia e gjendjes qe iu dergua modelit
    pergjigja       text,
    burimet         jsonb not null default '[]'::jsonb,   -- linqet nga web search
    modeli          text,
    tokena          jsonb,
    krijuar_me      timestamptz not null default now()
);
create index if not exists idx_fin_raportet_user on fin_raportet(user_id, krijuar_me desc);

-- ── 9. CILESIMET (monedha baze, kurset, pragjet) ──────────────────────────
create table if not exists fin_cilesimet (
    celes           text primary key,
    vlera           jsonb not null,
    perditesuar_me  timestamptz not null default now()
);

insert into fin_cilesimet (celes, vlera) values
    ('monedha_baze',      '"EUR"'::jsonb),
    -- sa njesi te monedhes baze ben 1 njesi e monedhes se dhene
    ('kurset',            '{"EUR":1,"ALL":0.0102,"USD":0.92,"GBP":1.17,"CHF":1.05}'::jsonb),
    -- sa muaj shpenzime duhet te mbaje rezerva e emergjences
    ('rezerva_muaj',      '3'::jsonb),
    -- norma e synuar e kursimit (% e te ardhurave)
    ('synimi_kursimit',   '20'::jsonb),
    -- sa dite perpara te sinjalizohet nje afat
    ('paralajmerim_dite', '14'::jsonb)
on conflict (celes) do nothing;

-- ── 10. RLS — mbyllur per anon; moduli shkruan vetem me service key ───────
alter table fin_llogarite     enable row level security;
alter table fin_transaksionet enable row level security;
alter table fin_detyrimet     enable row level security;
alter table fin_planet        enable row level security;
alter table fin_te_ardhurat   enable row level security;
alter table fin_investimet    enable row level security;
alter table fin_objektivat    enable row level security;
alter table fin_raportet      enable row level security;
alter table fin_cilesimet     enable row level security;
-- Pa asnje policy: celesi anon nuk lexon dot asgje. Service key e anashkalon
-- RLS-ne, dhe vetem backend-i e mban ate celes.
