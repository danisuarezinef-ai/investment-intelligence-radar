-- Exact operational checkpoint for PAPER-only simulator engines.
-- Stores the state required to resume a PAPER game after an ephemeral Railway restart.

create table if not exists public.radar_paper_engine_checkpoints (
  origin_node text primary key,
  observed_at timestamptz not null,
  schema_version integer not null default 1 check (schema_version = 1),
  payload jsonb not null,
  real_trading boolean not null default false check (real_trading = false),
  updated_at timestamptz not null default now()
);

alter table public.radar_paper_engine_checkpoints enable row level security;
revoke all on table public.radar_paper_engine_checkpoints from public, anon, authenticated;
grant select, insert, update on table public.radar_paper_engine_checkpoints to service_role;

comment on table public.radar_paper_engine_checkpoints is
'Exact PAPER simulator account/position/trade/mark checkpoint for restart continuity. Never grants live trading authority.';
