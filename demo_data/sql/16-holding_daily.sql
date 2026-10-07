-- SYNTHETIC DATA ONLY. Use a new empty demo project after the schema files.
begin;
insert into holding_daily (date,holding_id,units,price_eur,value_eur) values
('2026-10-07','example-broker-one|DEMO-WORLD',140,96.8,13552.0),
('2026-10-07','example-broker-one|DEMO-EUROPE',80,52.4,4192.0),
('2026-10-07','example-broker-one|DEMO-TECH',32,143.1,4579.2),
('2026-10-07','example-broker-one|DEMO-ASML',5,712,3560),
('2026-10-07','example-broker-one|DEMO-UNILEVER',45,49.6,2232.0),
('2026-10-07','example-broker-two|DEMO-APPLE',14,184,2576),
('2026-10-07','example-broker-two|DEMO-JAPAN',50,56.3,2815.0),
('2026-10-07','example-broker-two|DEMO-EM',110,31.7,3487.0),
('2026-10-07','example-broker-two|DEMO-WORLD',35,96.8,3388.0),
('2026-10-07','example-broker-two|DEMO-BOND-1',4000,0.985,3940.0),
('2026-10-07','example-broker-two|DEMO-CORP',75,101.8,7635.0),
('2026-10-07','example-crypto-exchange|DEMO-BTC',0.035,58200,2037.0000000000002),
('2026-10-07','example-crypto-exchange|DEMO-ETH',0.65,2780,1807.0),
('2026-10-07','example-managed-portfolio|DEMO-MWORLD',125,112.3,14037.5),
('2026-10-07','example-managed-portfolio|DEMO-MBOND',80,95.4,7632.0)
on conflict do nothing;
commit;
