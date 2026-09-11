-- Pre-1.6 strategy evaluation authority. PAPER/SHADOW only; no live execution.
create table if not exists public.radar_strategy_evaluation_state (
  origin_node text primary key,
  capture_started_at timestamptz not null default now(),
  schema_version integer not null default 1,
  updated_at timestamptz not null default now(),
  real_trading boolean not null default false check (real_trading = false)
);

create table if not exists public.radar_strategy_decision_outcomes (
  origin_node text not null,
  competitor_key text not null,
  decision_fingerprint text not null,
  first_observed_at timestamptz not null default now(),
  entry_ts timestamptz,
  exit_ts timestamptz not null,
  symbol text not null,
  qty numeric,
  entry_price numeric,
  exit_price numeric,
  entry_capital numeric,
  exit_value_net numeric,
  realized_pnl numeric,
  return_pct double precision,
  costs numeric,
  duration_hours double precision,
  outcome_class text,
  entry_reason text,
  exit_reason text,
  evidence_class text not null,
  forward_eligible boolean not null default false,
  payload jsonb not null default '{}'::jsonb,
  real_trading boolean not null default false check (real_trading = false),
  primary key(origin_node, competitor_key, decision_fingerprint)
);
create index if not exists idx_strategy_decision_outcomes_exit
  on public.radar_strategy_decision_outcomes(origin_node, competitor_key, exit_ts);

create table if not exists public.radar_strategy_evaluation_daily (
  origin_node text not null,
  competitor_key text not null,
  day date not null,
  observed_at timestamptz not null,
  v_score integer,
  v_confidence double precision,
  decision_quality double precision,
  risk_control double precision,
  generalization double precision,
  stability_score double precision,
  transfer_score double precision,
  anti_overfitting_score double precision,
  data_quality_score double precision,
  promotion_readiness double precision,
  evaluation jsonb not null default '{}'::jsonb,
  real_trading boolean not null default false check (real_trading = false),
  primary key(origin_node, competitor_key, day)
);

create table if not exists public.radar_learning_journal (
  origin_node text not null,
  lesson_id text not null,
  subject text not null,
  claim text not null,
  status text not null,
  created_at timestamptz not null,
  updated_at timestamptz not null default now(),
  regime text,
  horizon text,
  confidence text,
  supporting_evidence jsonb not null default '{}'::jsonb,
  validation jsonb not null default '{}'::jsonb,
  real_trading boolean not null default false check (real_trading = false),
  primary key(origin_node, lesson_id)
);

alter table public.radar_strategy_evaluation_state enable row level security;
alter table public.radar_strategy_decision_outcomes enable row level security;
alter table public.radar_strategy_evaluation_daily enable row level security;
alter table public.radar_learning_journal enable row level security;

revoke all on public.radar_strategy_evaluation_state from anon, authenticated;
revoke all on public.radar_strategy_decision_outcomes from anon, authenticated;
revoke all on public.radar_strategy_evaluation_daily from anon, authenticated;
revoke all on public.radar_learning_journal from anon, authenticated;
grant all on public.radar_strategy_evaluation_state to service_role;
grant all on public.radar_strategy_decision_outcomes to service_role;
grant all on public.radar_strategy_evaluation_daily to service_role;
grant all on public.radar_learning_journal to service_role;
