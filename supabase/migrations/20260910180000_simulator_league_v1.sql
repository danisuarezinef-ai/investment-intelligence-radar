-- Durable PAPER Simulation League. No real execution authority exists here.

create table if not exists public.radar_simulator_league_daily (
  origin_node text not null,
  competitor_key text not null,
  day date not null,
  observed_at timestamptz not null,
  display_name text not null,
  risk_rank integer not null,
  risk_label text not null,
  strategy_kind text not null,
  initial_equity numeric not null check (initial_equity > 0),
  equity numeric not null check (equity >= 0),
  cash numeric,
  invested numeric,
  drawdown_pct double precision,
  target_invested_pct double precision,
  real_trading boolean not null default false check (real_trading = false),
  primary key (origin_node, competitor_key, day)
);

create index if not exists idx_radar_simulator_league_daily_day
  on public.radar_simulator_league_daily(origin_node, day desc);

create table if not exists public.radar_simulator_league_state (
  origin_node text primary key,
  champion_key text not null default 'champion',
  challenger_order jsonb not null default '["conservative","balanced","aggressive","high_conviction","experimental"]'::jsonb,
  champion_since date not null default current_date,
  promotion_days integer not null default 10 check (promotion_days >= 2),
  risk_guard_pp double precision not null default 10.0 check (risk_guard_pp >= 0),
  last_promotion_day date,
  updated_at timestamptz not null default now(),
  real_trading boolean not null default false check (real_trading = false)
);

create table if not exists public.radar_simulator_league_events (
  id bigint generated always as identity primary key,
  origin_node text not null,
  day date not null,
  from_key text not null,
  to_key text not null,
  reason text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  real_trading boolean not null default false check (real_trading = false)
);

alter table public.radar_simulator_league_daily enable row level security;
alter table public.radar_simulator_league_state enable row level security;
alter table public.radar_simulator_league_events enable row level security;

revoke all on table public.radar_simulator_league_daily from public, anon, authenticated;
revoke all on table public.radar_simulator_league_state from public, anon, authenticated;
revoke all on table public.radar_simulator_league_events from public, anon, authenticated;

grant select, insert, update on table public.radar_simulator_league_daily to service_role;
grant select, insert, update on table public.radar_simulator_league_state to service_role;
grant select, insert on table public.radar_simulator_league_events to service_role;
grant usage, select on sequence public.radar_simulator_league_events_id_seq to service_role;

comment on table public.radar_simulator_league_daily is
'Observed PAPER strategy marks for the Simulation League. Same-day rows converge to the latest observation; no synthetic history.';
comment on table public.radar_simulator_league_state is
'Simulation-only Champion/Challenger role state. It grants no model or live-trading authority.';
