-- Kontroll i shpejte: a u ekzekutuan vertet migrimet 7 dhe 8?
-- Cdo rresht duhet te thote 'OK'. Cfaredo 'MUNGON' tregon se cila pjese e
-- skedarit nuk kaloi — zakonisht nje bllok i kopjuar gjysme.
select 'kolona kryer_me (migrimi 7)' as pjesa,
       case when exists (select 1 from information_schema.columns
                          where table_name = 'fin_transaksionet'
                            and column_name = 'kryer_me')
            then 'OK' else 'MUNGON' end as gjendja
union all
select 'trigeri i ores (migrimi 7)',
       case when exists (select 1 from pg_trigger
                          where tgname = 'trg_fin_trx_koha')
            then 'OK' else 'MUNGON' end
union all
select 'tabela fin_veprimet (migrimi 7)',
       case when to_regclass('fin_veprimet') is not null
            then 'OK' else 'MUNGON' end
union all
select 'kolonat perditesuar_me (migrimi 7): '
       || (select count(*)::text from information_schema.columns
            where column_name = 'perditesuar_me' and table_name like 'fin\_%')
       || ' nga 15',
       case when (select count(*) from information_schema.columns
                   where column_name = 'perditesuar_me'
                     and table_name like 'fin\_%') >= 15
            then 'OK' else 'MUNGON' end
union all
select 'tabela fin_rezervat (migrimi 8)',
       case when to_regclass('fin_rezervat') is not null
            then 'OK' else 'MUNGON' end
union all
select 'tabela fin_mesazhet (migrimi 8)',
       case when to_regclass('fin_mesazhet') is not null
            then 'OK' else 'MUNGON' end
union all
select 'trigerat e rinj (migrimi 8)',
       case when (select count(*) from pg_trigger
                   where tgname in ('trg_fin_rezervat_perditesuar',
                                    'trg_fin_mesazhet_perditesuar')) = 2
            then 'OK' else 'MUNGON' end
union all
select 'cilesimet e asistentit (migrimi 8)',
       case when (select count(*) from fin_cilesimet
                   where celes in ('konfirmim_automatik',
                                   'emri_i_asistentit')) = 2
            then 'OK' else 'MUNGON' end;
