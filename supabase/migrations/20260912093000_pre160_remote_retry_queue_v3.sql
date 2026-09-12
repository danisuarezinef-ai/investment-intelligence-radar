create table if not exists public.radar_sync_retry_queue (
  id text primary key,
  channel text not null,
  payload jsonb not null default '{}'::jsonb,
  payload_hash text not null,
  attempts integer not null default 0 check (attempts >= 0),
  next_attempt_at timestamptz not null default now(),
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  origin_node text,
  origin_deployment text
);
create index if not exists radar_sync_retry_queue_due_idx on public.radar_sync_retry_queue(next_attempt_at, created_at);
create index if not exists radar_sync_retry_queue_channel_idx on public.radar_sync_retry_queue(channel, created_at desc);
create table if not exists public.radar_sync_dead_letter (
  id text primary key,
  channel text not null,
  payload jsonb not null default '{}'::jsonb,
  payload_hash text not null,
  attempts integer not null,
  last_error text,
  dead_at timestamptz not null default now(),
  origin_node text,
  origin_deployment text
);
create index if not exists radar_sync_dead_letter_channel_idx on public.radar_sync_dead_letter(channel, dead_at desc);
alter table public.radar_sync_retry_queue enable row level security;
alter table public.radar_sync_dead_letter enable row level security;
comment on table public.radar_sync_retry_queue is 'Pre-1.6 remote retry authority. Service-role only; no trading authority.';
comment on table public.radar_sync_dead_letter is 'Pre-1.6 terminal failed-sync records. Service-role only; no trading authority.';
