-- Pre-1.6 archive candidate inbox. It never mutates Brain Evolution Hall/Graveyard.
create table if not exists public.radar_strategy_archive_candidates (
  origin_node text not null,
  candidate_id text not null,
  competitor_key text not null,
  archive_kind text not null check (archive_kind in ('HALL_CANDIDATE','GRAVEYARD_CANDIDATE')),
  first_observed_at timestamptz not null default now(),
  last_observed_at timestamptz not null default now(),
  eligible boolean not null default false,
  reason text,
  payload jsonb not null default '{}'::jsonb,
  reviewed boolean not null default false,
  applied boolean not null default false check (applied = false),
  real_trading boolean not null default false check (real_trading = false),
  primary key(origin_node,candidate_id)
);
create index if not exists idx_pre160_archive_candidate_kind
  on public.radar_strategy_archive_candidates(origin_node,archive_kind,eligible,last_observed_at desc);

alter table public.radar_strategy_archive_candidates enable row level security;
revoke all on public.radar_strategy_archive_candidates from anon, authenticated;
grant all on public.radar_strategy_archive_candidates to service_role;
