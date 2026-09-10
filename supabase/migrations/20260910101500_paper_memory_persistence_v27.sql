-- Durable exact snapshots for PAPER state and experiment memory.
create table if not exists radar_paper_state(
  origin_node text primary key,updated_at timestamptz not null default now(),payload jsonb not null,
  real_trading boolean not null default false check(real_trading=false));
create table if not exists radar_paper_positions(
  origin_node text not null,origin_id text not null,observed_at timestamptz not null,payload jsonb not null,
  real_trading boolean not null default false check(real_trading=false),primary key(origin_node,origin_id));
create table if not exists radar_paper_trades(
  origin_node text not null,origin_id text not null,observed_at timestamptz not null,payload jsonb not null,
  real_trading boolean not null default false check(real_trading=false),primary key(origin_node,origin_id));
create table if not exists radar_portfolio_values(
  origin_node text not null,origin_id text not null,observed_at timestamptz not null,payload jsonb not null,
  real_trading boolean not null default false check(real_trading=false),primary key(origin_node,origin_id));
create table if not exists radar_experiment_memory(
  origin_node text not null,origin_id text not null,observed_at timestamptz not null,payload jsonb not null,
  real_trading boolean not null default false check(real_trading=false),primary key(origin_node,origin_id));
create index if not exists radar_paper_trades_observed_idx on radar_paper_trades(observed_at);
create index if not exists radar_portfolio_values_observed_idx on radar_portfolio_values(observed_at);
create index if not exists radar_experiment_memory_observed_idx on radar_experiment_memory(observed_at);
alter table radar_paper_state enable row level security;
alter table radar_paper_positions enable row level security;
alter table radar_paper_trades enable row level security;
alter table radar_portfolio_values enable row level security;
alter table radar_experiment_memory enable row level security;
