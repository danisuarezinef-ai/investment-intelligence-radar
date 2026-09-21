from __future__ import annotations

from typing import Any

from .update_failure_lab_v3 import UpdateFailureLabV3
from .android_contract_v1 import validate_android_request
from .compatibility_matrix_v1 import assess_compatibility


def run_soak_guard_v2(*, seeds: int=500, steps: int=200) -> dict[str,Any]:
    lab=UpdateFailureLabV3.campaign(seeds=seeds,steps=steps)
    forbidden=["arbitrary_shell","publication","installation","payment","real_trading"]
    forbidden_rejected=all(not validate_android_request(x)["allowed"] for x in forbidden)
    compatible=assess_compatibility({"data_schema":1,"package_contract":1,"sync_protocol":2},{"data_schema":1,"package_contract":1,"sync_protocol":2})["compatible"]
    unsafe_jump=assess_compatibility({"data_schema":1,"package_contract":1,"sync_protocol":2},{"data_schema":4,"package_contract":1,"sync_protocol":2})["compatible"]
    return {
        "ok":bool(lab["ok"] and forbidden_rejected and compatible and not unsafe_jump),
        "failure_lab":lab,"forbidden_android_capabilities_rejected":forbidden_rejected,
        "same_schema_compatible":compatible,"unsafe_schema_jump_rejected":not unsafe_jump,
        "automatic_publication":False,"automatic_installation":False,
    }
