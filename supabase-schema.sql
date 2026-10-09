-- Wealth dashboard database. Run once in Supabase: SQL Editor, New query, paste, Run.
-- Tree:  institutions -> accounts -> holdings -> instruments
--        daily history hangs off each level (net_worth_daily, account_daily, holding_daily).
-- Row level security is on with no policies: only the secret key used by the app on your PC can read or write.

-- remove the flat tables of the first version, if they exist

create table if not exists institutions (
  id          text primary key,              -- e.g. 'abn-amro'
  name        text not null,
  updated_at  timestamptz not null default now()
);

create table if not exists accounts (
  id                   text primary key,       -- e.g. 'degiro'
  institution_id       text not null references institutions(id),
  name                 text not null,
  kind                 text not null check (kind in ('brokerage', 'managed', 'savings', 'deposit', 'current', 'loan')),
  opened               text,
  interest_rate_pct    numeric,
  maturity             text,
  counted_in_net_worth boolean not null default true,
  value_eur            numeric,                -- holdings plus cash; for loans the balance owed
  cash_eur             numeric,
  profit_eur           numeric,
  fees_paid_eur        numeric,
  active               boolean not null default true,
  updated_at           timestamptz not null default now()
);

create table if not exists instruments (
  id           text primary key,               -- ISIN, or 'n:<name>' when no ISIN is known
  isin         text,
  name         text not null,
  category     text,                           -- Stock, Broad ETF, Tech ETF, Bond, Bond fund, ...
  asset_type   text,                           -- Stocks, ETFs, Bonds, Other
  ticker       text,
  price_eur    numeric,
  price_live   boolean,
  updated_at   timestamptz not null default now()
);

create table if not exists holdings (
  id                text primary key,          -- '<account id>|<instrument id>'
  account_id        text not null references accounts(id),
  instrument_id     text not null references instruments(id),
  units             numeric not null,
  cost_eur          numeric,
  net_cashflow_eur  numeric,
  value_eur         numeric,
  profit_eur        numeric,
  day_change_eur    numeric,
  return_pct        numeric,
  maturity          text,
  active            boolean not null default true,
  updated_at        timestamptz not null default now()
);
create index on holdings (account_id);
create index on holdings (instrument_id);
create index on accounts (institution_id);

create table if not exists net_worth_daily (
  date           date primary key,
  net_worth      numeric,
  assets         numeric,
  debt           numeric,
  managed        numeric,
  savings        numeric,
  self_directed  numeric
);

create table if not exists account_daily (
  date        date not null,
  account_id  text not null references accounts(id),
  value_eur   numeric,
  primary key (date, account_id)
);

create table if not exists holding_daily (
  date        date not null,
  holding_id  text not null references holdings(id),
  units       numeric,
  price_eur   numeric,
  value_eur   numeric,
  primary key (date, holding_id)
);

create table if not exists plan_items (
  id     int primary key,
  text   text not null,
  done   boolean not null default false
);

create table if not exists portfolio_backup (
  id          int primary key,
  data        jsonb not null,
  updated_at  timestamptz not null default now()
);

-- handy views for browsing in the Table Editor
create or replace view v_tree with (security_invoker = true) as
select i.name as institution, a.name as account, a.kind, n.name as instrument, n.isin, n.category,
       h.units, n.price_eur, h.value_eur, h.profit_eur, h.return_pct
from holdings h
join accounts a on a.id = h.account_id
join institutions i on i.id = a.institution_id
join instruments n on n.id = h.instrument_id
where h.active
order by i.name, a.name, h.value_eur desc;

create or replace view v_institutions with (security_invoker = true) as
select i.name as institution,
       sum(case when a.kind = 'loan' then 0 else a.value_eur end) as assets_eur,
       sum(case when a.kind = 'loan' and a.counted_in_net_worth then a.value_eur else 0 end) as debt_eur,
       count(*) as accounts
from accounts a join institutions i on i.id = a.institution_id
where a.active
group by i.name
order by assets_eur desc;

create or replace view v_allocation with (security_invoker = true) as
select n.asset_type, sum(h.value_eur) as value_eur, count(*) as holdings
from holdings h join instruments n on n.id = h.instrument_id
join accounts a on a.id = h.account_id
where h.active and a.kind <> 'managed'
group by n.asset_type
order by value_eur desc;

alter table institutions enable row level security;
alter table accounts enable row level security;
alter table instruments enable row level security;
alter table holdings enable row level security;
alter table net_worth_daily enable row level security;
alter table account_daily enable row level security;
alter table holding_daily enable row level security;
alter table plan_items enable row level security;
alter table portfolio_backup enable row level security;
