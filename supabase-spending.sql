-- Spending tables. Safe to run more than once.
create table if not exists spending_categories (
  id text primary key, name text not null, grp text, kind text check (kind in ('expense', 'income', 'transfer'))
);
create table if not exists spending_accounts (
  id text primary key, name text
);
create table if not exists spending_rules (
  id int primary key, match text not null, type text, category_id text, label text
);
create table if not exists spending_transactions (
  id               text primary key,
  date             date not null,
  amount           numeric not null,        -- negative = money out
  description      text,
  merchant         text,
  account_id       text,
  category_id      text,
  category_source  text,                    -- user, rule, auto, ai, unsure or empty
  note             text
);
create index if not exists spending_transactions_date on spending_transactions (date);
create index if not exists spending_transactions_category on spending_transactions (category_id);

alter table spending_categories enable row level security;
alter table spending_accounts enable row level security;
alter table spending_rules enable row level security;
alter table spending_transactions enable row level security;

comment on table spending_transactions is 'Spending: every payment account transaction, categorised';
comment on table spending_categories is 'Spending: categories with their group and kind (expense, income, transfer)';
comment on table spending_rules is 'Spending: rules that put a merchant or text in a category';
comment on table spending_accounts is 'Spending: display names of payment accounts';

create or replace view v_spending_monthly with (security_invoker = true) as
select date_trunc('month', t.date)::date as month, c.grp as "group", coalesce(c.name, 'Uncategorised') as category,
       coalesce(c.kind, 'expense') as kind, sum(t.amount) as total_eur, count(*) as transactions
from spending_transactions t left join spending_categories c on c.id = t.category_id
group by 1, 2, 3, 4 order by 1 desc, 5;

create or replace view v_spending_yearly with (security_invoker = true) as
select extract(year from t.date)::int as year, c.grp as "group", coalesce(c.name, 'Uncategorised') as category,
       sum(-t.amount) as spent_eur, count(*) as transactions
from spending_transactions t left join spending_categories c on c.id = t.category_id
where coalesce(c.kind, 'expense') = 'expense'
group by 1, 2, 3 order by 1 desc, 4 desc;
