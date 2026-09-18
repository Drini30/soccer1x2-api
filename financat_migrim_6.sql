-- ==========================================================================
-- FINANCAT — migrimi 6: personat, dhe lidhja e cdo levizjeje me ta
-- ==========================================================================
-- Ekzekutohet NJE HERE ne SQL Editor te Supabase. I sigurt te ri-ekzekutohet.
--
-- Nje familje me dy paga nuk eshte nje xhep i vetem: duhet te dukret kush
-- sjell sa, kush shpenzon sa, dhe cilat llogari i perkasin kujt. Totali
-- mbetet nje, por tani ka edhe zberthimin.
-- ==========================================================================

create table if not exists fin_personat (
    id              bigserial primary key,
    user_id         text        not null default 'une',
    emri            text        not null,
    -- Ngjyra ndihmon ta dallosh menjehere ne liste; opsionale.
    ngjyra          text,
    shenime         text,
    aktiv           boolean     not null default true,
    krijuar_me      timestamptz not null default now()
);
create unique index if not exists idx_fin_personat_emri
    on fin_personat(user_id, emri);

-- Lidhja e personit me gjithcka qe levizet
alter table fin_llogarite
    add column if not exists personi_id bigint references fin_personat(id) on delete set null;
alter table fin_te_ardhurat
    add column if not exists personi_id bigint references fin_personat(id) on delete set null;
alter table fin_transaksionet
    add column if not exists personi_id bigint references fin_personat(id) on delete set null;
alter table fin_detyrimet
    add column if not exists personi_id bigint references fin_personat(id) on delete set null;

create index if not exists idx_fin_trx_personi
    on fin_transaksionet(user_id, personi_id, data desc);

alter table fin_personat enable row level security;
