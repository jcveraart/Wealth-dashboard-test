-- SYNTHETIC DATA ONLY. Use a new empty demo project after the schema files.
begin;
alter table spending_transactions add column if not exists linked_to text;
insert into institutions (id,name,updated_at) values
('example-broker-one','Example Broker One','2026-10-07T14:38:18.748232Z'),
('example-broker-two','Example Broker Two','2026-10-07T14:38:18.748232Z'),
('example-crypto-exchange','Example Crypto Exchange','2026-10-07T14:38:18.748232Z'),
('abn-amro','ABN AMRO','2026-10-07T14:38:18.748232Z'),
('demo-bank','Demo Bank','2026-10-07T14:38:18.748232Z'),
('demo-travel-bank','Demo Travel Bank','2026-10-07T14:38:18.748232Z'),
('example-savings-bank','Example Savings Bank','2026-10-07T14:38:18.748232Z'),
('example-deposit-bank','Example Deposit Bank','2026-10-07T14:38:18.748232Z'),
('example-student-loan','Example Student Loan','2026-10-07T14:38:18.748232Z'),
('example-personal-loan','Example Personal Loan','2026-10-07T14:38:18.748232Z')
on conflict do nothing;
commit;
