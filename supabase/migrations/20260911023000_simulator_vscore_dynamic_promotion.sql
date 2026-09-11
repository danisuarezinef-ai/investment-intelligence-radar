-- v-score + dynamic Simulation League promotion. PAPER only.

alter table public.radar_simulator_league_daily
  add column if not exists v_score integer,
  add column if not exists v_band text,
  add column if not exists v_confidence double precision,
  add column if not exists v_raw_quality double precision,
  add column if not exists v_components jsonb not null default '{}'::jsonb,
  add column if not exists score_semantics text,
  add column if not exists promotion_readiness double precision,
  add column if not exists promotion_detail jsonb not null default '{}'::jsonb;

alter table public.radar_simulator_league_daily
  drop constraint if exists radar_simulator_league_daily_v_score_check;
alter table public.radar_simulator_league_daily
  add constraint radar_simulator_league_daily_v_score_check
  check (v_score is null or (v_score >= 0 and v_score <= 400));

alter table public.radar_simulator_league_daily
  drop constraint if exists radar_simulator_league_daily_v_confidence_check;
alter table public.radar_simulator_league_daily
  add constraint radar_simulator_league_daily_v_confidence_check
  check (v_confidence is null or (v_confidence >= 0 and v_confidence <= 1));

alter table public.radar_simulator_league_daily
  drop constraint if exists radar_simulator_league_daily_promotion_readiness_check;
alter table public.radar_simulator_league_daily
  add constraint radar_simulator_league_daily_promotion_readiness_check
  check (promotion_readiness is null or (promotion_readiness >= 0 and promotion_readiness <= 100));

alter table public.radar_simulator_league_state
  add column if not exists promotion_threshold double precision not null default 88.0,
  add column if not exists min_promotion_confidence double precision not null default 0.55,
  add column if not exists min_v_advantage double precision not null default 4.0,
  add column if not exists promotion_policy text not null default 'dynamic_v1';

alter table public.radar_simulator_league_state
  drop constraint if exists radar_simulator_league_state_promotion_threshold_check;
alter table public.radar_simulator_league_state
  add constraint radar_simulator_league_state_promotion_threshold_check
  check (promotion_threshold >= 50 and promotion_threshold <= 100);

alter table public.radar_simulator_league_state
  drop constraint if exists radar_simulator_league_state_min_promotion_confidence_check;
alter table public.radar_simulator_league_state
  add constraint radar_simulator_league_state_min_promotion_confidence_check
  check (min_promotion_confidence >= 0 and min_promotion_confidence <= 1);

alter table public.radar_simulator_league_state
  drop constraint if exists radar_simulator_league_state_min_v_advantage_check;
alter table public.radar_simulator_league_state
  add constraint radar_simulator_league_state_min_v_advantage_check
  check (min_v_advantage >= 0 and min_v_advantage <= 200);

comment on column public.radar_simulator_league_daily.v_score is
'Evidence-adjusted 0..400 PAPER strategy quality score; neutral is 200.';
comment on column public.radar_simulator_league_daily.promotion_readiness is
'Dynamic 0..100 readiness to replace the Simulation League Champion. Grants no model/live authority.';
comment on column public.radar_simulator_league_state.promotion_policy is
'Dynamic evidence policy for simulation-only Champion changes; legacy promotion_days is retained only for schema compatibility.';
