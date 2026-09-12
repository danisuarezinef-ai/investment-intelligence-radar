create table if not exists public.radar_brain_evidence_snapshots (
  id text primary key,
  kind text not null,
  observed_at timestamptz not null default now(),
  source_max_evaluated_at timestamptz,
  payload jsonb not null,
  payload_hash text not null,
  origin_deployment text,
  real_trading boolean not null default false,
  constraint radar_brain_evidence_snapshots_real_trading_false check (real_trading = false)
);
create index if not exists radar_brain_evidence_snapshots_kind_observed_idx
  on public.radar_brain_evidence_snapshots(kind, observed_at desc);
alter table public.radar_brain_evidence_snapshots enable row level security;
comment on table public.radar_brain_evidence_snapshots is
  'Content-addressed evidence/calibration snapshots for pre-1.6 brain readiness. Service-role Edge writes only; never trading authority.';
