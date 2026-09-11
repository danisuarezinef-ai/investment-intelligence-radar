from pathlib import Path


def test_schema2_constraint_migration_allows_only_versions_one_and_two():
    path=Path('supabase/migrations/20260912004500_paper_engine_checkpoint_schema_v2.sql')
    sql=path.read_text(encoding='utf-8').lower().replace(' ','')
    assert 'dropconstraintifexistsradar_paper_engine_checkpoints_schema_version_check' in sql
    assert 'check(schema_versionin(1,2))' in sql
    assert 'real_trading' not in sql  # this hotfix must not weaken the existing trading boundary
