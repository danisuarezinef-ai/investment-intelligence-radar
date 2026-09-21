from __future__ import annotations

from typing import Any


def build_executive_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    active=int(data.get("active_workers") or 0); target=int(data.get("target_workers") or 0)
    decisions=int(data.get("human_decisions") or 0); recovery=int(data.get("autonomous_recoveries") or 0)
    progress=max(0,min(float(data.get("progress_percent") or 0),100.0))
    if decisions: state="NECESITA TU DECISIÓN"
    elif recovery: state="RECUPERANDO"
    elif active: state="TRABAJANDO"
    else: state="EN ESPERA"
    attention = decisions > 0
    return {
        "schema_version":2,
        "hero":{"state":state,"goal":str(data.get("goal") or "Sin objetivo activo"),"progress_percent":round(progress,1)},
        "key_metrics":{
            "workers":f"{active}/{target}" if target else str(active),
            "eta_seconds":data.get("eta_seconds"),
            "completed":int(data.get("completed") or 0),
            "human_decisions":decisions,
        },
        "now":str(data.get("now") or "Sin tarea productiva activa"),
        "next":str(data.get("next") or "Sin siguiente tarea registrada"),
        "attention":{"required":attention,"count":decisions,"autonomous_recovery_count":recovery},
        "technical_details_collapsed":True,
    }
