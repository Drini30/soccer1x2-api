-- ==========================================================================
-- FINANCAT — migrimi 2: njoftimet e pagesave dhe datat e te ardhurave
-- ==========================================================================
-- Ekzekutohet NJE HERE ne SQL Editor te Supabase, mbi skemen ekzistuese.
-- Eshte i sigurt te ri-ekzekutohet: cdo shtese perdor IF NOT EXISTS.
-- Asnje te dhene ekzistuese nuk preket.
-- ==========================================================================

-- ── 1. TE ARDHURAT: kur pritet te vije paraja ─────────────────────────────
alter table fin_te_ardhurat
    -- Dita e muajit kur pritet pagesa (1-31). NULL = pa date fikse.
    add column if not exists dita_pageses int,
    -- Paga eshte fikse; freelance-i ndryshon muaj pas muaji. Kur eshte true,
    -- njoftimi te pyet "sa more kete muaj?" ne vend qe te propozoje shumen.
    add column if not exists shuma_e_ndryshueshme boolean not null default false,
    -- Ku bie zakonisht kjo pagese — sherben per te parambushur formularin.
    add column if not exists llogaria_id bigint references fin_llogarite(id) on delete set null;

alter table fin_te_ardhurat
    add constraint fin_te_ardhurat_dita_check
    check (dita_pageses is null or (dita_pageses between 1 and 31)) not valid;

-- ── 2. PLANET: dita e pageses per shpenzimet e perseritshme ───────────────
alter table fin_planet
    add column if not exists dita_pageses int,
    add column if not exists llogaria_id bigint references fin_llogarite(id) on delete set null;

alter table fin_planet
    add constraint fin_planet_dita_check
    check (dita_pageses is null or (dita_pageses between 1 and 31)) not valid;

-- ── 3. TRANSAKSIONET: lidhja me burimin e te ardhurave ────────────────────
-- Njoftimi per nje page konsiderohet i mbyllur kur ekziston nje transaksion i
-- lidhur me ate burim brenda muajit. Pa kete kolone, sistemi s'do ta dinte
-- dot nese pagesa u regjistrua apo jo.
alter table fin_transaksionet
    add column if not exists te_ardhura_id bigint;

create index if not exists idx_fin_trx_te_ardhura
    on fin_transaksionet(user_id, te_ardhura_id, data desc);
create index if not exists idx_fin_trx_plani
    on fin_transaksionet(user_id, plani_id, data desc);

-- ── 4. Kursi i LEK-ut ─────────────────────────────────────────────────────
-- 'LEK' shkruhet me shpesh se kodi nderkombetar 'ALL'. Tani te dyja njihen;
-- kurset ndryshohen nga faqja: Menu → Cilesimet.
update fin_cilesimet
   set vlera = vlera || '{"LEK": 0.0102}'::jsonb,
       perditesuar_me = now()
 where celes = 'kurset'
   and not (vlera ? 'LEK');
