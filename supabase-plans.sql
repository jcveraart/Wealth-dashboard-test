create table if not exists savings_plans (
  id int primary key, account text, instrument text, isin text, amount_eur numeric, frequency text, day int,
  active boolean, since text, last_execution date, source text
);
alter table savings_plans enable row level security;
comment on table savings_plans is 'Automatic recurring buys (savings plans), for example at Trade Republic';
