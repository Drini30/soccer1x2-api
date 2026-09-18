-- ==========================================================================
-- FINANCAT — migrimi 5: buxhetet mujore per kategori
-- ==========================================================================
-- Ekzekutohet NJE HERE ne SQL Editor te Supabase. I sigurt te ri-ekzekutohet.
--
-- Buxheti eshte gje tjeter nga plani: plani thote "qeraja eshte 30.000 dhe
-- paguhet me 5"; buxheti thote "ushqimeve u kam vene 35.000 ne muaj dhe deri
-- sot kam harxhuar 28.000". I pari eshte detyrim, i dyti eshte kufi qe e vendos
-- vete dhe qe mund ta kalosh — por duke e ditur.
-- ==========================================================================

create table if not exists fin_buxhetet (
    id              bigserial primary key,
    user_id         text        not null default 'une',
    kategoria       text        not null,
    shuma_mujore    numeric(16,2) not null,
    monedha         text        not null default 'EUR',
    -- Sa % e buxhetit te nxjerre paralajmerimin para se te kalohet fare.
    pragu_alarmit   int         not null default 85,
    aktiv           boolean     not null default true,
    shenime         text,
    krijuar_me      timestamptz not null default now()
);

-- Nje kategori, nje buxhet. Pa kete, dy rreshta per 'ushqime' do te jepnin dy
-- shirita qe kundershtojne njeri-tjetrin.
create unique index if not exists idx_fin_buxhetet_kategoria
    on fin_buxhetet(user_id, kategoria);

alter table fin_buxhetet
    add constraint fin_buxhetet_prag_check
    check (pragu_alarmit between 1 and 100) not valid;

alter table fin_buxhetet enable row level security;
