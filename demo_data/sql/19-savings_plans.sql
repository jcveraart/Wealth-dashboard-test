-- SYNTHETIC DATA ONLY. Use a new empty demo project after the schema files.
begin;
insert into savings_plans (id,account,instrument,isin,amount_eur,frequency,day,active,since,last_execution,source) values
(0,'Example Broker One','World Equity ETF','DEMO-WORLD',400,'monthly',15,TRUE,'2024-01','2026-09-15','synthetic demo'),
(1,'Example Broker Two','Emerging Markets ETF','DEMO-EM',150,'monthly',15,TRUE,NULL,NULL,'synthetic demo')
on conflict do nothing;
commit;
