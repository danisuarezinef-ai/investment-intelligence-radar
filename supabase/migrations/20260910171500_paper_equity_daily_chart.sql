-- Durable 30-day PAPER equity curve for the Simulation Lab.
-- Uses only persisted observed marks. Missing agent coverage is excluded rather
-- than synthesized/backfilled. REAL trading is unrelated and remains disabled.

create or replace function public.radar_paper_equity_daily(
  p_days integer default 30,
  p_origin_node text default 'cloud-primary'
)
returns table(day date, equity numeric, agents integer)
language sql
stable
security invoker
set search_path = public
as $$
  with params as (
    select least(greatest(coalesce(p_days,30),1),90)::integer as days
  ),
  expected as (
    select count(*)::integer as n
    from public.paper_agents
    where enabled = true
  ),
  ranked as (
    select
      pv.agent_id,
      (pv.ts at time zone 'UTC')::date as day,
      pv.equity,
      row_number() over (
        partition by pv.agent_id, (pv.ts at time zone 'UTC')::date
        order by pv.ts desc, pv.id desc
      ) as rn
    from public.portfolio_values pv
    join public.paper_agents pa on pa.id = pv.agent_id and pa.enabled = true
    cross join params p
    where pv.origin_node = coalesce(nullif(p_origin_node,''),'cloud-primary')
      and pv.ts >= now() - make_interval(days => p.days)
      and pv.equity is not null
  ),
  daily as (
    select day, sum(equity)::numeric as equity, count(*)::integer as agents
    from ranked
    where rn = 1
    group by day
  )
  select d.day, d.equity, d.agents
  from daily d
  cross join expected e
  where e.n > 0 and d.agents = e.n
  order by d.day;
$$;

revoke all on function public.radar_paper_equity_daily(integer,text) from public;
grant execute on function public.radar_paper_equity_daily(integer,text) to service_role;

comment on function public.radar_paper_equity_daily(integer,text) is
'Observed daily aggregate PAPER equity using the final persisted mark per enabled agent; incomplete days are excluded and never backfilled.';
