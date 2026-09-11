-- Pre-1.6 evidence v3: daily snapshots, frozen PIT trade context and append-only decision hash chain.
create table if not exists public.radar_pre160_evidence_daily (
  origin_node text not null,
  day date not null,
  first_observed_at timestamptz not null default now(),
  last_observed_at timestamptz not null default now(),
  snapshot_hash text not null,
  readiness_score double precision,
  blockers jsonb not null default '[]'::jsonb,
  snapshot jsonb not null default '{}'::jsonb,
  audit jsonb not null default '{}'::jsonb,
  real_trading boolean not null default false check (real_trading = false),
  primary key(origin_node,day)
);

create table if not exists public.radar_pre160_decision_contexts (
  origin_node text not null,
  source_key text not null,
  trade_id bigint not null,
  trade_ts timestamptz not null,
  competitor_key text not null,
  symbol text not null,
  side text not null,
  regime_ts timestamptz,
  regime text,
  regime_confidence double precision,
  regime_features jsonb not null default '{}'::jsonb,
  status text not null,
  frozen_at timestamptz not null default now(),
  payload jsonb not null default '{}'::jsonb,
  real_trading boolean not null default false check (real_trading = false),
  primary key(origin_node,source_key,trade_id)
);

create table if not exists public.radar_pre160_evidence_chain (
  id bigint generated always as identity primary key,
  origin_node text not null,
  decision_fingerprint text not null,
  competitor_key text not null,
  exit_ts timestamptz not null,
  observed_at timestamptz not null default now(),
  prev_hash text,
  record_hash text not null,
  payload jsonb not null default '{}'::jsonb,
  real_trading boolean not null default false check (real_trading = false),
  unique(origin_node,decision_fingerprint),
  unique(origin_node,record_hash)
);

create index if not exists idx_pre160_evidence_daily_observed on public.radar_pre160_evidence_daily(origin_node,last_observed_at desc);
create index if not exists idx_pre160_context_trade on public.radar_pre160_decision_contexts(origin_node,trade_ts desc);
create index if not exists idx_pre160_chain_tail on public.radar_pre160_evidence_chain(origin_node,id desc);

alter table public.radar_pre160_evidence_daily enable row level security;
alter table public.radar_pre160_decision_contexts enable row level security;
alter table public.radar_pre160_evidence_chain enable row level security;

revoke all on public.radar_pre160_evidence_daily from anon, authenticated;
revoke all on public.radar_pre160_decision_contexts from anon, authenticated;
revoke all on public.radar_pre160_evidence_chain from anon, authenticated;
grant all on public.radar_pre160_evidence_daily to service_role;
grant all on public.radar_pre160_decision_contexts to service_role;
grant all on public.radar_pre160_evidence_chain to service_role;
