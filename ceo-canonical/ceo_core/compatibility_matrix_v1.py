from __future__ import annotations

from typing import Any


def assess_compatibility(current: dict[str, int], candidate: dict[str, int]) -> dict[str, Any]:
    cur_data=int(current.get("data_schema",1)); new_data=int(candidate.get("data_schema",1))
    cur_contract=int(current.get("package_contract",1)); new_contract=int(candidate.get("package_contract",1))
    cur_protocol=int(current.get("sync_protocol",1)); new_protocol=int(candidate.get("sync_protocol",1))
    blockers=[]; migrations=[]
    if new_data < cur_data: blockers.append("data_schema_downgrade")
    elif new_data > cur_data+1: blockers.append("data_schema_jump_too_large")
    elif new_data == cur_data+1: migrations.append("data_schema_forward_migration")
    if new_contract < cur_contract: blockers.append("package_contract_downgrade")
    if new_protocol < cur_protocol: blockers.append("sync_protocol_downgrade")
    return {
        "schema_version":1,"compatible":not blockers,"blockers":blockers,"required_migrations":migrations,
        "rollback_requires_data_backup":bool(migrations),"automatic_destructive_migration":False,
        "current":dict(current),"candidate":dict(candidate),
    }
