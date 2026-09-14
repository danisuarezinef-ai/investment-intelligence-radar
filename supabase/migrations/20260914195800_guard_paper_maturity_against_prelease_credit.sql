-- Forward-only PAPER maturity hardening.
-- Production contract: no interval may receive maturity credit for time before the
-- currently held distributed lease epoch was actually acquired.
-- This migration does not enable live trading, broker submission, promotion, release,
-- or Setup 1.6.

create or replace function public.radar_append_paper_maturity_interval(
  p_interval_id text,
  p_session_id text,
  p_lease_owner text,
  p_lease_epoch bigint,
  p_started_at timestamptz,
  p_ended_at timestamptz,
  p_healthy boolean,
  p_exact_restore boolean,
  p_singleton boolean,
  p_persistence_reconciled boolean,
  p_market_data_ok boolean,
  p_backfilled boolean,
  p_downtime boolean,
  p_state_hash text,
  p_reason text,
  p_source text default 'runtime'
) returns public.radar_paper_forward_maturity_ledger
language plpgsql
security definer
set search_path to 'public'
as $function$
declare
  outrow public.radar_paper_forward_maturity_ledger;
  lease_ok boolean := false;
  lease_acquired_at timestamptz;
begin
  if p_interval_id is null or length(trim(p_interval_id)) = 0 then raise exception 'interval_id required'; end if;
  if p_session_id is null or length(trim(p_session_id)) = 0 then raise exception 'session_id required'; end if;
  if p_lease_owner is null or length(trim(p_lease_owner)) = 0 then raise exception 'lease_owner required'; end if;
  if p_ended_at <= p_started_at then raise exception 'invalid interval'; end if;
  if p_ended_at > now() + interval '5 seconds' then raise exception 'future interval forbidden'; end if;
  if p_ended_at - p_started_at > interval '15 minutes' then raise exception 'interval too large'; end if;
  if p_healthy and (p_backfilled or p_downtime) then raise exception 'invalid healthy credit flags'; end if;
  if p_healthy and (p_state_hash is null or length(trim(p_state_hash)) < 16) then raise exception 'healthy interval requires state_hash'; end if;

  select l.acquired_at into lease_acquired_at
  from public.radar_paper_runtime_lease l
  where l.owner_id = p_lease_owner
    and l.session_id = p_session_id
    and l.epoch = p_lease_epoch
    and l.real_trading = false
    and l.expires_at >= now()
  limit 1;

  lease_ok := lease_acquired_at is not null;
  if not lease_ok then raise exception 'active matching lease required'; end if;
  if p_started_at < lease_acquired_at then raise exception 'pre-lease forward maturity credit forbidden'; end if;

  if exists (
    select 1 from public.radar_paper_forward_maturity_ledger
    where tstzrange(started_at, ended_at, '[)') && tstzrange(p_started_at, p_ended_at, '[)')
      and interval_id <> p_interval_id
  ) then raise exception 'overlapping interval'; end if;

  insert into public.radar_paper_forward_maturity_ledger(
    interval_id, session_id, lease_owner, lease_epoch, started_at, ended_at, healthy, exact_restore,
    singleton, persistence_reconciled, market_data_ok, backfilled, downtime, state_hash, reason,
    source, real_trading
  ) values (
    p_interval_id, p_session_id, p_lease_owner, p_lease_epoch, p_started_at, p_ended_at, p_healthy,
    p_exact_restore, p_singleton, p_persistence_reconciled, p_market_data_ok, p_backfilled,
    p_downtime, p_state_hash, p_reason, coalesce(p_source, 'runtime'), false
  )
  on conflict(interval_id) do nothing
  returning * into outrow;

  if outrow.id is null then
    select * into outrow
    from public.radar_paper_forward_maturity_ledger
    where interval_id = p_interval_id;
  end if;

  return outrow;
end;
$function$;
