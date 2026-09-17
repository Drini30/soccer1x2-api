-- ==========================================================================
-- FINANCAT — migrimi 3: shuma e lire, dritarja e dates, shpenzimet vjetore
-- ==========================================================================
-- Ekzekutohet NJE HERE ne SQL Editor te Supabase. I sigurt te ri-ekzekutohet.
-- ==========================================================================

-- ── 1. Shuma mujore behet opsionale ───────────────────────────────────────
-- Nje e ardhur freelance nuk ka shume fikse. Kolona ishte NOT NULL, ndaj cdo
-- perpjekje per ta lene bosh kthente:
--   null value in column "shuma_mujore" ... violates not-null constraint
-- Kur mbetet bosh, sistemi e vlereson nga pagesat e meparshme te atij burimi.
alter table fin_te_ardhurat alter column shuma_mujore drop not null;

-- ── 2. Dritarja e dates: "paguhem mes 18-20" ──────────────────────────────
alter table fin_te_ardhurat
    add column if not exists dita_pageses_fund int;
alter table fin_planet
    add column if not exists dita_pageses_fund int;

alter table fin_te_ardhurat
    add constraint fin_te_ardhurat_dita_fund_check
    check (dita_pageses_fund is null or (dita_pageses_fund between 1 and 31)) not valid;
alter table fin_planet
    add constraint fin_planet_dita_fund_check
    check (dita_pageses_fund is null or (dita_pageses_fund between 1 and 31)) not valid;

-- ── 3. Muaji i pageses per shpenzimet vjetore fikse ───────────────────────
-- Taksa e makines paguhet nje here ne vit, ne nje muaj te caktuar. Pa kete
-- kolone nuk dihej se ne cilin muaj duhet kujtuar.
alter table fin_planet
    add column if not exists muaji_pageses int;
alter table fin_planet
    add constraint fin_planet_muaji_check
    check (muaji_pageses is null or (muaji_pageses between 1 and 12)) not valid;

-- ── 4. Llogaria 'Kesh' — para ne dore ─────────────────────────────────────
-- Krijohet vetem nese ende s'ekziston nje llogari cash.
insert into fin_llogarite (user_id, emri, lloji, monedha, bilanci_fillestar, likuide)
select 'une', 'Kesh', 'cash',
       coalesce((select trim(both '"' from vlera::text) from fin_cilesimet
                  where celes = 'monedha_baze'), 'EUR'),
       0, true
where not exists (select 1 from fin_llogarite
                   where user_id = 'une' and lloji = 'cash');
