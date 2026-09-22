from __future__ import annotations

import hashlib
import json
import os
import pathlib


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def apply(root: pathlib.Path) -> dict:
    root = root.resolve()
    path = root / "ceo_core" / "goal_completion_gate.py"
    text = path.read_text(encoding="utf-8")

    old = '''        evidence = state.metadata.get("goal_audit_evidence") or {}
        refs = list(evidence.get("evidence_refs") or []) if isinstance(evidence, dict) else []
        verdict = self.evaluate(state, evidence_refs=refs)
        if verdict.eligible:
            return {"changed": False, "reason": "grounded_pass", "verdict": verdict.to_dict()}
'''

    new = '''        evidence = state.metadata.get("goal_audit_evidence") or {}
        refs = list(evidence.get("evidence_refs") or []) if isinstance(evidence, dict) else []

        # W6: a deterministic completion certificate intentionally replaces the
        # provider-era continuity-round requirement. On restart, never send that
        # certified state back through the legacy-only continuity gate first.
        #
        # Do not trust the persisted flag blindly: recompute the certificate from
        # current durable evidence and require the stored/evidence hashes to match.
        if isinstance(evidence, dict) and str(evidence.get("source") or "") == "deterministic_completion_certificate_v1":
            try:
                from .deterministic_completion_certifier_v1 import DeterministicCompletionCertifierV1
                stored = state.metadata.get("deterministic_completion_certificate_v1") or {}
                current = DeterministicCompletionCertifierV1().assess(state, self)
                evidence_hash = str(evidence.get("certificate_sha256") or "")
                stored_hash = str(stored.get("certificate_sha256") or "") if isinstance(stored, dict) else ""
                if (
                    current.final_complete
                    and evidence_hash
                    and evidence_hash == stored_hash == current.certificate_sha256
                ):
                    return {
                        "changed": False,
                        "reason": "deterministic_grounded_pass",
                        "certificate_sha256": current.certificate_sha256,
                        "evidence_refs": list(current.evidence_refs),
                        "grounded_refs": list(current.grounded_refs),
                    }
            except Exception as exc:
                state.metadata["deterministic_completion_revalidation_error_v1"] = (
                    f"{type(exc).__name__}: {exc}"
                )[:500]

        verdict = self.evaluate(state, evidence_refs=refs)
        if verdict.eligible:
            return {"changed": False, "reason": "grounded_pass", "verdict": verdict.to_dict()}
'''

    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"W6 migration anchor count={count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

    contract_path = root / "CEO_UPDATE_PACKAGE.json"
    contract_updated = False
    if contract_path.is_file():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        hashes = dict(contract.get("file_hashes") or {})
        rel = "ceo_core/goal_completion_gate.py"
        if rel in hashes:
            hashes[rel] = sha256_file(path)
            contract["file_hashes"] = hashes
            contract_path.write_text(
                json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            contract_updated = True

    return {
        "ok": True,
        "root": str(root),
        "patched": "ceo_core/goal_completion_gate.py",
        "sha256": sha256_file(path),
        "contract_hash_updated": contract_updated,
    }


def main() -> int:
    root_text = str(os.environ.get("CEO_W6_ROOT") or "").strip()
    if not root_text:
        raise RuntimeError("CEO_W6_ROOT is required")
    out = apply(pathlib.Path(root_text))
    print("W6_COMPLETION_PERSISTENCE_PATCH_APPLIED")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
