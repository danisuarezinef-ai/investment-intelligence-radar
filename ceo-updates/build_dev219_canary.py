from pathlib import Path
import hashlib,json,zipfile
VERSION="1.4.96-rc1-channel-canary"
ART="CEO_1.4.96-rc1-channel-canary-safe.zip"
BASE="https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/"
REQ=['ABRIR_CEO.cmd', 'CEO_UPDATE_PACKAGE.json', 'pyproject.toml', 'scripts/ceo_stdlib_work_mode.py', 'scripts/launch_current.py', 'scripts/relaunch_after_update.py', 'scripts/update_candidate_preflight.py', 'scripts/install_windows_bootstrap.py', 'scripts/bootstrap_release_signer.py', 'scripts/sign_update_with_local_authority.py', 'ceo_core/in_app_updater.py', 'ceo_core/update_channel.py', 'ceo_core/update_trust.json', 'ceo_core/update_failure_lab.py', 'ceo_core/update_diagnostics.py', 'ceo_core/update_state_machine.py', 'ceo_core/update_transaction.py', 'ceo_core/mobile_dev_queue.py', 'ceo_core/self_dev_handoff.py', 'ceo_core/release_readiness_v5.py', 'ceo_core/update_failure_lab_v2.py', 'ceo_core/physical_campaign_plan.py', 'ceo_core/self_dev_inbox.py', 'ceo_core/mobile_sync_v2.py', 'ceo_core/operator_update_summary.py', 'ceo_core/release_readiness_v6.py', 'ceo_core/self_dev_reconciler.py', 'ceo_core/update_failure_lab_v3.py', 'ceo_core/update_recovery_planner_v2.py', 'ceo_core/mobile_dev_queue_v2.py', 'ceo_core/android_contract_v1.py', 'ceo_core/evidence_bridge_v1.py', 'ceo_core/executive_snapshot_v2.py', 'ceo_core/compatibility_matrix_v1.py', 'ceo_core/release_readiness_v7.py', 'ceo_core/soak_guard_v2.py', 'ceo_core/release_signing_authority.py', 'ceo_core/credentials.py', 'ceo_core/windows_shell.py', 'assets/CEO_DE_IAS.ico', 'assets/CEO_DE_IAS.png', 'ceo_core/observability.py', 'ceo_core/operational_resilience.py', 'ceo_core/scheduler.py', 'ceo_core/sqlite_store.py', 'ceo_core/runtime.py', 'ceo_core/models.py', 'ceo_core/store.py', 'ceo_core/quality_gate.py', 'ceo_core/self_correction.py', 'ceo_core/project_memory_v2.py', 'ceo_core/dynamic_task_tree.py', 'ceo_core/value_prioritization.py', 'ceo_core/dependency_manager.py', 'ceo_core/routing.py', 'ceo_core/multi_ai_orchestrator.py', 'ceo_core/consensus_verification.py', 'ceo_core/application_recovery.py', 'ceo_core/evidence_ledger_v2.py', 'ceo_core/operations_dashboard.py', 'ceo_core/operator_attention.py', 'ceo_core/remote_control.py', 'ceo_core/mission_supervisor_v2.py', 'ceo_core/fair_work_allocator.py', 'ceo_core/checkpoint_integrity_v2.py', 'ceo_core/capability_policy_v2.py', 'ceo_core/remote_session_v2.py', 'ceo_core/mobile_compute_protocol.py', 'ceo_core/tool_registry_v2.py', 'ceo_core/canary_execution.py', 'ceo_core/incident_manager_v2.py', 'ceo_core/release_readiness_v3.py', 'ceo_core/project_catalog.py', 'ceo_core/portfolio_supervisor.py', 'ceo_core/quota_governor_v2.py', 'ceo_core/decision_trace_v3.py', 'ceo_core/delegation_contracts_v2.py', 'ceo_core/soak_guard_v1.py', 'ceo_core/release_readiness_v4.py', 'ceo_core/self_evolution_governor.py']
root=Path(".dev219-build")
import shutil; shutil.rmtree(root,ignore_errors=True);root.mkdir()
for rel in REQ:
 p=root/rel;p.parent.mkdir(parents=True,exist_ok=True)
 if rel=="CEO_UPDATE_PACKAGE.json":continue
 if rel=="ABRIR_CEO.cmd": data=b"@echo off\r\necho DEV219 CHANNEL CANARY - ACTIVATION BLOCKED BY DESIGN\r\nexit /b 23\r\n"
 elif rel=="scripts/update_candidate_preflight.py": data=b'print("DEV219 CHANNEL CANARY: remote detection/download/verification PASS; activation deliberately blocked")\nraise SystemExit(23)\n'
 elif rel=="pyproject.toml": data=b'[project]\nname="ceo-dev219-channel-canary"\nversion="1.4.96"\n'
 else:data=b""
 p.write_bytes(data)
hashes={r:hashlib.sha256((root/r).read_bytes()).hexdigest() for r in REQ if r!="CEO_UPDATE_PACKAGE.json"}
contract={"contract_version":1,"app_version":VERSION,"data_schema_version":1,"launcher":"ABRIR_CEO.cmd","required_paths":REQ,"file_hashes":hashes,"purpose":"DEV219 safe remote-channel canary; staging only; activation blocked intentionally"}
(root/"CEO_UPDATE_PACKAGE.json").write_text(json.dumps(contract,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
fixed=(2026,9,19,12,0,0)
with zipfile.ZipFile(ART,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for p in sorted(root.rglob("*")):
  if p.is_file():
   zi=zipfile.ZipInfo(p.relative_to(root).as_posix(),fixed);zi.compress_type=zipfile.ZIP_DEFLATED;zi.external_attr=0o100644<<16;z.writestr(zi,p.read_bytes())
b=Path(ART).read_bytes();sha=hashlib.sha256(b).hexdigest()
manifest={"artifact_name":ART,"channel":"stable","data_schema_version":1,"health_path":"/api/health","launcher":"ABRIR_CEO.cmd","manifest_version":2,"package_contract_version":1,"min_app_version":"1.4.95-rc1-update-handoff-consolidation","max_app_version":"","notes":"DEV219 safe canary: validates remote detection, download, signature, SHA and package contract. Activation is deliberately blocked by preflight.","published_at":"2026-09-19T12:00:00+00:00","release_id":"dev219-1.4.96-rc1-channel-canary","release_sequence":219,"release_status":"release","sha256":sha,"size_bytes":len(b),"url":BASE+ART,"version":VERSION}
Path("DEV219_MANIFEST_UNSIGNED.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(sha,len(b))
