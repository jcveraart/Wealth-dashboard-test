-- SYNTHETIC DATA ONLY. Use a new empty demo project after the schema files.
begin;
insert into spending_rules (id,match,type,category_id,label) values
(0,'harbour grocer','merchant','groceries','Example grocery rule')
on conflict do nothing;
commit;
