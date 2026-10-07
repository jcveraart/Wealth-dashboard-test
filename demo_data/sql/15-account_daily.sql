-- SYNTHETIC DATA ONLY. Use a new empty demo project after the schema files.
begin;
insert into account_daily (date,account_id,value_eur) values
('2026-10-07','example-broker-one',28600.2),
('2026-10-07','example-broker-two',24051.0),
('2026-10-07','example-crypto-exchange',3939.0),
('2026-10-07','example-managed-portfolio',22019.5),
('2026-10-07','demo-bank-current-account',2750.0),
('2026-10-07','demo-travel-card',650.0),
('2026-10-07','emergency-savings',12532.0),
('2026-10-07','fixed-deposit',6670.0),
('2026-10-07','example-student-loan',14750.0),
('2026-10-07','example-personal-loan',2400.0)
on conflict do nothing;
commit;
