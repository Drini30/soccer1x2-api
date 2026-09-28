-- ==========================================================================
-- KONTROLL: cfare ka kaluar nga migrimet, tabele per tabele
-- ==========================================================================
-- Vetem lexim — nuk ndryshon asgje. Cdo rresht duhet te thote 'OK'.
-- Kolona 'gjendja' thote SAKTE cila pjese mungon dhe per cilen tabele.
-- ==========================================================================
with tabelat (emri, migrimi) as (values
    ('fin_llogarite', '1'), ('fin_transaksionet', '1'), ('fin_detyrimet', '1'),
    ('fin_planet', '1'), ('fin_te_ardhurat', '1'), ('fin_investimet', '1'),
    ('fin_objektivat', '1'), ('fin_raportet', '1'), ('fin_cilesimet', '1'),
    ('fin_bizneset', '4'), ('fin_biznes_zerat', '4'),
    ('fin_buxhetet', '5'), ('fin_personat', '6'),
    ('fin_veprimet', '7'),
    ('fin_rezervat', '8'), ('fin_mesazhet', '8')
),
gjetjet as (
  select t.emri, t.migrimi,
         to_regclass(t.emri) is not null as ka_tabele,
         exists (select 1 from information_schema.columns c
                  where c.table_name = t.emri
                    and c.column_name = 'perditesuar_me') as ka_kolone,
         exists (select 1 from pg_trigger g
                  where g.tgname = 'trg_' || t.emri || '_perditesuar') as ka_triger
  from tabelat t
)
select emri as tabela,
       case
         when not ka_tabele then 'MUNGON TABELA — ekzekuto migrimin ' || migrimi
         when not ka_kolone then 'mungon kolona perditesuar_me (migrimi 7)'
         when not ka_triger then 'mungon trigeri perditesuar (migrimi 7 ose 8)'
         else 'OK'
       end as gjendja
from gjetjet
union all
select '· kolona kryer_me',
       case when exists (select 1 from information_schema.columns
                          where table_name = 'fin_transaksionet'
                            and column_name = 'kryer_me')
            then 'OK' else 'mungon (migrimi 7, pjesa 1)' end
union all
select '· trigeri i ores',
       case when exists (select 1 from pg_trigger where tgname = 'trg_fin_trx_koha')
            then 'OK' else 'mungon (migrimi 7, pjesa 1)' end
union all
select '· funksioni i vules',
       case when exists (select 1 from pg_proc
                          where proname = 'fin_vulos_perditesimin')
            then 'OK' else 'mungon (migrimi 7, pjesa 2)' end
union all
select '· cilesimet e asistentit',
       case when (select count(*) from fin_cilesimet
                   where celes in ('konfirmim_automatik', 'emri_i_asistentit',
                                   'zona_kohore')) = 3
            then 'OK' else 'mungojne (migrimi 7 pjesa 4, ose 8 pjesa 4)' end
order by 1;
