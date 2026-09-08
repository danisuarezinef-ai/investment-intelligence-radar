-- Decision Lab v5 forward integrity. Service ingestion only; no public policies.
alter table public.decision_forward_ledger add column if not exists local_prediction_id text;
alter table public.decision_forward_ledger add column if not exists feature_fingerprint text;
alter table public.decision_forward_ledger add column if not exists thesis_fingerprint text;
alter table public.decision_forward_ledger add column if not exists confidence double precision;
alter table public.decision_forward_ledger add column if not exists uncertainty jsonb not null default '{}'::jsonb;
alter table public.decision_forward_ledger add column if not exists decision_state text not null default 'WAIT';
alter table public.decision_forward_ledger add column if not exists paper_allocation jsonb;
alter table public.decision_forward_ledger add column if not exists data_cutoff timestamptz;
alter table public.decision_forward_ledger add column if not exists known_at_boundary timestamptz;
alter table public.decision_forward_ledger add column if not exists provenance_snapshot jsonb not null default '{}'::jsonb;
alter table public.decision_thesis_events add column if not exists thesis_id text;
alter table public.decision_thesis_events add column if not exists event_hash text;
create unique index if not exists decision_thesis_event_hash_uq on public.decision_thesis_events(event_hash) where event_hash is not null;

create or replace function public.guard_forward_ledger_immutability() returns trigger
language plpgsql security invoker set search_path='' as $$
begin
 if row(new.created_at,new.symbol,new.horizon,new.target_date,new.model_version,new.prediction_hash,new.payload,
   new.feature_fingerprint,new.thesis_fingerprint,new.confidence,new.uncertainty,new.decision_state,
   new.paper_allocation,new.data_cutoff,new.known_at_boundary,new.provenance_snapshot)
   is distinct from
   row(old.created_at,old.symbol,old.horizon,old.target_date,old.model_version,old.prediction_hash,old.payload,
   old.feature_fingerprint,old.thesis_fingerprint,old.confidence,old.uncertainty,old.decision_state,
   old.paper_allocation,old.data_cutoff,old.known_at_boundary,old.provenance_snapshot)
 then raise exception 'forward prediction is immutable'; end if;
 if old.outcome is not null and new.outcome is distinct from old.outcome
 then raise exception 'outcome already assigned'; end if;
 return new;
end $$;
revoke all on function public.guard_forward_ledger_immutability() from public,anon,authenticated;
drop trigger if exists decision_forward_immutable on public.decision_forward_ledger;
create trigger decision_forward_immutable before update on public.decision_forward_ledger
for each row execute function public.guard_forward_ledger_immutability();

create or replace function public.guard_thesis_append_only() returns trigger
language plpgsql security invoker set search_path='' as $$
begin raise exception 'thesis history is append-only'; end $$;
revoke all on function public.guard_thesis_append_only() from public,anon,authenticated;
drop trigger if exists decision_thesis_no_update on public.decision_thesis_events;
drop trigger if exists decision_thesis_no_delete on public.decision_thesis_events;
create trigger decision_thesis_no_update before update on public.decision_thesis_events
for each row execute function public.guard_thesis_append_only();
create trigger decision_thesis_no_delete before delete on public.decision_thesis_events
for each row execute function public.guard_thesis_append_only();

alter table public.decision_forward_ledger enable row level security;
alter table public.decision_thesis_events enable row level security;
