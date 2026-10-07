-- SYNTHETIC DATA ONLY. Use a new empty demo project after the schema files.
begin;
insert into spending_accounts (id,name) values
('demo-checking','Demo Bank Current Account'),
('demo-travel','Demo Travel Card')
on conflict do nothing;
commit;
