-- PAPER durable transport v1: server-side RPCs used by Edge Functions over HTTPS/PostgREST.
-- Safety invariant: REAL_TRADING is always false.

create or replace function public.radar_status_paper_lease()
returns jsonb language sql security definer set search_path=public as $$
  select to_jsonb(l) from public.radar_paper_runtime_lease l where l.lease_name='autonomous-paper' limit 1
$$;

create or replace function public.radar_put_paper_checkpoint(p_origin_node text,p_observed_at timestamptz,p_schema_version integer,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_row public.radar_paper_engine_checkpoints%rowtype;
begin
  if coalesce(trim(p_origin_node),'')='' then raise exception 'origin_node required'; end if;
  if p_schema_version not in (1,2) then raise exception 'unsupported schema_version'; end if;
  if p_payload is null or jsonb_typeof(p_payload)<>'object' then raise exception 'payload required'; end if;
  if coalesce((p_payload->>'real_trading')::boolean,true) is distinct from false then raise exception 'real_trading must be false'; end if;
  if coalesce(length(p_payload->>'state_hash'),0)<>64 then raise exception 'invalid state_hash'; end if;
  insert into public.radar_paper_engine_checkpoints(origin_node,observed_at,schema_version,payload,real_trading,updated_at)
  values(p_origin_node,coalesce(p_observed_at,clock_timestamp()),p_schema_version,p_payload,false,clock_timestamp())
  on conflict(origin_node) do update set observed_at=excluded.observed_at,schema_version=excluded.schema_version,payload=excluded.payload,real_trading=false,updated_at=clock_timestamp()
  returning * into v_row;
  return to_jsonb(v_row);
end $$;

create or replace function public.radar_get_paper_checkpoint(p_origin_node text)
returns jsonb language sql security definer set search_path=public as $$
  select to_jsonb(c) from public.radar_paper_engine_checkpoints c where c.origin_node=p_origin_node limit 1
$$;

create or replace function public.radar_compare_paper_checkpoint(p_origin_node text,p_expected_state_hash text)
returns jsonb language sql security definer set search_path=public as $$
  select jsonb_build_object('found',c.origin_node is not null,'state_hash',c.payload->>'state_hash','hash_equal',coalesce(c.payload->>'state_hash','')=coalesce(p_expected_state_hash,''),'schema_version',c.schema_version,'real_trading',false,'updated_at',c.updated_at)
  from public.radar_paper_engine_checkpoints c where c.origin_node=p_origin_node limit 1
$$;

create or replace function public.radar_get_autonomy_core(p_origin_node text)
returns jsonb language sql security definer set search_path=public as $$
  select to_jsonb(s) from public.radar_autonomy_state s where s.origin_node=p_origin_node limit 1
$$;

create or replace function public.radar_put_autonomy_core(p_origin_node text,p_updated_at timestamptz,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_row public.radar_autonomy_state%rowtype;
begin
  if coalesce(trim(p_origin_node),'')='' then raise exception 'origin_node required'; end if;
  if p_payload is null or jsonb_typeof(p_payload)<>'object' then raise exception 'payload required'; end if;
  insert into public.radar_autonomy_state(origin_node,updated_at,payload,real_trading)
  values(p_origin_node,coalesce(p_updated_at,clock_timestamp()),p_payload,false)
  on conflict(origin_node) do update set updated_at=excluded.updated_at,payload=excluded.payload,real_trading=false
  where public.radar_autonomy_state.updated_at<=excluded.updated_at
  returning * into v_row;
  if not found then
    select * into v_row from public.radar_autonomy_state where origin_node=p_origin_node;
    return jsonb_build_object('stale_write_rejected',true,'row',to_jsonb(v_row));
  end if;
  return jsonb_build_object('stale_write_rejected',false,'row',to_jsonb(v_row));
end $$;

revoke all on function public.radar_status_paper_lease() from public,anon,authenticated;
revoke all on function public.radar_acquire_paper_lease(text,text,integer) from public,anon,authenticated;
revoke all on function public.radar_heartbeat_paper_lease(text,text,integer) from public,anon,authenticated;
revoke all on function public.radar_release_paper_lease(text,text) from public,anon,authenticated;
revoke all on function public.radar_put_paper_checkpoint(text,timestamptz,integer,jsonb) from public,anon,authenticated;
revoke all on function public.radar_get_paper_checkpoint(text) from public,anon,authenticated;
revoke all on function public.radar_compare_paper_checkpoint(text,text) from public,anon,authenticated;
revoke all on function public.radar_get_autonomy_core(text) from public,anon,authenticated;
revoke all on function public.radar_put_autonomy_core(text,timestamptz,jsonb) from public,anon,authenticated;
grant execute on function public.radar_status_paper_lease() to service_role;
grant execute on function public.radar_acquire_paper_lease(text,text,integer) to service_role;
grant execute on function public.radar_heartbeat_paper_lease(text,text,integer) to service_role;
grant execute on function public.radar_release_paper_lease(text,text) to service_role;
grant execute on function public.radar_put_paper_checkpoint(text,timestamptz,integer,jsonb) to service_role;
grant execute on function public.radar_get_paper_checkpoint(text) to service_role;
grant execute on function public.radar_compare_paper_checkpoint(text,text) to service_role;
grant execute on function public.radar_get_autonomy_core(text) to service_role;
grant execute on function public.radar_put_autonomy_core(text,timestamptz,jsonb) to service_role;
notify pgrst,'reload schema';
