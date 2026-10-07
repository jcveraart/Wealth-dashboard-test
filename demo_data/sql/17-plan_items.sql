-- SYNTHETIC DATA ONLY. Use a new empty demo project after the schema files.
begin;
insert into plan_items (id,text,done) values
(0,'Compare savings rates (example task)',FALSE),
(1,'Review annual account fees (example task)',TRUE)
on conflict do nothing;
commit;
