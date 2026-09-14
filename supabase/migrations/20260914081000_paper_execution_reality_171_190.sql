-- Tasks 171-190: PAPER-only execution evidence authority. Production migration already applied via Supabase MCP.
create table if not exists public.radar_market_quote_observations (
 quote_key text primary key,symbol text not null,observed_at timestamptz not null,source text not null,
 bid numeric not null check(bid>0),ask numeric not null check(ask>=bid),volume numeric,market_open boolean,
 provider_status text not null default 'OK',raw_hash text not null,metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(),real_trading boolean not null default false check(real_trading=false));
alter table public.radar_market_quote_observations enable row level security;
revoke all on public.radar_market_quote_observations from anon,authenticated;
create index if not exists radar_market_quote_symbol_time_idx on public.radar_market_quote_observations(symbol,observed_at desc);

create table if not exists public.radar_paper_execution_orders (
 order_id text primary key,idempotency_key text not null unique,decision_id text,session_id text not null,agent_id uuid,
 symbol text not null,side text not null check(side in('BUY','SELL')),requested_qty numeric not null check(requested_qty>0),
 requested_at timestamptz not null,quote_key text references public.radar_market_quote_observations(quote_key),
 status text not null check(status in('PENDING','PARTIAL','FILLED','REJECTED','CANCELLED')),max_slippage_bps numeric,
 metadata jsonb not null default '{}'::jsonb,created_at timestamptz not null default now(),
 real_trading boolean not null default false check(real_trading=false));
alter table public.radar_paper_execution_orders enable row level security;
revoke all on public.radar_paper_execution_orders from anon,authenticated;
create index if not exists radar_paper_execution_orders_quote_idx on public.radar_paper_execution_orders(quote_key);

create table if not exists public.radar_paper_execution_fills (
 fill_id text primary key,order_id text not null references public.radar_paper_execution_orders(order_id),
 fill_seq integer not null check(fill_seq>=1),qty numeric not null check(qty>0),price numeric not null check(price>0),
 spread_cost numeric not null default 0 check(spread_cost>=0),slippage_cost numeric not null default 0 check(slippage_cost>=0),
 fee numeric not null default 0 check(fee>=0),observed_at timestamptz not null,
 quote_key text references public.radar_market_quote_observations(quote_key),accounting_applied boolean not null default false,
 metadata jsonb not null default '{}'::jsonb,created_at timestamptz not null default now(),
 real_trading boolean not null default false check(real_trading=false),unique(order_id,fill_seq));
alter table public.radar_paper_execution_fills enable row level security;
revoke all on public.radar_paper_execution_fills from anon,authenticated;
create index if not exists radar_paper_execution_fills_order_idx on public.radar_paper_execution_fills(order_id,fill_seq);
create index if not exists radar_paper_execution_fills_quote_idx on public.radar_paper_execution_fills(quote_key);

create or replace view public.radar_paper_execution_reality_summary with (security_invoker=true) as
select (select count(*) from public.radar_market_quote_observations) quote_count,
 (select count(*) from public.radar_paper_execution_orders) order_count,
 (select count(*) from public.radar_paper_execution_fills) fill_count,
 (select count(*) from public.radar_paper_execution_fills where accounting_applied) accounted_fill_count,false real_trading;
revoke all on public.radar_paper_execution_reality_summary from anon,authenticated;

-- Backend Edge functions use direct DB connections; public Data API execution is not required.
revoke execute on function public.radar_append_paper_maturity_interval(text,text,text,bigint,timestamptz,timestamptz,boolean,boolean,boolean,boolean,boolean,boolean,boolean,text,text,text) from public,anon,authenticated;
revoke execute on function public.radar_paper_valid_forward_hours() from public,anon,authenticated;

-- Database-level race-proof protection against double-counted forward time.
do $$ begin
 if not exists(select 1 from pg_constraint where conname='paper_maturity_no_overlap' and conrelid='public.radar_paper_forward_maturity_ledger'::regclass) then
  alter table public.radar_paper_forward_maturity_ledger add constraint paper_maturity_no_overlap exclude using gist (tstzrange(started_at,ended_at,'[)') with &&);
 end if;
end $$;
