-- Stable cross-node identities. Never use a local SQLite id as a remote PK.
alter table public.historical_challenger_results alter column run_id drop not null;
alter table public.historical_challenger_results add column if not exists run_origin_node text;
alter table public.historical_challenger_results add column if not exists run_origin_id bigint;
create unique index if not exists historical_challenger_origin_uq on public.historical_challenger_results(origin_node,origin_id);
create index if not exists historical_challenger_run_origin_idx on public.historical_challenger_results(run_origin_node,run_origin_id);

alter table public.brain_meta_methods add column if not exists origin_node text;
alter table public.brain_meta_methods add column if not exists origin_id text;
alter table public.brain_vault_registry add column if not exists origin_node text;
alter table public.brain_vault_registry add column if not exists origin_id text;
alter table public.brain_hall_of_fame add column if not exists origin_node text;
alter table public.brain_hall_of_fame add column if not exists origin_id text;
alter table public.brain_graveyard add column if not exists origin_node text;
alter table public.brain_graveyard add column if not exists origin_id text;
create unique index if not exists brain_meta_origin_uq on public.brain_meta_methods(origin_node,origin_id);
create unique index if not exists brain_vault_origin_uq on public.brain_vault_registry(origin_node,origin_id);
create unique index if not exists brain_hof_origin_uq on public.brain_hall_of_fame(origin_node,origin_id);
create unique index if not exists brain_graveyard_origin_uq on public.brain_graveyard(origin_node,origin_id);
