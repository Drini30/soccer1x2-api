-- ==========================================================================
-- ASISTENTI IM — migrimi 8: fondet e rezervuara dhe biseda me asistentin
-- ==========================================================================
-- Ekzekutohet NJE HERE ne SQL Editor te Supabase. I sigurt te ri-ekzekutohet.
--
-- Dy shtesa qe ndryshojne menyren si perdoret aplikacioni:
--
-- 1. FONDET E REZERVUARA. Nje bilanc bruto genjen: brenda tij ka para qe
--    tashme i ke premtuar diku — taksat, emergjenca, kesti i muajit tjeter.
--    Nje ekonomist nuk pyet "sa kam" por "sa kam TE LIRE". Rezervat e zene
--    ate pjese, dhe ajo zbritet kudo ku matet aftesia per te shpenzuar.
--
-- 2. BISEDA. Njoftimet vijne si mesazhe, dhe urdhrat jepen si mesazhe:
--    "shto si te paguar internetin", "shto rrogen te Kesh 95000 lek".
--    Cdo urdher ruhet me tekstin origjinal dhe me propozimin e kuptuar, qe
--    nje keqkuptim te jete gjithmone i gjurmueshem dhe i kthyeshem.
-- ==========================================================================

-- ── 1. FONDET E REZERVUARA ────────────────────────────────────────────────
create table if not exists fin_rezervat (
    id              bigserial primary key,
    user_id         text        not null default 'une',
    emri            text        not null,
    shuma           numeric(16,2) not null,
    monedha         text        not null default 'EUR',
    -- Rezerva mund te jete e nje llogarie te caktuar ose e pergjithshme.
    llogaria_id     bigint      references fin_llogarite(id) on delete set null,
    -- emergjence | taksa | objektiv | detyrim | tjeter
    lloji           text        not null default 'tjeter',
    -- Deri kur mbahet e zene; null = pa afat.
    afati           date,
    arsyeja         text,
    aktiv           boolean     not null default true,
    krijuar_me      timestamptz not null default now(),
    perditesuar_me  timestamptz
);
create index if not exists idx_fin_rezervat_user
    on fin_rezervat(user_id, aktiv);

-- ── 2. BISEDA ME ASISTENTIN ───────────────────────────────────────────────
create table if not exists fin_mesazhet (
    id              bigserial primary key,
    user_id         text        not null default 'une',
    kur             timestamptz not null default now(),
    -- 'une' = e shkrova une; 'asistenti' = e tha asistenti
    kush            text        not null default 'une',
    teksti          text        not null,
    -- urdher | pergjigje | njoftim | gabim
    lloji           text        not null default 'urdher',
    -- Cfare u kuptua nga urdhri: veprimi, shuma, burimi, llogaria…
    propozimi       jsonb       not null default '{}'::jsonb,
    -- i_ri | konfirmuar | anuluar | kryer | pa_kuptuar
    statusi         text        not null default 'i_ri',
    -- Rreshti i ditarit qe krijoi ky urdher, kur u krye.
    veprimi_id      bigint,
    krijuar_me      timestamptz not null default now(),
    perditesuar_me  timestamptz
);
create index if not exists idx_fin_mesazhet_user
    on fin_mesazhet(user_id, kur desc);
create index if not exists idx_fin_mesazhet_pritje
    on fin_mesazhet(user_id, statusi) where statusi = 'i_ri';

-- ── 3. VULA E PERDITESIMIT EDHE PER TABELAT E REJA ────────────────────────
-- fin_vulos_perditesimin() vjen nga migrimi 7; ketu vetem lidhet me dy
-- tabelat e reja, qe rregulli "cdo ndryshim mban oren" te mos kete perjashtim.
do $$
declare
    t text;
begin
    foreach t in array array['fin_rezervat', 'fin_mesazhet'] loop
        execute format('drop trigger if exists trg_%s_perditesuar on %I', t, t);
        execute format(
            'create trigger trg_%s_perditesuar before update on %I '
            'for each row execute function fin_vulos_perditesimin()', t, t);
    end loop;
end $$;

alter table fin_rezervat  enable row level security;
alter table fin_mesazhet  enable row level security;

-- ── 4. CILESIMET E ASISTENTIT ─────────────────────────────────────────────
insert into fin_cilesimet (celes, vlera) values
    -- Kur eshte true, nje urdher i kuptuar qarte kryhet pa klikuar "Konfirmo".
    -- Parazgjedhja eshte false me qellim: nje gabim shtypi nuk duhet te
    -- levize para pa te pare njeriu.
    ('konfirmim_automatik', 'false'::jsonb),
    -- Emri qe mban aplikacioni ne krye te faqes.
    ('emri_i_asistentit',  '"Asistenti im"'::jsonb)
on conflict (celes) do nothing;
