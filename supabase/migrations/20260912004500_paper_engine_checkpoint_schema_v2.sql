begin;

alter table public.radar_paper_engine_checkpoints
  drop constraint if exists radar_paper_engine_checkpoints_schema_version_check;

alter table public.radar_paper_engine_checkpoints
  add constraint radar_paper_engine_checkpoints_schema_version_check
  check (schema_version in (1,2));

commit;
