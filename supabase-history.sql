-- History tables (added after the first schema). Safe to run more than once.
create table if not exists account_history (
  id         text primary key,          -- '<date>|<account>'
  date       date not null,
  account    text not null,
  value_eur  numeric,
  source     text
);
create table if not exists yearly_flows (
  year                   int not null,
  account                text not null,
  deposits_eur           numeric,
  withdrawals_eur        numeric,
  invested_eur           numeric,
  dividends_eur          numeric,
  interest_received_eur  numeric,
  interest_paid_eur      numeric,
  fees_eur               numeric,
  taxes_eur              numeric,
  profit_eur             numeric,
  return_pct             numeric,
  note                   text,
  primary key (year, account)
);
alter table account_history enable row level security;
alter table yearly_flows enable row level security;
comment on table account_history is 'History: recorded value of each account at points in time (year ends from statements)';
comment on table yearly_flows is 'History: money in and out, income, costs and result per account per year';

create or replace view v_wealth_by_year with (security_invoker = true) as
select extract(year from date)::int as year, account, (array_agg(value_eur order by date desc))[1] as year_end_value_eur
from account_history group by 1, 2 order by 1, 2;
