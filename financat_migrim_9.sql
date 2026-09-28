-- ==========================================================================
-- ASISTENTI IM — migrimi 9: PORTOFOLI
-- ==========================================================================
-- NGJITE TE GJITHIN, NJE HERE. I sigurt te ri-ekzekutohet.
-- Kerkon migrimet 1-8 te ekzekutuara.
--
-- Portofoli eshte paraja qe mban ne xhep: nje shume e marre nga totali dhe e
-- ndare menjane per shpenzimet e perditshme. Cdo gje qe shkruan aty i zbritet
-- ATIJ, jo llogarive — dhe nese nuk perballon, shkon ne minus. Minusi nuk
-- fshihet: eshte informacioni kryesor qe te thote se ke shpenzuar me shume
-- se sa kishe ndare.
--
-- Portofoli NUK eshte nje tabele e re. Eshte nje llogari e zakonshme me
-- lloj 'portofol', qe te trashegoje pa asnje rresht te ri gjithcka qe
-- ekziston tashme: bilanci i llogaritur nga transaksionet, ditari, data dhe
-- ora, raportet, eksporti. Nje tabele e dyte do te thoshte te njejtat
-- rregulla te shkruara dy here — dhe nje nga te dyja do te mbetej prapa.
-- ==========================================================================

-- ── 1. BISEDA E PORTOFOLIT, E NDARE NGA AJO E ASISTENTIT ──────────────────
-- Te dyja jane biseda, por nuk jane e njejta bisede: njera mban urdhrat mbi
-- gjithe ekonomine, tjetra vetem xhepin. Te perziera, asnjera nuk lexohet.
alter table fin_mesazhet
    add column if not exists konteksti text not null default 'asistenti';

create index if not exists idx_fin_mesazhet_konteksti
    on fin_mesazhet(user_id, konteksti, kur desc);

-- Lidhja me levizjen qe krijoi mesazhi — pa te, "Anulo" nuk do te dinte cilin
-- transaksion te heqe.
alter table fin_mesazhet
    add column if not exists transaksioni_id bigint;

-- ── 2. PRAGU I NGJYRES ────────────────────────────────────────────────────
-- Mbi kete shume portofoli eshte i qete (jeshil); nen te paralajmeron
-- (portokalli); ne zero ose ne minus eshte i kuq.
insert into fin_cilesimet (celes, vlera) values
    ('portofoli_prag', '3000'::jsonb)
on conflict (celes) do nothing;
