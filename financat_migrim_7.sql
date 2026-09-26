-- ==========================================================================
-- FINANCAT — migrimi 7: data DHE ora per cdo levizje, dhe ditari i veprimeve
-- ==========================================================================
-- Ekzekutohet NJE HERE ne SQL Editor te Supabase. I sigurt te ri-ekzekutohet.
--
-- Deri tani nje transaksion mbante vetem daten. Nje date pa ore nuk te thote
-- dot cila pagese erdhi e para kur ke dy ne te njejten dite, dhe nuk te lejon
-- ta gjesh nje levizje duke kujtuar "e bera pasdite". Tani cdo levizje mban
-- momentin e sakte (kryer_me), cdo rresht mban kur u ndryshua per here te
-- fundit (perditesuar_me), dhe cdo veprim ne aplikacion lihet ne nje ditar
-- te vetin (fin_veprimet) me daten dhe oren.
--
-- Ora ruhet si timestamptz — pra me zonen brenda. Shfaqja behet ne zonen
-- e vendosur te cilesimet ('zona_kohore', parazgjedhur Europe/Tirane), qe
-- nje pagese e bere ne oren 00:30 te mos dale dje.
-- ==========================================================================

-- ── 1. MOMENTI I SAKTE I CDO LEVIZJEJE ────────────────────────────────────
alter table fin_transaksionet
    add column if not exists kryer_me timestamptz;

-- Mbushja e historikut: per rreshtat e vjeter ora e vetme qe dihet vertet
-- eshte ajo e shkrimit. Kur shkrimi ka ndodhur po ate dite, ajo eshte edhe
-- ora e levizjes; kur jo (nje pagese e shenuar me vone), data mbetet e shenjte
-- dhe ora vihet 12:00 — nje shenje e qarte "ora e vertete nuk njihet".
update fin_transaksionet
   set kryer_me = case
         when (krijuar_me at time zone 'Europe/Tirane')::date = data
              then krijuar_me
         else (data + time '12:00') at time zone 'Europe/Tirane'
       end
 where kryer_me is null;

alter table fin_transaksionet
    alter column kryer_me set default now();
alter table fin_transaksionet
    alter column kryer_me set not null;

create index if not exists idx_fin_trx_kryer
    on fin_transaksionet(user_id, kryer_me desc);

-- 'data' dhe 'kryer_me' nuk guxojne te ndahen nga njera-tjetra: e para eshte
-- baza e cdo grupimi mujor, e dyta e renditjes brenda dites. Trigeri i mban
-- te lidhura pavaresisht se cilen prek shkrimi.
create or replace function fin_vulos_kohen() returns trigger as $$
declare
    zona text := coalesce(current_setting('fin.zona', true), 'Europe/Tirane');
begin
    if tg_op = 'INSERT' then
        if new.kryer_me is null then
            -- Date pa ore: ora e momentit qe po shkruhet, mbi daten e zgjedhur.
            new.kryer_me := (new.data + (now() at time zone zona)::time)
                            at time zone zona;
        else
            new.data := (new.kryer_me at time zone zona)::date;
        end if;
        return new;
    end if;

    if new.kryer_me is distinct from old.kryer_me then
        new.data := (new.kryer_me at time zone zona)::date;
    elsif new.data is distinct from old.data then
        -- Ndryshoi vetem data → ora e mbajtur deri tani e ndjek ate.
        new.kryer_me := (new.data + (old.kryer_me at time zone zona)::time)
                        at time zone zona;
    end if;
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_fin_trx_koha on fin_transaksionet;
create trigger trg_fin_trx_koha
    before insert or update on fin_transaksionet
    for each row execute function fin_vulos_kohen();

-- ── 2. KUR U PREK PER HERE TE FUNDIT CDO RRESHT ───────────────────────────
-- Nje fushe qe mbushet nga kodi harrohet nje dite; nje fushe qe e mbush baza
-- nuk harrohet kurre.
create or replace function fin_vulos_perditesimin() returns trigger as $$
begin
    new.perditesuar_me := now();
    return new;
end;
$$ language plpgsql;

do $$
declare
    t text;
begin
    foreach t in array array[
        'fin_llogarite', 'fin_transaksionet', 'fin_detyrimet', 'fin_planet',
        'fin_te_ardhurat', 'fin_investimet', 'fin_objektivat', 'fin_raportet',
        'fin_bizneset', 'fin_biznes_zerat', 'fin_buxhetet', 'fin_personat',
        'fin_cilesimet'
    ] loop
        -- Migrimet 4-6 mund te mos jene ekzekutuar ende; ato qe mungojne thjesht
        -- kapercehen, dhe ky migrim mund te ri-ekzekutohet pas tyre.
        if to_regclass(t) is null then
            continue;
        end if;
        execute format(
            'alter table %I add column if not exists perditesuar_me timestamptz', t);
        execute format('drop trigger if exists trg_%s_perditesuar on %I', t, t);
        execute format(
            'create trigger trg_%s_perditesuar before update on %I '
            'for each row execute function fin_vulos_perditesimin()', t, t);
    end loop;
end $$;

-- ── 3. DITARI I VEPRIMEVE ─────────────────────────────────────────────────
-- Cdo shtim, ndryshim, fshirje dhe pagese le nje gjurme me daten dhe oren.
-- Pa kete, nje shifer qe levizi pa u kuptuar mbetet pergjithmone pa shpjegim.
create table if not exists fin_veprimet (
    id          bigserial primary key,
    user_id     text        not null default 'une',
    -- momenti i veprimit (jo domosdo i levizjes qe ai veprim regjistroi)
    kur         timestamptz not null default now(),
    -- shtim | ndryshim | fshirje | pagese | shlyerje | cilesime | buxhete |
    -- keshillim | skanim | cmime | eksport
    veprimi     text        not null,
    tabela      text,
    rreshti_id  bigint,
    titulli     text        not null,
    -- fushat e prekura, ne menyre qe nje ndryshim i gabuar te mund te kthehet
    detaje      jsonb       not null default '{}'::jsonb,
    krijuar_me  timestamptz not null default now()
);
create index if not exists idx_fin_veprimet_user
    on fin_veprimet(user_id, kur desc);
create index if not exists idx_fin_veprimet_rreshti
    on fin_veprimet(user_id, tabela, rreshti_id);

alter table fin_veprimet enable row level security;

-- ── 4. ZONA E ORES ────────────────────────────────────────────────────────
insert into fin_cilesimet (celes, vlera) values
    ('zona_kohore', '"Europe/Tirane"'::jsonb)
on conflict (celes) do nothing;
