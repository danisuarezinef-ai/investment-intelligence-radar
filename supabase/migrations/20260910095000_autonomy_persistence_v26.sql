-- Durable cloud authority for autonomous runtime evidence.
-- Stores exact observed payloads only; no synthetic/backfilled evidence.
create table if not exists radar_autonomy_state (
  origin_node text primary key,
  updated_at timestamptz not null default now(),
  payload jsonb not null,
  real_trading boolean not null default false check (real_trading = false)
);

create table if not exists radar_autonomy_runs (
  origin_node text not null,
  origin_id text not null,
  observed_at timestamptz not null,
  payload jsonb not null,
  real_trading boolean not null default false check (real_trading = false),
  primary key(origin_node, origin_id)
);
create index if not exists radar_autonomy_runs_observed_idx on radar_autonomy_runs(observed_at);

create table if not exists radar_autonomy_experiments (
  origin_node text not null,
  origin_id text not null,
  observed_at timestamptz not null,
  payload jsonb not null,
  real_trading boolean not null default false check (real_trading = false),
  primary key(origin_node, origin_id)
);
create index if not exists radar_autonomy_experiments_observed_idx on radar_autonomy_experiments(observed_at);

create table if not exists radar_autonomy_soak_ticks (
  origin_node text not null,
  origin_id text not null,
  observed_at timestamptz not null,
  payload jsonb not null,
  real_trading boolean not null default false check (real_trading = false),
  primary key(origin_node, origin_id)
);
create index if not exists radar_autonomy_soak_ticks_observed_idx on radar_autonomy_soak_ticks(observed_at);

alter table radar_autonomy_state enable row level security;
alter table radar_autonomy_runs enable row level security;
alter table radar_autonomy_experiments enable row level security;
alter table radar_autonomy_soak_ticks enable row level security;
