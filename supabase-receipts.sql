-- Additive migration. Raw files stay on the laptop; these tables keep metadata only.
create table if not exists receipt_documents (
  id text primary key,
  supplier text, invoice_number text, order_number text, date date,
  currency text, total numeric, reconciled boolean not null default false,
  attachments jsonb not null default '[]'::jsonb,
  uploaded timestamptz,
  updated_at timestamptz not null default now(),
  active boolean not null default true
);
create table if not exists receipt_items (
  id text primary key,
  receipt_id text not null references receipt_documents(id) on delete cascade,
  description text, quantity numeric, unit_price numeric, total numeric,
  category text, sku text
);
create table if not exists receipt_payment_links (
  receipt_id text not null references receipt_documents(id) on delete cascade,
  transaction_id text not null,
  amount_eur numeric not null check (amount_eur > 0),
  confirmed boolean not null default true,
  active boolean not null default true,
  updated_at timestamptz not null default now(),
  primary key(receipt_id,transaction_id)
);
create table if not exists payment_document_sources (
  id text primary key, name text, media_type text, kind text
);
create table if not exists payment_source_links (
  transaction_id text not null, source_id text not null references payment_document_sources(id),
  active boolean not null default true, updated_at timestamptz not null default now(),
  primary key(transaction_id,source_id)
);
alter table receipt_documents enable row level security;
alter table receipt_items enable row level security;
alter table receipt_payment_links enable row level security;
alter table payment_document_sources enable row level security;
alter table payment_source_links enable row level security;
create index if not exists receipt_links_transaction on receipt_payment_links(transaction_id);
