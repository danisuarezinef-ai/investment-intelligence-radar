from __future__ import annotations

"""Dependency-light CEO Work Mode server.

This is a Windows resilience path for cases where FastAPI/Uvicorn are unavailable.
It deliberately uses only Python's stdlib for HTTP while reusing the existing CEO core.
No validation gates are re-run or bypassed.
"""

import asyncio
import getpass
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import shutil
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from ceo_core.version_identity import current_version
APP_VERSION = current_version()
from ceo_core.startup_diagnostics import StartupDiagnostics
from ceo_core.executive_snapshot_v2 import build_executive_snapshot

DIAGNOSTICS = StartupDiagnostics()
RESULTS = ROOT / "RESULTADOS_CEO"
RESULTS.mkdir(parents=True, exist_ok=True)
STATUS_PATH = ROOT / "CEO_REAL_WORK_INTERFACE_STATUS.json"
STATUS_COPY = RESULTS / "CEO_REAL_WORK_INTERFACE_STATUS.json"
FAILURE_PATH = ROOT / "CEO_STARTUP_FAILURE.txt"


def write_status(payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload.setdefault("production_verified", False)
    payload.setdefault("generated_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    for p in (STATUS_PATH, STATUS_COPY):
        try:
            p.write_text(text, encoding="utf-8")
        except Exception:
            pass
    try:
        DIAGNOSTICS.record(str(payload.get("status") or "UNKNOWN"), component="work-mode", **{k: v for k, v in payload.items() if k != "status"})
    except Exception:
        pass


def write_failure(exc: BaseException) -> None:
    text = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
    try:
        FAILURE_PATH.write_text(text, encoding="utf-8")
    except Exception:
        pass
    try:
        DIAGNOSTICS.exception(exc, component="work-mode")
    except Exception:
        pass
    write_status({"status": "BLOCKED", "error": str(exc), "diagnostic": str(FAILURE_PATH), "persistent_diagnostic": str(DIAGNOSTICS.latest_path)})


HTML = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CEO de IAs · Trabajo real</title><link rel="icon" href="/favicon.ico">
<style>
:root{font-family:Inter,Segoe UI,system-ui,sans-serif;background:#f3f5f8;color:#111827;--ink:#111827;--muted:#687386;--line:#e2e7ef;--soft:#f7f9fc;--blue:#2563eb;--cyan:#06b6d4;--violet:#7c3aed;--green:#15803d;--amber:#a16207;--red:#b42318}*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#eef3fa 0,#f7f8fb 220px,#f3f5f8 100%)}main{max-width:1180px;margin:auto;padding:20px 18px 60px}.top{display:flex;justify-content:space-between;gap:18px;align-items:center;margin-bottom:14px}.brand-wrap{display:flex;align-items:center;gap:11px}.brandmark{width:38px;height:38px;border-radius:12px;background:linear-gradient(145deg,#0f172a,#1e293b);position:relative;box-shadow:0 8px 25px rgba(15,23,42,.18)}.brandmark:before{content:"";position:absolute;inset:8px;border:4px solid #4de0ff;border-right-color:transparent;border-radius:50%}.brandmark:after{content:"";position:absolute;width:8px;height:8px;border-radius:50%;background:#8b5cf6;right:7px;top:7px}.brand{font-weight:900;letter-spacing:.11em}.version{font-size:11px;color:var(--muted);margin-top:2px}.status{font-size:13px;text-align:right}.status strong{display:inline-flex;align-items:center;padding:7px 11px;border-radius:999px;background:#fff;border:1px solid var(--line)}.status #provider{font-size:11px;color:var(--muted);margin-top:4px}.card{background:rgba(255,255,255,.94);border:1px solid var(--line);border-radius:20px;padding:18px;margin:12px 0;box-shadow:0 10px 35px rgba(35,48,73,.055)}.hero{padding:22px;background:linear-gradient(135deg,#fff 0,#f7fbff 65%,#f4f1ff 100%)}.hero-top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.eyebrow{font-size:11px;font-weight:800;letter-spacing:.13em;color:#526079;text-transform:uppercase}.goal-title{font-size:clamp(23px,3.5vw,38px);line-height:1.12;margin:7px 0 6px;max-width:830px}.goal-sub{color:var(--muted);font-size:13px}.state-chip{white-space:nowrap;font-size:12px;font-weight:800;border-radius:999px;padding:8px 11px;background:#e8f7ed;color:var(--green)}.executive-grid{display:grid;grid-template-columns:1.2fr repeat(3,1fr);gap:10px;margin-top:16px}.exec-metric{border:1px solid var(--line);background:#fff;border-radius:15px;padding:13px}.exec-metric b{display:block;font-size:24px;line-height:1}.exec-metric span{display:block;color:var(--muted);font-size:11px;margin-top:6px}.work-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}.workbox{background:var(--soft);border-radius:15px;padding:13px;min-height:105px}.workbox h3{font-size:13px;margin:0 0 8px}.section-head{display:flex;justify-content:space-between;gap:12px;align-items:center}h1{font-size:clamp(26px,4.5vw,44px);margin:8px 0 12px;line-height:1.06}h2{font-size:16px;margin:0 0 4px}.def{color:var(--muted);font-size:12px;margin-bottom:11px}textarea,input,select{width:100%;border:1px solid #d7dde7;border-radius:12px;padding:11px;font:inherit;background:#fff}textarea{min-height:105px;resize:vertical}.row{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}.metric{background:var(--soft);border-radius:13px;padding:12px}.metric b{display:block;font-size:22px}.metric span{font-size:11px;color:var(--muted)}button{border:0;border-radius:11px;padding:10px 15px;background:#111827;color:#fff;cursor:pointer;font-weight:700}button:hover{filter:brightness(1.06)}button:disabled{opacity:.5;cursor:default}button.secondary{background:#edf1f6;color:#1f2937}.safety{display:flex;gap:7px;flex-wrap:wrap}.pill{background:#edf7ef;border-radius:999px;padding:6px 10px;font-size:11px}.warn{background:#fff3d8}.queue{display:grid;gap:7px}.task{padding:9px 11px;background:var(--soft);border-radius:11px;display:flex;justify-content:space-between;gap:12px}.small{font-size:12px;color:var(--muted)}.project{padding:9px 0;border-bottom:1px solid #eee}.project:last-child{border-bottom:0}.error{background:#fff0ec;padding:10px;border-radius:12px;white-space:pre-wrap}.ok{color:var(--green)}.waiting{color:var(--amber)}.secret{display:flex;gap:8px;align-items:center;margin-top:12px}.secret input{flex:1}.active-goal{margin-top:10px;padding:10px 12px;background:var(--soft);border-radius:12px}.active-goal strong{display:block;margin-bottom:4px}.banner{margin-top:13px;padding:11px 13px;border-radius:12px;font-weight:700;font-size:13px}.banner.okb{background:#e8f7ed;color:var(--green)}.banner.warnb{background:#fff4db;color:#815b00}.banner.errb{background:#fff0ec;color:#8f2d1f}.banner.infob{background:#eaf4ff;color:#1d4f91}.live{background:#e8f7ed!important;color:var(--green)!important}.updatebox{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center}.update-actions{display:flex;gap:8px;flex-wrap:wrap}.update-status{padding:12px;background:var(--soft);border-radius:12px}.update-status strong{display:block;margin-bottom:3px}.ops-list{display:grid;gap:7px}.ops-item{padding:9px 10px;background:#fff;border:1px solid var(--line);border-radius:10px}.ops-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:#94a3b8}.ops-dot.working,.ops-dot.complete{background:#16a34a}.ops-dot.attention{background:#f59e0b}.ops-dot.planning{background:#3b82f6}.ops-dot.paused{background:#64748b}.ops-chart{width:100%;height:150px;background:#fff;border:1px solid var(--line);border-radius:10px;margin-top:8px}.ops-select{width:auto;min-width:150px;padding:7px 9px}.attention-card{background:#fff8e7;border:1px solid #eed69c;border-radius:12px;padding:12px;margin-top:8px}.attention-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:8px}.danger{background:#a32920!important}.controlbar{display:grid;grid-template-columns:1fr 1fr;gap:10px}.controlbox{background:var(--soft);border-radius:14px;padding:12px}.compact-details{margin:12px 0;background:#fff;border:1px solid var(--line);border-radius:16px;overflow:hidden}.compact-details>summary{cursor:pointer;padding:14px 16px;font-weight:800;list-style:none}.compact-details>summary::-webkit-details-marker{display:none}.compact-details>summary:after{content:"＋";float:right;color:#64748b}.compact-details[open]>summary:after{content:"−"}.details-body{border-top:1px solid var(--line);padding:14px 16px}.tech-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.human-attn-badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:800}.human-attn-badge.ok{color:var(--green)}.human-attn-badge.warn{color:var(--amber)}@media(max-width:800px){.executive-grid{grid-template-columns:1fr 1fr}.work-grid,.tech-grid,.controlbar{grid-template-columns:1fr}.grid{grid-template-columns:1fr 1fr}.top{align-items:flex-start}.status{text-align:left}.hero-top{display:block}.state-chip{display:inline-block;margin-top:8px}}@media(max-width:520px){.executive-grid{grid-template-columns:1fr 1fr}.exec-metric b{font-size:20px}}
</style></head>
<body><main>
<div class="top"><div class="brand-wrap"><div class="brandmark" aria-hidden="true"></div><div><div class="brand">CEO DE IAs</div><div class="version">Executive UX · actualización continua</div></div></div><div class="status"><strong id="op">Cargando…</strong><div id="provider"></div></div></div>
<section class="card hero"><div class="hero-top"><div><div class="eyebrow">Goal Engine</div><div id="heroGoal" class="goal-title">Preparando CEO…</div><div class="goal-sub" id="heroSub">Objetivo, estado y siguiente acción en una sola vista.</div></div><span id="opsHealth" class="state-chip">Cargando…</span></div><div id="actionBanner" class="banner warnb">Comprobando estado operativo…</div><div class="executive-grid"><div class="exec-metric"><b id="progress">0%</b><span>Progreso del objetivo</span></div><div class="exec-metric"><b id="running">0</b><span>Workers activos</span></div><div class="exec-metric"><b id="opsEta">—</b><span>Tiempo estimado</span></div><div class="exec-metric"><b id="heroAttention">0</b><span>Decisiones tuyas</span></div></div><div class="work-grid"><div class="workbox"><h3>Ahora</h3><div id="opsCurrent" class="ops-list"><span class="small">Sin trabajo activo.</span></div></div><div class="workbox"><h3>Siguiente</h3><div id="opsNext" class="ops-list"><span class="small">Sin siguiente tarea.</span></div></div></div></section>
<section id="attentionSection" class="card" style="display:none"><div class="section-head"><div><h2>Necesita tu decisión</h2><div class="def">Sólo acciones que CEO no puede decidir por sí solo.</div></div><span id="humanAttentionBadge" class="human-attn-badge warn">Pendiente</span></div><div id="attentionCards"><span class="small">Sin decisiones humanas pendientes.</span></div></section>
<section class="card"><div class="section-head"><div><h2>Control</h2><div class="def">Lo esencial para dirigir el trabajo sin entrar en detalles técnicos.</div></div><button class="secondary" onclick="refreshAll()">Actualizar vista</button></div><div id="activeGoal" class="active-goal" style="display:none"></div><div class="controlbar" style="margin-top:10px"><div class="controlbox"><div class="row" style="justify-content:space-between"><span>Potencia</span><strong id="powerLabel">30%</strong></div><input id="power" type="range" min="1" max="100" value="30" oninput="powerLabel.textContent=this.value+'%'" onchange="savePower()"><div id="deviceDetail" class="small" style="margin-top:6px"></div></div><div class="controlbox"><div class="row" style="justify-content:space-between"><span>Estado de IA</span><span id="execPill" class="pill warn">Comprobando…</span></div><div id="geminiDetail" class="small" style="margin-top:8px">Gemini todavía no validado.</div><div id="keyBox" class="secret"><input id="sessionKey" type="password" autocomplete="off" spellcheck="false" placeholder="Gemini API key para esta sesión"><button onclick="activateGemini()">Activar</button><button class="secondary" onclick="retryStoredGemini()">Reintentar guardada</button></div></div></div><div class="row" style="margin-top:10px"><button class="secondary" onclick="pauseProject()" id="pauseBtn">Pausar</button><button class="secondary" onclick="resumeProject()" id="resumeBtn">Reanudar</button><button class="danger" onclick="cancelProject()" id="cancelBtn">Cancelar objetivo</button><span id="progressDetail" class="small"></span></div></section>
<details class="compact-details"><summary>Nuevo objetivo o proyecto</summary><div class="details-body"><h2>¿Qué quieres que consiga CEO?</h2><div class="def">CEO descompone, prioriza y continúa sin esperar “sigue”.</div><textarea id="goal" placeholder="Escribe un objetivo real…"></textarea><input id="name" placeholder="Nombre del proyecto (opcional)" style="margin-top:9px"><div class="row" style="margin-top:10px"><button onclick="startNewProject()" id="startBtn">Empezar proyecto</button></div><div id="startStatus" class="small" style="margin-top:9px">Listo para crear un proyecto nuevo.</div></div></details>
<section class="card"><div class="section-head"><div><h2>Actualizaciones</h2><div class="def">Una sola acción: CEO descarga, verifica y prepara; tú confirmas la instalación.</div></div><button class="secondary" style="padding:7px 11px" onclick="toggleUpdateInfo()" title="Información avanzada">i</button></div><div class="updatebox"><div class="update-status"><strong id="updateHeadline">Comprobando actualizaciones…</strong><div id="updateDetail" class="small"></div><div id="updateProgress" class="update-progress"><div id="updateProgressBar"></div></div><div id="updateProgressMeta" class="update-progress-meta"><span id="updatePhase">—</span><span id="updatePercent">0%</span></div></div><div class="update-actions"><button id="oneClickUpdateBtn" onclick="oneClickUpdate()" disabled>CEO está al día</button></div></div><div id="updateInfo" style="display:none;margin-top:10px"><div class="small" style="margin-bottom:8px">CEO comprueba el canal interno, verifica firma Ed25519, SHA-256, contrato y compatibilidad; conserva la versión anterior y puede volver atrás si la nueva no arranca correctamente. Las firmas y la publicación del canal no requieren acciones manuales del usuario.</div><input id="updateManifest" placeholder="Canal HTTPS de actualizaciones (manifest.json)"><div class="update-actions" style="margin-top:8px"><button class="secondary" onclick="saveUpdateChannel()">Guardar canal</button><button class="secondary" onclick="checkUpdate()">Comprobar ahora</button></div></div></section>
<details class="compact-details"><summary>Actividad técnica y evolución</summary><div class="details-body"><div class="executive-grid" style="grid-template-columns:repeat(3,1fr);margin-top:0"><div class="exec-metric"><b id="opsThroughput">—</b><span>tareas/h equivalentes</span></div><div class="exec-metric"><b id="opsTarget">—</b><span>workers objetivo</span></div><div class="exec-metric"><b id="done">0</b><span>completadas reales</span></div><div class="exec-metric"><b id="pending">0</b><span>pendientes reales</span></div><div class="exec-metric"><b id="opsRecoveries">0</b><span>recuperaciones</span></div><div class="exec-metric"><b id="opsCorrections">0</b><span>autocorrecciones</span></div></div><div class="tech-grid" style="margin-top:12px"><div><h2>Últimos eventos</h2><div id="opsTimeline" class="ops-list"><span class="small">Sin eventos todavía.</span></div><div id="opsAttention" class="small" style="margin-top:9px"></div></div><div><div class="row" style="justify-content:space-between"><h2>Evolución</h2><select id="opsMetric" class="ops-select" onchange="drawOpsChart(lastOps)"><option value="completed">Completadas</option><option value="failures">Fallos</option><option value="recoveries">Recuperaciones</option><option value="quality">Calidad</option></select></div><canvas id="opsChart" class="ops-chart" width="520" height="150"></canvas><div id="opsLedger" class="small" style="margin-top:6px"></div><div class="small" style="margin-top:6px">Reinicios automáticos: <strong id="opsRestarts">0</strong></div></div></div></div></details>
<details class="compact-details"><summary>Cola de trabajo</summary><div class="details-body"><div id="queue" class="queue"><span class="small">Sin cola todavía.</span></div></div></details>
<details class="compact-details"><summary>Seguridad</summary><div class="details-body"><div class="safety"><span class="pill">✓ Sin auto-promoción</span><span class="pill">✓ Git remoto bloqueado</span><span class="pill">✓ Sin compras automáticas</span><span class="pill">✓ Destructivas con gate humano</span></div></div></details>
<details class="compact-details"><summary>Proyectos</summary><div class="details-body"><div id="projects"><span class="small">Cargando…</span></div></div></details>
<details class="compact-details"><summary>Diagnóstico</summary><div class="details-body"><div id="diag" class="small">Interfaz activa.</div></div></details>
</main>
<script>
const $=id=>document.getElementById(id);let state=null;
async function j(url,opt){const r=await fetch(url,opt);const x=await r.json();if(!r.ok)throw new Error(x.error||('HTTP '+r.status));return x}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
let draftDirty=false;
function fmtDuration(sec){sec=Number(sec||0);if(!isFinite(sec)||sec<=0)return '—';if(sec<60)return Math.round(sec)+' s';if(sec<3600)return Math.round(sec/60)+' min';const h=Math.floor(sec/3600),m=Math.round((sec%3600)/60);return h+' h '+m+' min'}
let lastOps=null;
let humanAttentionCount=0;
function drawOpsChart(o){o=o||lastOps||{};lastOps=o;const d=o.dashboard||{},metric=$('opsMetric')?.value||'completed',vals=(d.series||{})[metric]||[],c=$('opsChart');if(!c)return;const ctx=c.getContext('2d'),w=c.width,h=c.height;ctx.clearRect(0,0,w,h);ctx.strokeStyle='#deded8';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(30,10);ctx.lineTo(30,h-24);ctx.lineTo(w-8,h-24);ctx.stroke();const usable=vals.map(v=>v==null?null:+v),numbers=usable.filter(v=>v!=null&&Number.isFinite(v));if(!numbers.length){ctx.fillStyle='#777';ctx.font='12px Segoe UI';ctx.fillText('Sin datos suficientes',42,75);return}let min=Math.min(...numbers),max=Math.max(...numbers);if(metric!=='quality')min=Math.min(0,min);if(max===min)max=min+1;const x=i=>30+(w-42)*(i/Math.max(1,usable.length-1));const y=v=>(h-24)-((v-min)/(max-min))*(h-40);ctx.strokeStyle='#171717';ctx.lineWidth=2;ctx.beginPath();let started=false;usable.forEach((v,i)=>{if(v==null||!Number.isFinite(v)){started=false;return}const xx=x(i),yy=y(v);if(!started){ctx.moveTo(xx,yy);started=true}else ctx.lineTo(xx,yy)});ctx.stroke();ctx.fillStyle='#666';ctx.font='10px Segoe UI';ctx.fillText(String(max.toFixed(metric==='quality'?2:0)),2,14);ctx.fillText(String(min.toFixed(metric==='quality'?2:0)),2,h-24)}
function renderAttention(cards){cards=cards||[];humanAttentionCount=cards.length;const box=$('attentionCards'),section=$('attentionSection'),badge=$('humanAttentionBadge'),hero=$('heroAttention');if(hero)hero.textContent=String(cards.length);if(section)section.style.display=cards.length?'block':'none';if(badge){badge.textContent=cards.length?(cards.length+' pendiente'+(cards.length===1?'':'s')):'Sin decisiones';badge.className='human-attn-badge '+(cards.length?'warn':'ok')}if(!box)return;box.innerHTML=cards.length?cards.map(c=>`<div class="attention-card"><strong>${esc(c.title||'Decisión')}</strong><div class="small" style="margin-top:4px">${esc(c.body||'')}</div><div class="attention-actions"><button onclick="attentionAction('${esc(c.id)}','approve')">Aprobar</button><button class="secondary" onclick="attentionAction('${esc(c.id)}','postpone')">Posponer</button><button class="danger" onclick="attentionAction('${esc(c.id)}','reject')">Rechazar</button></div></div>`).join(''):'<span class="small">Sin decisiones humanas pendientes.</span>'}
async function attentionAction(id,action){if((action==='approve'||action==='reject')&&!confirm(action==='approve'?'¿Aprobar esta acción una sola vez?':'¿Rechazar esta acción?'))return;try{render(await j('/api/attention/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,action})}))}catch(e){$('diag').innerHTML='<div class="error">'+esc(e.message)+'</div>'}}
function eventLabel(kind){const m={provider_selected:'Proveedor seleccionado',provider_executing:'Proveedor ejecutando',provider_returned:'Resultado recibido',task_started:'Tarea iniciada',task_complete:'Tarea completada',verification_verdict:'Verificación independiente',recovery_started:'Recuperación automática',recovery_complete:'Recuperación completada',quality_retry:'Autocorrección',decision_created:'Decisión requerida'};return m[kind]||String(kind||'Evento').replaceAll('_',' ')}
function stageLabel(stage){const m={executing:'trabajando',returned:'resultado recibido',running:'trabajando',pending:'pendiente',retry:'reintentando',complete:'completada',completed:'completada',needs_review:'revisión'};return m[String(stage||'').toLowerCase()]||String(stage||'trabajando').replaceAll('_',' ')}
function renderObservability(o){o=o||{};lastOps=o;const h=o.health||{};const rawLevel=h.level||'idle';const level=(rawLevel==='attention'&&humanAttentionCount===0)?'planning':rawLevel;const labels={working:'TRABAJANDO',planning:(rawLevel==='attention'?'RECUPERANDO':'PLANIFICANDO'),stalled:'ATASCADO',waiting_provider:'ESPERANDO PROVEEDOR',attention:'TE NECESITA',complete:'COMPLETADO',paused:'PAUSADO',idle:'EN ESPERA'};const health=$('opsHealth');if(health){health.innerHTML='<span class="ops-dot '+esc(level)+'"></span>'+esc(labels[level]||String(level).toUpperCase());health.className='state-chip'}const tp=o.throughput||{};$('opsThroughput').textContent=tp.tasks_per_hour_equivalent==null?'—':tp.tasks_per_hour_equivalent;$('opsEta').textContent=fmtDuration(o.eta?.seconds);$('opsRestarts').textContent=o.scheduler?.auto_restarts??0;const rz=o.resilience||{},pt=o.productive_truth||{};$('opsTarget').textContent=rz.adaptive_scheduler?.target??'—';$('opsRecoveries').textContent=pt.worker_recoveries??rz.worker_recoveries??0;const gv=o.governance||{};$('opsCorrections').textContent=gv.self_corrections??0;const cur=o.current_work||[];$('opsCurrent').innerHTML=cur.length?cur.slice(0,3).map(x=>`<div class="ops-item"><strong>${esc(x.title)}</strong><div class="small">${esc(x.provider||'IA')} · ${esc(stageLabel(x.stage))} · ${fmtDuration(x.elapsed_seconds)}</div></div>`).join(''):'<span class="small">Sin trabajo productivo activo en este instante.</span>';const nx=o.next_work||[];$('opsNext').innerHTML=nx.length?nx.slice(0,3).map(x=>`<div class="ops-item"><strong>${esc(x.title)}</strong><div class="small">${esc(stageLabel(x.status))}${x.priority!=null?' · prioridad '+x.priority:''}</div></div>`).join(''):'<span class="small">CEO decidirá el siguiente paso cuando termine la tarea actual.</span>';const tl=o.timeline||[];$('opsTimeline').innerHTML=tl.length?tl.slice(0,8).map(x=>`<div class="ops-item"><strong>${esc(eventLabel(x.kind))}</strong><div class="small">${esc(x.title||'')}${x.provider?' · '+esc(x.provider):''}</div>${x.detail?`<div class="small">${esc(x.detail)}</div>`:''}</div>`).join(''):'<span class="small">Sin eventos todavía.</span>';const att=o.attention||[],stale=o.stale_workers||[];const dh=gv.dependency_health||{};const depIssues=(dh.missing||0)+(dh.failed_hard||0)+(dh.cycles||0);const automaticIssues=att.length+stale.length+depIssues;const attBox=$('opsAttention');if(humanAttentionCount>0){attBox.textContent='Hay '+humanAttentionCount+' decisión(es) que requieren tu intervención.'}else if(rawLevel==='waiting_provider'){attBox.textContent='Proveedor temporalmente no disponible. CEO mantiene el scheduler local y reintentará sin consumir recuperaciones.'}else if(rawLevel==='stalled'){attBox.textContent='CEO detectó producción nula: está cambiando de estrategia; actividad de proveedor no cuenta como progreso.'}else if(automaticIssues>0||rawLevel==='attention'){attBox.textContent='CEO está resolviendo '+Math.max(1,automaticIssues)+' incidencia(s) automáticamente. No requiere acción tuya ahora.'}else{attBox.textContent='Sin incidencias activas.'}const led=o.evidence_ledger||{};$('opsLedger').textContent='Registro de evidencia: '+(led.valid===false?'integridad comprometida':'integridad correcta')+' · '+(led.entries??0)+' eventos';drawOpsChart(o)}
$('goal').addEventListener('input',()=>{draftDirty=true});
$('name').addEventListener('input',()=>{draftDirty=true});
function render(s){
state=s;const live=!!s.execution_enabled;const real=s.operational_status||'SIN PROYECTO';const schedulerAlive=!!s.scheduler_alive;
const working=!!(s.active&&live&&schedulerAlive&&['TRABAJANDO','PLANIFICANDO','VERIFICANDO','CORRIGIENDO'].includes(real));
$('op').textContent=s.active?real:'SIN PROYECTO';$('op').style.color=working?'#176d2d':(['BLOQUEADO','SIN SCHEDULER'].includes(real)?'#8b2f1f':'#7a5600');
const keyRecognized=!!s.gemini_key_recognized;const keyStatus=String(s.gemini_key_status||'');
const browserReady=!!s.browser_provider_ready;
$('provider').textContent=(browserReady?'ChatGPT web · Chrome':(live?'IA conectada':'IA web no disponible'))+(schedulerAlive?' · motor activo':' · motor detenido');
$('execPill').textContent=browserReady?'✓ IA WEB preparada · sin API requerida':(live?'✓ IA conectada':'⚠ IA web no disponible');$('execPill').className='pill '+((browserReady||live)?'live':'warn');$('keyBox').style.display='none';
const geminiFailed=!live&&s.provider_mode==='gemini-validation-failed';const geminiErr=String(s.gemini_validation_error||'').slice(0,620);
const transportProblem=/ConnectError|Timeout|NETWORK|TRANSPORT|UNAVAILABLE/i.test(geminiErr+' '+keyStatus);$('geminiDetail').textContent=live?('Conexión Gemini verificada'+(s.gemini_model?' · modelo '+s.gemini_model:'')+'.'):(keyRecognized?('✓ Clave autenticada y guardada. '+(transportProblem?'Conexión con Gemini temporalmente no disponible.':'Gemini no permite generar ahora.')+' CEO reintentará automáticamente; no necesitas crear otra clave. '+geminiErr):(geminiFailed?('Clave rechazada o no autenticada. '+geminiErr):('No se pudo verificar Gemini en este momento. CEO conserva la clave cifrada y reintentará.')));
$('progress').textContent=(s.metrics?.progress??0)+'%';$('running').textContent=s.metrics?.running??0;$('done').textContent=s.metrics?.completed??0;$('pending').textContent=s.metrics?.pending??0;const bp=s.metrics?.batch_progress??0;const cr=s.metrics?.control_running??0;const cp=s.metrics?.control_pending??0;const cc=s.metrics?.control_completed??0;const last=s.metrics?.last_productive_progress_at||'todavía sin avance productivo registrado';$('progressDetail').textContent='Lote conocido: '+bp+'% · control interno: '+cr+' ejecutando, '+cp+' pendiente(s), '+cc+' completada(s) · último avance real: '+last;const dp=s.device_fabric?.plan?.changes||[];const nt=s.device_fabric?.notification_target||{};$('deviceDetail').textContent='Reparto por dispositivo activo. Potencia '+(s.power_percent??30)+'% · cambios de asignación en este balance: '+dp.length+' · notificaciones de decisión fijadas al móvil'+(nt.device_id?' ('+nt.device_id+')':' cuando esté conectado')+'.';
renderAttention(s.attention_cards||[]);renderObservability(s.observability);
$('power').value=s.power_percent??30;$('powerLabel').textContent=$('power').value+'%';const hasActive=!!s.active;$('pauseBtn').disabled=!hasActive||!!s.paused;$('resumeBtn').disabled=!hasActive||!s.paused||!live;$('cancelBtn').disabled=!hasActive;$('startBtn').disabled=!live;$('startBtn').title=live?'Iniciar trabajo real con IA web':'CEO necesita Chrome/Edge disponible; no requiere API';
if(s.active&&s.goal){$('activeGoal').style.display='block';$('activeGoal').innerHTML='<strong>Objetivo activo</strong><div class="small">'+esc(s.goal)+'</div>'}else{$('activeGoal').style.display='none'}
const heroGoal=$('heroGoal'),heroSub=$('heroSub');if(heroGoal)heroGoal.textContent=(s.active&&s.goal)?s.goal:'Sin objetivo activo';if(heroSub)heroSub.textContent=s.active?('CEO continúa de forma autónoma · '+real):'Crea o reanuda un proyecto para empezar.';
const q=s.queue||[];$('queue').innerHTML=q.length?q.map(t=>`<div class="task"><div><strong>${esc(t.title)}</strong><div class="small">${esc(t.status)} · prioridad ${t.priority??0}${(t.dependencies||[]).length?' · deps '+t.dependencies.length:''}</div></div><span class="small">${esc(t.provider||'')}</span></div>`).join(''):'<span class="small">No hay tareas en cola.</span>';
if(s.active&&real==='CORRIGIENDO'){$('actionBanner').className='banner warnb';$('actionBanner').textContent='⚠ CEO detectó un atasco productivo y está cambiando de estrategia. Los reintentos no cuentan como progreso hasta producir una salida útil.'}
else if(working){$('actionBanner').className='banner okb';$('actionBanner').textContent='✓ CEO está ejecutando trabajo productivo. Estado real: '+real+'.'}
else if(s.active&&s.paused){$('actionBanner').className='banner warnb';$('actionBanner').textContent='Proyecto PAUSADO; no está ejecutando tareas.'}
else if(s.work_complete_certified&&s.completion_phase==='work_complete_pending_certification'){$('actionBanner').className='banner infob';$('actionBanner').textContent='✓ Trabajo del objetivo completado con evidencia determinista. Solo queda la certificación de resistencia en Windows; CEO no gastará llamadas IA ni creará nuevas auditorías mientras espera.'}
else if(!live){$('actionBanner').className='banner warnb';$('actionBanner').textContent='La IA web no está disponible. Comprueba Chrome/Edge y la sesión de ChatGPT.'}
else if(s.active&&real==='NECESITA DECISIÓN'){$('actionBanner').className='banner errb';$('actionBanner').textContent='✗ Hay una tarea humana en NEEDS_REVIEW. Si es una auditoría interna de continuidad, CEO debe recuperarla solo; no requiere tu decisión. En DEV15 esas auditorías son atómicas y no deben quedar aquí.'}
else if(s.active&&real==='BLOQUEADO'){const bs=s.autonomy_stalled?.blockers||[];const blocked=(s.queue||[]).filter(t=>['blocked','failed','needs_review'].includes(t.status)).slice(0,3).map(t=>t.title+' ['+t.status+']');const why=(bs.length?bs:blocked);const explicit=s.operator_block_reason||s.metadata?.operator_block_reason||'';$('actionBanner').className='banner errb';$('actionBanner').textContent='✗ CEO está BLOQUEADO. Causa: '+(why.length?why.join(' · '):(explicit||'bloqueo sin causa estructurada; requiere diagnóstico'))}
else if(s.goal_audit_rejection||s.goal_audit_invalidated){$('actionBanner').className='banner warnb';$('actionBanner').textContent='⚠ Cierre rechazado por evidencia insuficiente. CEO debe continuar hasta reunir prueba independiente.'}
else if(s.active&&real==='COMPLETADO'){$('actionBanner').className='banner okb';$('actionBanner').textContent='✓ Objetivo completado con evidencia independiente y auditoría estricta.'}
else if(s.field_endurance_required&&!s.field_endurance_certified){$('actionBanner').className='banner infob';$('actionBanner').textContent='ℹ Certificación de resistencia pendiente. El trabajo productivo puede continuar; cuando todo el trabajo quede probado, CEO esperará esta certificación sin consumir proveedor IA.'}
else if(s.active){$('actionBanner').className='banner warnb';$('actionBanner').textContent='⚠ CEO no tiene trabajo ejecutándose ahora: '+real+'. El watchdog debe replanificar si el objetivo sigue incompleto.'}
else{$('actionBanner').className='banner okb';$('actionBanner').textContent='✓ CEO puede trabajar mediante IA web en Chrome sin depender de API.'}
const wd=s.watchdog?.status?(' · watchdog '+s.watchdog.status):'';const gen=s.goal_continuity_generation?(' · ciclos de continuidad '+s.goal_continuity_generation):'';const sup=(s.metrics?.superseded??0)?(' · supersedidas '+s.metrics.superseded):'';const dup=s.continuity_duplicate_spawn_drops?(' · follow-ups duplicados descartados '+s.continuity_duplicate_spawn_drops):'';
const stall=s.autonomy_stalled?(' · bloqueo '+esc(JSON.stringify(s.autonomy_stalled).slice(0,700))):'';$('diag').textContent=(s.message||'Servidor local activo.')+wd+gen+sup+dup+(s.scheduler_error?' · '+s.scheduler_error:'')+stall;
}
async function refresh(){try{render(await j('/api/state'))}catch(e){$('diag').innerHTML='<div class="error">'+esc(e.message)+'</div>'}}
let updateState=null;let updateActionBusy=false;
function toggleUpdateInfo(){const x=$('updateInfo');x.style.display=x.style.display==='none'?'block':'none'}
function setUpdateButton(label,enabled,version=''){const b=$('oneClickUpdateBtn');b.textContent=label;b.disabled=!enabled;if(version)b.dataset.version=version;else delete b.dataset.version}
let updateProgressTimer=null;let updateProgressStarted=0;
function showUpdateProgress(percent,phase,detail=''){const wrap=$('updateProgress'),meta=$('updateProgressMeta'),bar=$('updateProgressBar');wrap.style.display='block';meta.style.display='flex';const p=Math.max(0,Math.min(100,Number(percent)||0));bar.style.width=p+'%';$('updatePercent').textContent=Math.round(p)+'%';$('updatePhase').textContent=phase||'Procesando';if(detail)$('updateDetail').textContent=detail}
function stopUpdateProgress(){if(updateProgressTimer){clearInterval(updateProgressTimer);updateProgressTimer=null}}
async function pollUpdateProgress(){try{const p=await j('/api/update/progress');const phase=String(p.phase||'').toLowerCase();const labels={downloading:'Descargando',downloaded:'Descarga completa',verifying:'Verificando firma e integridad',extracting:'Preparando versión',ready_to_install:'Lista para instalar',preflight:'Probando nueva versión sin activarla',preflight_ok:'Prueba previa superada',activating:'Activando',waiting_old_process:'Cerrando versión anterior',launching_new_version:'Arrancando nueva versión',health_check:'Comprobando salud',healthy:'Actualización completada',rollback:'Revirtiendo',rolled_back:'Versión anterior restaurada'};let percent=Number(p.percent);if(!Number.isFinite(percent)){percent=phase==='verifying'?78:phase==='extracting'?86:phase==='ready_to_install'?100:0}let detail='';if(p.bytes_expected>0)detail='Descargados '+Math.round((p.bytes_downloaded||0)/1024)+' KB de '+Math.round(p.bytes_expected/1024)+' KB';showUpdateProgress(percent,labels[phase]||phase||'Procesando',detail);if(phase==='ready_to_install'&&!updateActionBusy){stopUpdateProgress();$('updateHeadline').textContent='Actualización lista para instalar';$('updateDetail').textContent='Descarga, firma e integridad verificadas.';setUpdateButton('Instalar y reiniciar',true,String(p.version||''))}}catch(e){}}
function startUpdateProgress(){stopUpdateProgress();updateProgressStarted=Date.now();pollUpdateProgress();updateProgressTimer=setInterval(pollUpdateProgress,400)}
async function updateStatus(remote=false){try{const u=await j('/api/update/status'+(remote?'?remote=1':''));updateState=u;$('updateManifest').value=u.manifest_url||$('updateManifest').value||'';const installable=(u.staged||[]).find(x=>!x.installed&&!x.rolled_back&&!x.preflight_failed);const remoteVersion=String(u.remote?.version||'');const stalePrepared=!!(installable&&u.available&&remoteVersion&&remoteVersion!==String(installable.version||''));if(u.error){$('updateHeadline').textContent='No se pudo comprobar la actualización';$('updateDetail').textContent=u.error;setUpdateButton('Reintentar comprobación',true)}else if(stalePrepared){$('updateHeadline').textContent='Hay una versión más nueva';$('updateDetail').textContent='La versión preparada '+installable.version+' quedó obsoleta. CEO preparará '+remoteVersion+' en su lugar.';setUpdateButton('Preparar '+remoteVersion,true,remoteVersion)}else if(installable){$('updateHeadline').textContent='Actualización lista para instalar';$('updateDetail').textContent=installable.version+' ya está descargada y verificada.';setUpdateButton('Instalar y reiniciar',true,installable.version)}else if(u.available){$('updateHeadline').textContent='Nueva versión disponible';$('updateDetail').textContent=(u.remote.notes||u.remote.version)+' · versión actual '+u.current_version;setUpdateButton('Actualizar CEO',true,u.remote.version)}else if(!u.configured){$('updateHeadline').textContent='Canal de actualización no disponible';$('updateDetail').textContent='Abre la información (i) sólo si necesitas configurar el canal manualmente.';setUpdateButton('Comprobar de nuevo',true)}else if(remote){$('updateHeadline').textContent='CEO está al día';$('updateDetail').textContent='Versión '+u.current_version;setUpdateButton('CEO está al día',false)}else{$('updateHeadline').textContent='Actualizaciones preparadas';$('updateDetail').textContent='CEO comprobará el canal automáticamente.';setUpdateButton('Comprobar ahora',true)}return u}catch(e){$('updateHeadline').textContent='Error al comprobar actualizaciones';$('updateDetail').textContent=e.message;setUpdateButton('Reintentar',true);return null}}
async function saveUpdateChannel(){const url=$('updateManifest').value.trim();try{await j('/api/update/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({manifest_url:url,channel:'stable',auto_check:true})});$('updateHeadline').textContent='Canal guardado';$('updateDetail').textContent='Comprobando canal…';await updateStatus(true)}catch(e){$('updateDetail').textContent=e.message}}
async function checkUpdate(){setUpdateButton('Comprobando…',false);$('updateHeadline').textContent='Comprobando actualizaciones…';await updateStatus(true)}
async function waitForRestart(expectedVersion){stopUpdateProgress();updateProgressTimer=setInterval(async()=>{try{const p=await j('/api/update/progress');const phase=String(p.phase||'');const pct=Number.isFinite(Number(p.percent))?Number(p.percent):0;showUpdateProgress(pct,phase||'Reiniciando',p.reason||'');if(phase==='healthy'){stopUpdateProgress();$('updateHeadline').textContent='Actualización completada';$('updateDetail').textContent='CEO '+expectedVersion+' está sano. Recargando interfaz…';setTimeout(()=>location.reload(),700)}else if(phase==='rolled_back'){stopUpdateProgress();$('updateHeadline').textContent='La actualización no arrancó';$('updateDetail').textContent='CEO restauró automáticamente la versión anterior: '+(p.reason||'motivo no disponible');setUpdateButton('Comprobar una versión nueva',true)}}catch(e){$('updateHeadline').textContent='Reiniciando CEO…';$('updateDetail').textContent='La interfaz espera a que el backend vuelva a estar disponible. No cierres esta ventana.'}},700)}
async function oneClickUpdate(){if(updateActionBusy)return;const b=$('oneClickUpdateBtn');if(!updateState||(!updateState.available&&!(updateState.staged||[]).some(x=>!x.installed&&!x.rolled_back))){return checkUpdate()}updateActionBusy=true;try{let installable=(updateState.staged||[]).find(x=>!x.installed&&!x.rolled_back&&!x.preflight_failed&&(!updateState.available||!updateState.remote?.version||String(x.version)===String(updateState.remote.version)));if(!installable){setUpdateButton('Descargando y verificando…',false);$('updateHeadline').textContent='Preparando actualización…';startUpdateProgress();$('updateDetail').textContent='CEO comprueba firma, integridad y compatibilidad. La versión actual sigue intacta.';const r=await j('/api/update/stage',{method:'POST'});if(r.available===false){stopUpdateProgress();updateActionBusy=false;return await updateStatus(true)}stopUpdateProgress();showUpdateProgress(100,'Lista para instalar','Descarga y verificaciones completadas.');installable=(r&&r.receipt&&!r.receipt.installed&&!r.receipt.rolled_back&&!r.receipt.preflight_failed)?r.receipt:null;if(installable){updateState=updateState||{};updateState.staged=[installable,...((updateState.staged||[]).filter(x=>String(x.version||'')!==String(installable.version||'')))];$('updateHeadline').textContent='Actualización lista para instalar';$('updateDetail').textContent=installable.version+' ya está descargada y verificada.';setUpdateButton('Instalar y reiniciar',true,installable.version)}else{const refreshed=await updateStatus(false);installable=(refreshed?.staged||[]).find(x=>!x.installed&&!x.rolled_back&&!x.preflight_failed)}}if(!installable)throw new Error('La actualización no quedó preparada para instalar.');const version=installable.version;const ok=confirm('CEO '+version+' está verificado y listo.\n\n¿Instalar y reiniciar ahora?\n\nAntes de cerrar la versión actual, CEO hará una prueba real de arranque de la nueva versión en un entorno aislado.');if(!ok){updateActionBusy=false;$('updateHeadline').textContent='Actualización preparada';$('updateDetail').textContent='Queda lista. Puedes instalarla cuando quieras con el mismo botón.';setUpdateButton('Instalar y reiniciar',true,version);return}setUpdateButton('Probando nueva versión…',false);$('updateHeadline').textContent='Prueba previa de '+version+'…';showUpdateProgress(5,'Prueba previa','La versión actual seguirá funcionando hasta que la candidata demuestre que puede arrancar.');const r=await j('/api/update/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version,confirm:true})});$('updateHeadline').textContent='Reiniciando '+version+'…';$('updateDetail').textContent='Prueba previa superada. CEO cambiará de versión y verificará salud automáticamente.';showUpdateProgress(25,'Reiniciando','Puedes dejar esta ventana abierta; mostrará el resultado del relevo.');waitForRestart(version)}catch(e){stopUpdateProgress();const msg=e.message;await updateStatus(false);$('updateHeadline').textContent='No se pudo actualizar';$('updateDetail').textContent=msg;setUpdateButton('Reintentar actualización',true)}finally{updateActionBusy=false}}
async function projects(){try{const a=await j('/api/projects');$('projects').innerHTML=a.length?a.map(p=>`<div class="project"><div class="row" style="justify-content:space-between"><div><strong>${esc(p.name||p.goal||'Proyecto')}</strong><div class="small">avance ${p.progress??0}% · lote ${p.batch_progress??0}% · ${p.productive_completed??0} completadas reales${p.active?' · activo':''}${p.paused?' · pausado':''}${p.portfolio?(' · cartera #'+p.portfolio.rank+' · '+p.portfolio.slots+' slot'+(p.portfolio.slots===1?'':'s')):''}</div></div>${p.active?'':(p.cancelled_at?'<span class="pill warn">cancelado</span>':`<button class="secondary" onclick="activateProject('${esc(p.id)}')">Reanudar este proyecto</button>`) }</div></div>`).join(''):'<span class="small">No hay proyectos.</span>'}catch(e){}}
async function activateProject(id){try{$('actionBanner').className='banner warnb';$('actionBanner').textContent='Cambiando al proyecto seleccionado…';const s=await j('/api/project/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:id})});render(s);projects()}catch(e){$('diag').innerHTML='<div class="error">'+esc(e.message)+'</div>'}}
async function startNewProject(){const goal=$('goal').value.trim();const name=$('name').value.trim()||null;const status=$('startStatus');if(!state?.execution_enabled){$('actionBanner').className='banner errb';$('actionBanner').textContent='No iniciado: la IA web no está disponible en Chrome/Edge.';if(status)status.textContent='Browser AI Worker no disponible.';return}if(goal.length<3){if(status)status.textContent='Escribe un objetivo de al menos 3 caracteres.';return}let slow=setTimeout(()=>{if(status)status.textContent='Cerrando de forma segura el proyecto anterior y preparando el nuevo…';},1800);try{$('startBtn').disabled=true;if(status)status.textContent='Preparando el nuevo objetivo…';$('actionBanner').className='banner warnb';$('actionBanner').textContent='Iniciando proyecto nuevo…';const s=await j('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({goal,name,power_percent:+$('power').value})});clearTimeout(slow);draftDirty=false;$('goal').value='';$('name').value='';if(status)status.textContent='✓ Proyecto nuevo activo: '+(s.project_name||s.goal||'creado');render(s);await projects();setTimeout(refreshAll,700)}catch(e){clearTimeout(slow);$('startBtn').disabled=false;if(status)status.textContent='ERROR: '+e.message;$('actionBanner').className='banner errb';$('actionBanner').textContent='No se pudo iniciar: '+e.message;$('diag').innerHTML='<div class="error">'+esc(e.message)+'</div>'}}
async function pauseProject(){try{render(await j('/api/pause',{method:'POST'}))}catch(e){$('actionBanner').className='banner errb';$('actionBanner').textContent='No se pudo pausar: '+e.message}}
async function resumeProject(){try{render(await j('/api/resume',{method:'POST'}))}catch(e){$('actionBanner').className='banner errb';$('actionBanner').textContent='No se pudo reanudar: '+e.message}}
async function cancelProject(){if(!state?.active)return;const ok=confirm('Cancelar este objetivo detendrá su scheduler y retirará definitivamente sus tareas pendientes. El proyecto se conservará como cancelado para auditoría.\n\n¿Cancelar objetivo?');if(!ok)return;try{const s=await j('/api/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true})});render(s);await projects();$('actionBanner').className='banner warnb';$('actionBanner').textContent='Objetivo cancelado. No se reanudará automáticamente.'}catch(e){$('actionBanner').className='banner errb';$('actionBanner').textContent='No se pudo cancelar: '+e.message}}
async function savePower(){try{render(await j('/api/power',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({power_percent:+$('power').value})}))}catch(e){}}
async function activateGemini(){const key=$('sessionKey').value.trim();if(!key){$('geminiDetail').textContent='Pega la clave Gemini en el campo de sesión.';return}try{$('geminiDetail').textContent='Probando la nueva clave con Google…';const s=await j('/api/session-key',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key})});$('sessionKey').value='';render(s);if(s.execution_enabled){$('geminiDetail').textContent='✓ Nueva clave validada y activa'+(s.gemini_model?' · '+s.gemini_model:'')+'.'}else if(s.gemini_key_recognized){$('geminiDetail').textContent='✓ Nueva clave reconocida y guardada. Ejecución bloqueada: '+(s.gemini_key_status||'sin cuota/modelo disponible')+'. Pulsa “Reintentar guardada” más tarde.'}else{$('geminiDetail').textContent='✗ La nueva clave no pudo autenticarse.'}}catch(e){$('geminiDetail').textContent='✗ Nueva clave rechazada/no autenticada: '+e.message;$('diag').innerHTML='<div class="error">'+esc(e.message)+'</div>'}}
async function retryStoredGemini(){try{$('geminiDetail').textContent='Reintentando la clave cifrada guardada…';const s=await j('/api/session-key/revalidate',{method:'POST'});render(s);if(s.execution_enabled){$('geminiDetail').textContent='✓ Gemini validado y activo'+(s.gemini_model?' · '+s.gemini_model:'')+'.'}else if(s.gemini_key_recognized){$('geminiDetail').textContent='✓ Clave autenticada. Proveedor temporalmente en espera; CEO reintentará solo.'}else{$('geminiDetail').textContent='✗ La clave guardada no pudo autenticarse.'}}catch(e){$('geminiDetail').textContent='✗ Reintento Gemini fallido: '+e.message;$('diag').innerHTML='<div class="error">'+esc(e.message)+'</div>'}}
async function refreshAll(){await refresh();await projects()}setInterval(refresh,1200);refreshAll();updateStatus(false).then(u=>{if(u&&u.configured&&u.auto_check)setTimeout(()=>updateStatus(true),1200)});setInterval(()=>{if(updateState?.configured&&updateState?.auto_check)updateStatus(true)},6*60*60*1000);
</script></body></html>'''


class CEOEngine:
    def __init__(self, gemini_key: str | None):
        # Core imports are intentionally delayed so startup failures are always logged
        # next to the launcher, even if a dependency is missing.
        from ceo_core.ai_worker import AIWorkerProvider
        from ceo_core.goal_lock_local_provider_v1 import GoalLockLocalProviderV1
        from ceo_core.decomposer import TaskDecomposer
        from ceo_core.goal_engine import GoalEngine
        from ceo_core.goal_completion_gate import GoalCompletionGate
        from ceo_core.graph import TaskGraph
        from ceo_core.planning import BaselineTaskPlanner
        from ceo_core.project_catalog import ProjectCatalog
        from ceo_core.providers.chatgpt_web import ChatGPTWebTransport
        from ceo_core.real_work_queue import RealWorkQueue
        from ceo_core.progress_tracker import StableProgressTracker
        from ceo_core.device_fabric import AdaptiveDeviceFabric
        from ceo_core.in_app_updater import InAppUpdater
        from ceo_core.internal_release_coordinator import InternalReleaseCoordinator
        from ceo_core.prepared_release_bridge import PreparedReleaseBridge
        from ceo_core.observability import OperationalObservability
        from ceo_core.operator_attention import OperatorAttentionBroker
        from ceo_core.remote_control import RemoteControlProtocol, load_or_create_remote_secret
        from ceo_core.remote_session_v2 import RemoteSessionGuardV2
        from ceo_core.routing import MultiProviderRouter
        from ceo_core.runtime import user_data_root
        from ceo_core.scheduler import ContinuousScheduler

        self.TaskDecomposer = TaskDecomposer
        self.GoalEngine = GoalEngine
        self.GoalCompletionGate = GoalCompletionGate
        self.goal_completion_gate = GoalCompletionGate()
        self.Graph = TaskGraph
        self.BaselineTaskPlanner = BaselineTaskPlanner
        self.ProjectCatalog = ProjectCatalog
        self.RealWorkQueue = RealWorkQueue
        self.StableProgressTracker = StableProgressTracker
        self.AdaptiveDeviceFabric = AdaptiveDeviceFabric
        self.InAppUpdater = InAppUpdater
        self.InternalReleaseCoordinator = InternalReleaseCoordinator
        self.OperationalObservability = OperationalObservability
        self.OperatorAttentionBroker = OperatorAttentionBroker
        self.RemoteControlProtocol = RemoteControlProtocol
        self.RemoteSessionGuardV2 = RemoteSessionGuardV2
        self.MultiProviderRouter = MultiProviderRouter
        self.ContinuousScheduler = ContinuousScheduler
        self.AIWorkerProvider = AIWorkerProvider
        self.GoalLockLocalProviderV1 = GoalLockLocalProviderV1
        self.GeminiInteractionsTransport = None
        self.ChatGPTWebTransport = ChatGPTWebTransport
        self.data_dir = user_data_root()
        self.browser_transport = ChatGPTWebTransport()
        self.browser_provider_ready, self.browser_provider_detail = self.browser_transport.host_ready()
        self.no_api_required = True
        self.primary_ai_surface = "chatgpt-web"
        self.projects = ProjectCatalog(self.data_dir / "projects")
        self.progress_tracker = StableProgressTracker()
        self.device_fabric = AdaptiveDeviceFabric()
        self.updater = InAppUpdater(self.data_dir)
        self.internal_release = InternalReleaseCoordinator()
        self.prepared_release_bridge = PreparedReleaseBridge()
        self.internal_release.start()
        self.observability = OperationalObservability()
        self.attention_broker = OperatorAttentionBroker()
        self.remote_protocol = RemoteControlProtocol(load_or_create_remote_secret(self.data_dir))
        self.remote_session_guard = RemoteSessionGuardV2()
        # A key is never enough to claim execution is available. Keep it pending
        # until a real generateContent probe succeeds. This prevents a malformed,
        # revoked, quota-blocked or offline key from creating a false ACTIVE state.
        self._pending_gemini_key = (gemini_key or "").strip() or None
        startup_trust = _load_windows_dpapi_gemini_trust(self._pending_gemini_key) if self._pending_gemini_key else {}
        self.gemini_key = self._pending_gemini_key if startup_trust else None
        self.execution_enabled = bool(self.browser_provider_ready)
        self.provider_mode = (
            "chatgpt-web-ready"
            if self.browser_provider_ready
            else (
                "gemini-authenticated-waiting"
                if startup_trust
                else ("gemini-key-pending-validation" if self._pending_gemini_key else "browser-unavailable")
            )
        )
        self.gemini_model = str(startup_trust.get("model") or "") or None
        self.gemini_validation_error = None
        self.gemini_key_recognized = bool(startup_trust)
        self.gemini_key_status = "TRUSTED_PREVIOUSLY_VERIFIED" if startup_trust else None
        self.provider_validation_in_progress = False
        self._next_provider_revalidation_ts = 0.0
        self._provider_revalidation_interval_seconds = 300.0
        # DEV310 validation ownership. Provider probes are asynchronous, so an old
        # startup/revalidation result must never overwrite a newer manual key.
        self._provider_validation_epoch = 0
        self._provider_validation_source = "none"
        self._provider_validation_lock = threading.Lock()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, name="ceo-stdlib-async", daemon=True)
        self.thread.start()
        self.scheduler = None
        self.state = None
        self.router = None
        # DEV233: initialize the local/core runtime first. Provider validation is
        # deliberately deferred until after the local HTTP health endpoint is live.
        self.call(self._initialize())

    def _begin_provider_validation(self, source: str) -> int:
        with self._provider_validation_lock:
            self._provider_validation_epoch += 1
            self._provider_validation_source = str(source or "unknown")
            return int(self._provider_validation_epoch)

    def _provider_validation_is_current(self, epoch: int) -> bool:
        with self._provider_validation_lock:
            return int(epoch) == int(self._provider_validation_epoch)

    def start_provider_validation_background(self) -> bool:
        """Validate a recovered startup key without allowing stale-result overwrite."""
        if not self._pending_gemini_key or self.provider_validation_in_progress:
            return False
        key = self._pending_gemini_key
        self._pending_gemini_key = None
        epoch = self._begin_provider_validation("startup")
        self.provider_validation_in_progress = True
        def _runner():
            try:
                self.call(
                    self.activate_gemini(
                        key, validation_epoch=epoch, validation_source="startup"
                    ),
                    timeout=90,
                )
            except Exception as exc:
                self.gemini_validation_error = f"{type(exc).__name__}: {exc}"[:900]
                if self.gemini_key_recognized:
                    self.provider_mode = "chatgpt-web-ready" if self.browser_provider_ready else "gemini-authenticated-waiting"
                    self.gemini_key_status = self.gemini_key_status or "TRANSPORT_UNAVAILABLE"
                else:
                    self.provider_mode = "gemini-validation-deferred"
            finally:
                self.provider_validation_in_progress = False
        threading.Thread(target=_runner, name="ceo-provider-validation", daemon=True).start()
        return True

    def start_stored_provider_revalidation_background(self) -> bool:
        if self.provider_validation_in_progress:
            return False
        now = time.time()
        if now < float(self._next_provider_revalidation_ts or 0.0):
            return False
        self._next_provider_revalidation_ts = now + float(self._provider_revalidation_interval_seconds)
        epoch = self._begin_provider_validation("auto_revalidation")
        self.provider_validation_in_progress = True

        def _runner():
            try:
                self.call(
                    self.revalidate_stored_gemini(
                        validation_epoch=epoch, validation_source="auto_revalidation"
                    ),
                    timeout=90,
                )
            except Exception as exc:
                self.gemini_validation_error = f"{type(exc).__name__}: {exc}"[:900]
            finally:
                self.provider_validation_in_progress = False

        threading.Thread(target=_runner, name="ceo-provider-revalidation", daemon=True).start()
        return True

    def _gemini_transport_class(self):
        """Load API-specific code only when optional API mode is explicitly requested."""
        if self.GeminiInteractionsTransport is None:
            from ceo_core.providers.gemini_interactions import GeminiInteractionsTransport
            self.GeminiInteractionsTransport = GeminiInteractionsTransport
        return self.GeminiInteractionsTransport

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def call(self, coro, timeout: float = 180.0):
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return fut.result(timeout=timeout)

    def _router(self):
        local_goal_lock = self.GoalLockLocalProviderV1()
        providers = [local_goal_lock]

        # Browser-first execution is the default. CEO must remain useful with zero
        # API keys configured. The persistent Chrome profile is the normal AI surface.
        self.browser_provider_ready, self.browser_provider_detail = self.browser_transport.host_ready()
        if self.browser_provider_ready:
            providers.insert(0, self.AIWorkerProvider(self.browser_transport))

        # APIs are strictly optional and OFF by default.
        allow_optional_api = str(os.environ.get("CEO_ALLOW_OPTIONAL_API", "")).strip().lower() in {"1","true","yes","on"}
        if allow_optional_api and self.gemini_key:
            transport = self._gemini_transport_class()(api_key=self.gemini_key, model=self.gemini_model or "auto")
            providers.insert(0, self.AIWorkerProvider(transport))

        self.execution_enabled = bool(self.browser_provider_ready or (allow_optional_api and self.gemini_key))
        if self.browser_provider_ready:
            self.provider_mode = "chatgpt-web-ready"
        return self.MultiProviderRouter(providers)

    def _ensure_project_workspace(self, state):
        """Guarantee one durable workspace for every real-work project."""
        row = dict(state.metadata.get("workspace_v2") or {})
        configured = str(row.get("root") or "").strip()
        if configured:
            root = Path(configured).expanduser().resolve()
            managed = bool(row.get("managed", False))
        else:
            root = (self.data_dir / "workspaces" / state.id).resolve()
            managed = True
        root.mkdir(parents=True, exist_ok=True)
        row.update({
            "root": str(root),
            "project_id": state.id,
            "managed": managed,
            "available": True,
            "schema_version": 1,
        })
        state.metadata["workspace_v2"] = row
        return root

    async def _initialize(self):
        active = self.projects.active_project_id()
        if active:
            try:
                store = self.projects.store(active)
                state = store.load()
            except Exception:
                state = None
            if state is not None:
                state = store.prepare_for_resume(state)
                self._ensure_project_workspace(state)
                if self._pending_gemini_key:
                    trust_migration = _migrate_legacy_gemini_trust(state, self._pending_gemini_key)
                    state.metadata["dev312_gemini_trust_migration"] = trust_migration
                    migrated_trust = _load_windows_dpapi_gemini_trust(self._pending_gemini_key)
                    if migrated_trust:
                        self.gemini_key = self._pending_gemini_key
                        self.gemini_key_recognized = True
                        self.gemini_key_status = self.gemini_key_status or "TRUSTED_PREVIOUSLY_VERIFIED"
                        self.provider_mode = "chatgpt-web-ready" if self.browser_provider_ready else "gemini-authenticated-waiting"
                        self.gemini_model = str(migrated_trust.get("model") or "") or self.gemini_model
                self.state = state
                from ceo_core.scheduler import _apply_reliability_epoch_migration
                pre_scheduler_migration = _apply_reliability_epoch_migration(state)
                state.metadata["pre_scheduler_reliability_migration"] = pre_scheduler_migration
                if pre_scheduler_migration.get("changed"):
                    store.save(state)
                    self.projects.touch(state)
                self.device_fabric.initialize_windows(state)
                # Migrate prior real-work projects away from the old "finite batch ==
                # whole goal complete" semantics.  A persisted premature completion is
                # reopened unless it has an explicit goal-audit proof.
                state.metadata.setdefault("require_goal_audit", True)
                state.metadata.setdefault("strict_goal_completion_gate", True)
                state.metadata.setdefault("min_goal_audit_evidence_refs", 3)
                state.metadata.setdefault("min_goal_audit_grounded_refs", 2)
                state.metadata.setdefault("min_goal_continuity_generations", 3)
                if not (state.goal_success_definition or "").strip():
                    state.goal_success_definition = (
                        "The locked objective is complete only when concrete implementation or deliverable evidence exists, "
                        "independent verification supports it, no blocking work remains, and the strict goal audit passes."
                    )
                lower_goal = (state.goal or "").lower()
                if ("ceo" in lower_goal) and any(token in lower_goal for token in ("autónom", "autonom", "uso diario", "continuamente", "trabajador autónomo")):
                    state.metadata.setdefault("requires_field_endurance_certification", True)
                    state.metadata.setdefault("field_endurance_certified", False)
                migration = self.goal_completion_gate.migrate_invalid_legacy_pass(state)
                if state.completed_at is not None and not state.metadata.get("goal_audit_passed"):
                    state.metadata["reopened_after_goal_continuity_fix"] = True
                    state.completed_at = None
                    migration = {"changed": True, "reason": "premature_completion_reopened"}
                if migration.get("changed"):
                    state.metadata["grounded_completion_gate_migration"] = migration
                    store.save(state)
                    self.projects.touch(state)
                if not state.paused and not state.completed_at and not state.cancelled_at and not state.metadata.get("operator_cancelled"):
                    self.router = self._router()
                    self.scheduler = self.ContinuousScheduler(state, None, store, graph=self.Graph(), router=self.router)
                    self.scheduler.start()
        return True

    async def _stop_scheduler(self, *, timeout_seconds: float = 4.0):
        """Bounded project handoff.

        A stale recovery scheduler must never prevent the operator from starting a
        new objective. Give the current scheduler a short clean-stop window and,
        if it does not finish, persist a restart-safe checkpoint and cancel only
        the in-memory runtime tasks. The old project remains resumable.
        """
        scheduler = self.scheduler
        if scheduler is None:
            return {"ok": True, "mode": "no_scheduler", "forced": False}
        old_state = getattr(scheduler, "state", None)
        report = {
            "ok": True,
            "mode": "clean",
            "forced": False,
            "old_project_id": getattr(old_state, "id", None),
        }
        try:
            await asyncio.wait_for(scheduler.stop(), timeout=max(0.5, float(timeout_seconds)))
        except asyncio.TimeoutError:
            report.update({"mode": "forced_checkpoint", "forced": True})
            try:
                from ceo_core.models import TaskStatus
                if old_state is not None:
                    for task in old_state.tasks.values():
                        if task.status == TaskStatus.RUNNING:
                            if old_state.cancelled_at is not None or old_state.metadata.get("operator_cancelled"):
                                task.status = TaskStatus.SUPERSEDED
                                task.metadata["superseded_reason"] = "operator_cancelled"
                            else:
                                task.status = TaskStatus.RETRY
                                task.metadata["interrupted_by_project_handoff"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                                task.metadata["provider_stage"] = "interrupted"
                    old_state.metadata["project_handoff_recovery"] = {
                        "forced": True,
                        "reason": "scheduler_stop_timeout",
                        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    }
                stopper = getattr(scheduler, "_stop", None)
                if stopper is not None:
                    stopper.set()
                for future in list(getattr(scheduler, "_active", {}).values()):
                    if not future.done():
                        future.cancel()
                runner = getattr(scheduler, "_runner", None)
                if runner is not None and not runner.done():
                    runner.cancel()
                waits = [f for f in list(getattr(scheduler, "_active", {}).values()) if f is not None]
                if runner is not None:
                    waits.append(runner)
                if waits:
                    await asyncio.gather(*waits, return_exceptions=True)
                store = getattr(scheduler, "store", None)
                if store is not None and old_state is not None:
                    store.save(old_state)
            except Exception as exc:
                report["checkpoint_warning"] = f"{type(exc).__name__}: {exc}"[:500]
        except Exception as exc:
            report.update({"mode": "stop_error_recovered", "forced": True, "stop_error": f"{type(exc).__name__}: {exc}"[:500]})
        finally:
            if old_state is not None:
                try:
                    self.projects.touch(old_state)
                except Exception as exc:
                    report["catalog_warning"] = f"{type(exc).__name__}: {exc}"[:500]
                self.state = old_state
            self.scheduler = None
            self.router = None
        return report

    async def start_project(self, body: dict[str, Any]):
        self.browser_provider_ready, self.browser_provider_detail = self.browser_transport.host_ready()
        self.execution_enabled = bool(self.browser_provider_ready or (
            str(os.environ.get("CEO_ALLOW_OPTIONAL_API", "")).strip().lower() in {"1","true","yes","on"}
            and self.gemini_key
        ))
        if not self.execution_enabled:
            raise RuntimeError(
                "IA web no disponible. CEO necesita Chrome/Edge y su Browser AI Worker; "
                "no requiere ninguna API para iniciar trabajo real."
            )
        goal_text = str(body.get("goal") or "").strip()
        if len(goal_text) < 3:
            raise ValueError("El objetivo debe tener al menos 3 caracteres")
        # Plan first. A stale previous project must not destroy the operator's new
        # objective or leave the UI waiting with no visible progress.
        goal = self.GoalEngine().lock(
            goal_text,
            constraints=[
                "No spending, purchases, subscriptions or credits without separate explicit human approval.",
                "No automatic promotion of candidate builds.",
                "No Git network actions without explicit authorization.",
                "Destructive actions require a human gate.",
            ],
            forbidden_actions=["automatic_spending", "automatic_candidate_promotion", "unauthorized_git_network", "ungated_destructive_action"],
            urgency=50,
            budget_limit=0.0,
        )
        planner = self.BaselineTaskPlanner(self.TaskDecomposer())
        state = await planner.plan(goal)
        self.GoalEngine().apply(state, goal)
        handoff = await self._stop_scheduler(timeout_seconds=4.0)
        state.metadata["project_handoff"] = handoff
        if not (state.goal_success_definition or "").strip():
            state.goal_success_definition = (
                "The locked objective is complete only when concrete implementation or deliverable evidence exists, "
                "independent verification supports it, no blocking work remains, and the strict goal audit passes."
            )
        state.project_name = str(body.get("name") or goal_text[:80]).strip()
        state.power_percent = max(1, min(100, int(body.get("power_percent") or 30)))
        self._ensure_project_workspace(state)
        state.metadata["real_work_intake_v1"] = {
            "mode": "general_supervised",
            "automatic_spending": False,
            "automatic_candidate_promotion": False,
            "git_network_allowed": False,
            "destructive_actions_require_gate": True,
            "created_via": "stdlib_goal_engine",
        }
        state.metadata["production_verified"] = False
        self.device_fabric.initialize_windows(state)
        self.device_fabric.rebalance(state)
        state.metadata["provider_mode"] = self.provider_mode
        state.metadata["require_goal_audit"] = True
        state.metadata["goal_audit_passed"] = False
        state.metadata["goal_continuity_generation"] = 0
        state.metadata["strict_goal_completion_gate"] = True
        state.metadata["min_goal_audit_evidence_refs"] = 3
        state.metadata["min_goal_audit_grounded_refs"] = 2
        state.metadata["min_goal_continuity_generations"] = 3
        lower_goal = goal_text.lower()
        if ("ceo" in lower_goal) and any(token in lower_goal for token in ("autónom", "autonom", "uso diario", "continuamente", "trabajador autónomo")):
            state.metadata["requires_field_endurance_certification"] = True
            state.metadata.setdefault("field_endurance_certified", False)
        if not self.execution_enabled:
            state.metadata["execution_disabled_reason"] = self.gemini_validation_error or "External AI provider unavailable"
            state.metadata["provider_wait_v1"] = {
                "active": True, "category": "quota" if "QUOTA" in str(self.gemini_key_status or "").upper() else "provider_unavailable",
                "provider": "gemini-interactions", "retry_after_seconds": 300,
                "retry_after_ts": time.time() + 300, "recoveries_consumed": 0,
                "reason": self.gemini_validation_error or "External AI provider unavailable",
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        store = self.projects.store(state.id)
        store.save(state)
        self.projects.register(state, make_active=True)
        self.state = state
        self.router = self._router()
        self.scheduler = self.ContinuousScheduler(state, None, store, graph=self.Graph(), router=self.router)
        self.scheduler.start()
        return await self.snapshot()

    async def activate_gemini(
        self,
        raw_key: str,
        *,
        validation_epoch: int | None = None,
        validation_source: str = "manual",
    ):
        # Candidate validation is transactional: until the candidate is
        # authenticated, the currently-good provider state remains untouched.
        if validation_epoch is None:
            validation_epoch = self._begin_provider_validation(validation_source)
            if validation_source == "manual":
                # A new explicit key supersedes any startup key still in flight.
                self._pending_gemini_key = None

        key = _normalize_gemini_key(raw_key)
        if not key:
            candidate = str(raw_key or "").strip().strip("\"'").strip()
            if 20 <= len(candidate) <= 256 and not any(ch.isspace() for ch in candidate):
                key = candidate
        if not key:
            raise ValueError("No se reconoció una API key válida. Revisa que hayas pegado la clave completa.")

        transport = self._gemini_transport_class()(api_key=key, model="auto")
        probe = await transport.probe_live()

        # Last-validation-wins. A slower startup/old-key probe is read-only once a
        # newer validation has begun.
        if not self._provider_validation_is_current(validation_epoch):
            snap = await self.snapshot()
            snap["provider_validation_superseded"] = True
            return snap

        if not probe.get("ok"):
            detail = str(probe.get("detail") or probe.get("status") or "validación fallida")
            detail = detail.replace(key, "<redacted-api-key>")[:900]
            status = str(probe.get("status") or "GENERATION_UNAVAILABLE")
            status_upper = status.upper()
            models_visible = int(probe.get("models_visible") or 0)
            authenticated = probe.get("authenticated")
            prior_trust = _load_windows_dpapi_gemini_trust(key)
            hard_rejected = status_upper in {
                "401", "UNAUTHENTICATED", "API_KEY_INVALID", "INVALID_API_KEY"
            }

            if hard_rejected:
                _forget_windows_dpapi_gemini_trust()
                if self.gemini_key == key:
                    self.gemini_key = None
                self.gemini_key_recognized = False
                self.execution_enabled = bool(self.browser_provider_ready)
                self.gemini_key_status = status
                self.provider_mode = "chatgpt-web-ready" if self.browser_provider_ready else "gemini-validation-failed"
                raise RuntimeError(f"Google rechazó la clave Gemini: {detail}")

            recognized = bool(authenticated is True or models_visible > 0 or prior_trust)

            if not recognized:
                # Do not let an invalid/unverifiable replacement disable a working
                # credential. Only expose candidate failure diagnostics.
                self.gemini_validation_error = f"{status}: {detail}"[:900]
                if not self.gemini_key_recognized and not self.gemini_key:
                    self.gemini_key_status = status
                    self.provider_mode = (
                        "gemini-validation-failed"
                        if hard_rejected else "gemini-validation-deferred"
                    )
                raise RuntimeError(
                    "No se pudo comprobar la clave Gemini ahora; la credencial anterior "
                    f"se mantiene intacta. Detalle: {detail}"
                )

            # Google authenticated the key, but generation is temporarily
            # unavailable (quota/model/network at generation stage). Persist the
            # credential and wait autonomously instead of telling the user to
            # create another key.
            saved = _save_windows_dpapi_gemini_key(key)
            trust_saved = _save_windows_dpapi_gemini_trust(
                key,
                model=str(probe.get("model") or "") or self.gemini_model,
                source="authenticated_wait",
            )
            self.gemini_key = key
            self.gemini_key_recognized = True
            self.gemini_key_status = status
            self.gemini_validation_error = f"{status}: {detail}"[:900]
            self.execution_enabled = bool(self.browser_provider_ready)
            self.gemini_model = str(probe.get("model") or "") or None
            self.provider_mode = "chatgpt-web-ready" if self.browser_provider_ready else "gemini-authenticated-waiting"
            self._next_provider_revalidation_ts = (
                time.time() + float(self._provider_revalidation_interval_seconds)
            )

            state = self._state_obj()
            if state is not None:
                state.metadata["gemini_dpapi_saved"] = bool(saved)
                state.metadata["gemini_auth_trust_saved"] = bool(trust_saved)
                state.metadata["gemini_key_recognized"] = True
                state.metadata["gemini_key_status"] = status
                state.metadata["provider_mode"] = self.provider_mode
                state.metadata["gemini_live_verified"] = False
                state.metadata["execution_disabled_reason"] = self.gemini_validation_error
                state.metadata["provider_wait_v1"] = {
                    "active": True,
                    "category": "quota" if "QUOTA" in status_upper else "provider_unavailable",
                    "provider": "gemini-interactions",
                    "retry_after_seconds": int(self._provider_revalidation_interval_seconds),
                    "retry_after_ts": self._next_provider_revalidation_ts,
                    "reason": self.gemini_validation_error,
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "recoveries_consumed": 0,
                    "credential_authenticated": True,
                    "automatic_retry": True,
                }
                store = self.projects.store(state.id)
                store.save(state)
                self.projects.touch(state)
                self.router = self._router()
                if self.scheduler is not None:
                    self.scheduler.router = self.router
                    self.scheduler.graph.refresh(state)
            return await self.snapshot()

        # Commit successful validation only if it is still the newest one.
        if not self._provider_validation_is_current(validation_epoch):
            snap = await self.snapshot()
            snap["provider_validation_superseded"] = True
            return snap

        dpapi_saved = _save_windows_dpapi_gemini_key(key)
        trust_saved = _save_windows_dpapi_gemini_trust(
            key,
            model=str(probe.get("model") or "") or self.gemini_model,
            source="live_verified",
        )
        self.gemini_key = key
        self.gemini_validation_error = None
        self.gemini_key_recognized = True
        self.gemini_key_status = "LIVE_VERIFIED"
        self.execution_enabled = True
        self.gemini_model = str(probe.get("model") or "") or None
        self.provider_mode = "chatgpt-web-ready" if self.browser_provider_ready else "gemini-live-verified"
        self._next_provider_revalidation_ts = 0.0

        state = self._state_obj()
        if state is not None:
            state.metadata["gemini_dpapi_saved"] = bool(dpapi_saved)
            state.metadata["gemini_auth_trust_saved"] = bool(trust_saved)
            state.metadata["gemini_key_recognized"] = True
            state.metadata["gemini_key_status"] = "LIVE_VERIFIED"
            state.metadata["provider_mode"] = self.provider_mode
            state.metadata["gemini_live_verified"] = True
            if self.gemini_model:
                state.metadata["gemini_model"] = self.gemini_model
            state.metadata.pop("execution_disabled_reason", None)
            state.metadata.pop("provider_wait_v1", None)
            from ceo_core.models import TaskStatus
            for waiting_task in state.leaf_tasks:
                if waiting_task.metadata.pop("waiting_provider_v1", None) is not None:
                    waiting_task.metadata.pop("retry_after_ts", None)
                    if waiting_task.status == TaskStatus.BLOCKED:
                        waiting_task.status = TaskStatus.WAITING
            state.paused = False
            store = self.projects.store(state.id)
            store.save(state)
            self.projects.touch(state)
            self.router = self._router()
            if self.scheduler is None and not state.completed_at and not state.cancelled_at and not state.metadata.get("operator_cancelled"):
                self.scheduler = self.ContinuousScheduler(
                    state, None, store, graph=self.Graph(), router=self.router
                )
                self.scheduler.start()
            elif self.scheduler is not None:
                self.scheduler.router = self.router
                self.scheduler.graph.refresh(state)
        return await self.snapshot()

    async def revalidate_stored_gemini(
        self,
        *,
        validation_epoch: int | None = None,
        validation_source: str = "manual_revalidate",
    ):
        key = _load_windows_dpapi_gemini_key()
        if not key:
            raise RuntimeError("No hay una clave Gemini cifrada guardada para este usuario de Windows.")
        try:
            return await self.activate_gemini(
                key,
                validation_epoch=validation_epoch,
                validation_source=validation_source,
            )
        except Exception as exc:
            # Candidate/revalidation diagnostics may change, but a failed
            # revalidation never erases a previously-good runtime credential.
            self.gemini_validation_error = f"{type(exc).__name__}: {exc}"[:900]
            if self.gemini_key_recognized:
                self.provider_mode = "chatgpt-web-ready" if self.browser_provider_ready else "gemini-authenticated-waiting"
                self.gemini_key_status = self.gemini_key_status or "TRANSPORT_UNAVAILABLE"
            else:
                self.provider_mode = "gemini-validation-deferred"
            raise
        finally:
            key = None

    async def _ensure_scheduler_health(self):
        state = self._state_obj()
        if (
            self.gemini_key_recognized and not self.execution_enabled
            and not self.provider_validation_in_progress
            and time.time() >= float(self._next_provider_revalidation_ts or 0.0)
        ):
            self.start_stored_provider_revalidation_background()
        if state is None or state.paused or state.completed_at is not None or state.cancelled_at is not None or state.metadata.get("operator_cancelled"):
            return
        if self.scheduler is not None:
            runner = getattr(self.scheduler, "_runner", None)
            if runner is not None and runner.done():
                error = None
                try:
                    error = runner.exception()
                except Exception as exc:
                    error = exc
                if error is not None:
                    state.metadata.setdefault("scheduler_crash_history", []).append({
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "error": f"{type(error).__name__}: {error}"[:1000],
                    })
                    state.metadata["scheduler_crash_history"] = state.metadata["scheduler_crash_history"][-20:]
                self.scheduler = None
        if self.scheduler is None:
            store = self.projects.store(state.id)
            self.router = self._router()
            self.scheduler = self.ContinuousScheduler(state, None, store, graph=self.Graph(), router=self.router)
            self.scheduler.start()
            state.metadata["scheduler_auto_restarts"] = int(state.metadata.get("scheduler_auto_restarts", 0)) + 1
            store.save(state)

    def _state_obj(self):
        return self.scheduler.state if self.scheduler is not None else self.state

    async def executive_summary(self):
        s = await self.snapshot()
        o = s.get("observability") or {}
        cur = o.get("current_work") or []
        nxt = o.get("next_work") or []
        metrics = s.get("metrics") or {}
        attention = s.get("attention_cards") or []
        recoveries = int(((o.get("resilience") or {}).get("worker_recoveries") or 0))
        return build_executive_snapshot({
            "goal": s.get("goal") or "",
            "progress_percent": metrics.get("progress") or 0,
            "active_workers": metrics.get("running") or 0,
            "target_workers": ((o.get("resilience") or {}).get("adaptive_scheduler") or {}).get("target") or 0,
            "eta_seconds": (o.get("eta") or {}).get("seconds"),
            "completed": metrics.get("completed") or 0,
            "human_decisions": len(attention),
            "autonomous_recoveries": recoveries,
            "now": (cur[0].get("title") if cur else ""),
            "next": (nxt[0].get("title") if nxt else ""),
        })

    async def snapshot(self):
        await self._ensure_scheduler_health()
        state = self._state_obj()
        if state is None:
            return {
                "active": False,
                "execution_enabled": self.execution_enabled,
                "provider_mode": self.provider_mode,
                "no_api_required": True,
                "primary_ai_surface": self.primary_ai_surface,
                "browser_provider_ready": self.browser_provider_ready,
                "browser_provider_detail": self.browser_provider_detail,
                "gemini_model": self.gemini_model,
                "gemini_validation_error": self.gemini_validation_error,
                "gemini_key_recognized": self.gemini_key_recognized,
                "gemini_key_status": self.gemini_key_status,
                "power_percent": 30,
                "paused": False,
                "metrics": {"progress": 0, "running": 0, "completed": 0, "pending": 0},
                "queue": [],
                "observability": {"health":{"level":"idle","reasons":["no active project"]},"current_work":[],"next_work":[],"throughput":{},"eta":{"seconds":0},"attention":[],"stale_workers":[],"timeline":[],"scheduler":{"alive":False,"auto_restarts":0},"resilience":{"worker_recoveries":0,"adaptive_scheduler":{}}},
                "attention_cards": [],
                "message": "Goal Engine listo para recibir un objetivo.",
            }
        leaves = list(state.leaf_tasks)
        statuses = [t.status.value for t in leaves]
        queue = []
        for t in sorted(leaves, key=lambda x: (-int(x.priority), x.created_at))[:100]:
            if t.status.value not in {"complete", "superseded"}:
                queue.append({
                    "id": t.id, "title": t.title, "status": t.status.value, "priority": t.priority,
                    "dependencies": list(t.dependencies), "provider": t.provider_name,
                })
        try:
            self.projects.touch(state)
        except Exception:
            pass
        runner = getattr(self.scheduler, "_runner", None) if self.scheduler is not None else None
        scheduler_alive = bool(runner is not None and not runner.done())
        scheduler_error = None
        if runner is not None and runner.done():
            try:
                exc = runner.exception()
                if exc is not None:
                    scheduler_error = f"{type(exc).__name__}: {exc}"[:800]
            except Exception as exc:
                scheduler_error = f"{type(exc).__name__}: {exc}"[:800]
        provider_wait = dict(state.metadata.get("provider_wait_v1") or {})
        if provider_wait.get("active") and scheduler_alive:
            operational_status = "ESPERANDO PROVEEDOR"
        elif self.scheduler is not None:
            operational_status = self.scheduler.operational_status()
        elif state.cancelled_at is not None or state.metadata.get("operator_cancelled"):
            operational_status = "CANCELADO"
        elif state.completed_at is not None:
            operational_status = "COMPLETADO"
        elif state.paused:
            operational_status = "PAUSADO"
        else:
            operational_status = "SIN SCHEDULER"
        progress = self.progress_tracker.snapshot(state, persist=True)
        self.device_fabric.initialize_windows(state)
        device_plan = self.device_fabric.rebalance(state)
        timeline = list(state.metadata.get("activity_timeline", []))[-12:]
        watchdog = (state.metadata.get("autonomous_loop") or {}).get("watchdog") or {}
        stalled = state.metadata.get("autonomy_stalled")
        message = (
            f"Scheduler {operational_status}."
            + (f" Watchdog: {watchdog.get('status')}." if watchdog else "")
            + (f" ERROR: {scheduler_error}" if scheduler_error else "")
        )
        return {
            "active": True,
            "project_id": state.id,
            "project_name": state.project_name or state.goal[:80],
            "goal": state.goal,
            "execution_enabled": self.execution_enabled,
            "provider_mode": self.provider_mode,
            "no_api_required": True,
            "primary_ai_surface": self.primary_ai_surface,
            "browser_provider_ready": self.browser_provider_ready,
            "browser_provider_detail": self.browser_provider_detail,
            "gemini_model": self.gemini_model,
            "gemini_validation_error": self.gemini_validation_error,
            "gemini_key_recognized": self.gemini_key_recognized,
            "gemini_key_status": self.gemini_key_status,
            "power_percent": state.power_percent,
            "paused": state.paused,
            "completed_at": state.completed_at,
            "cancelled_at": state.cancelled_at,
            "cancelled_reason": state.cancelled_reason,
            "scheduler_alive": scheduler_alive,
            "scheduler_error": scheduler_error,
            "operational_status": operational_status,
            "operator_block_reason": state.metadata.get("operator_block_reason"),
            "watchdog": watchdog,
            "autonomy_stalled": stalled,
            "goal_audit_passed": bool(state.metadata.get("goal_audit_passed", False)),
            "goal_continuity_generation": int(state.metadata.get("goal_continuity_generation", 0)),
            "continuity_duplicate_spawn_drops": int(state.metadata.get("continuity_duplicate_spawn_drops", 0)),
            "continuity_nonspawn_rejections": int(state.metadata.get("continuity_nonspawn_rejections", 0)),
            "goal_audit_rejection": state.metadata.get("last_goal_audit_rejection"),
            "goal_audit_invalidated": state.metadata.get("goal_audit_invalidated"),
            "field_endurance_required": bool(state.metadata.get("requires_field_endurance_certification", False)),
            "field_endurance_certified": bool(state.metadata.get("field_endurance_certified", False)),
            "work_complete_certified": bool(state.metadata.get("work_complete_certified_v1", False)),
            "completion_phase": str(state.metadata.get("completion_phase_v1") or ""),
            "deterministic_completion_certificate": state.metadata.get("deterministic_completion_certificate_v1"),
            "metrics": {
                "progress": progress["display_progress"],
                "batch_progress": progress["batch_progress"],
                "legacy_progress": int(round(state.progress)),
                "running": progress["productive_running"],
                "completed": progress["productive_completed"],
                "pending": progress["productive_pending"],
                "control_running": progress["control_running"],
                "control_pending": progress["control_pending"],
                "control_completed": progress["control_completed"],
                "last_productive_progress_at": progress["last_productive_progress_at"],
                "superseded": statuses.count("superseded"),
            },
            "device_fabric": {
                "plan": device_plan,
                "notification_target": self.device_fabric.notification_target(state),
            },
            "queue": queue,
            "recent_activity": timeline,
            "observability": self.observability.snapshot(state, self.scheduler),
            "attention_cards": self.attention_broker.cards(state),
            "remote_control": {"protocol_version": self.remote_protocol.PROTOCOL_VERSION, "paired_devices": len(state.metadata.get("paired_remote_devices", {}) or {}), "network_exposed": False, "mutation_nonce_required": True, "replay_guard": "remote_session_v2"},
            "message": message,
        }

    async def attention_action(self, body: dict[str, Any]):
        state = self._state_obj()
        if state is None:
            raise RuntimeError("No active project")
        result = self.attention_broker.act(state, str(body.get("id") or ""), str(body.get("action") or ""), selection=body.get("selection"))
        store = self.scheduler.store if self.scheduler is not None else self.projects.store(state.id)
        store.save(state); self.projects.touch(state)
        return await self.snapshot()

    async def remote_pair(self, body: dict[str, Any]):
        if body.get("confirm") is not True:
            raise PermissionError("Remote pairing requires explicit local human confirmation")
        state = self._state_obj()
        if state is None:
            raise RuntimeError("No active project")
        device_id = str(body.get("device_id") or "").strip()
        if not device_id:
            raise ValueError("device_id required")
        scopes = [str(x) for x in (body.get("scopes") or ["status:read", "attention:read", "project:pause", "project:power", "decision:act"])]
        receipt = self.remote_protocol.pair(state, device_id, scopes)
        tokens = {scope: self.remote_protocol.issue_token(device_id, scope, ttl_seconds=3600) for scope in receipt.scopes}
        store = self.scheduler.store if self.scheduler is not None else self.projects.store(state.id)
        store.save(state); self.projects.touch(state)
        return {"paired": True, "receipt": receipt.to_dict(), "tokens": tokens, "safety": {"spending": False, "publication": False, "arbitrary_commands": False}}

    async def remote_status(self, token: str):
        state = self._state_obj()
        if state is None:
            raise RuntimeError("No active project")
        if self.remote_protocol.verify_token(state, token, "status:read") is None:
            raise PermissionError("Invalid or expired remote token")
        return self.remote_protocol.status_payload(state, self.observability.snapshot(state, self.scheduler))

    async def remote_attention(self, token: str):
        state = self._state_obj()
        if state is None:
            raise RuntimeError("No active project")
        if self.remote_protocol.verify_token(state, token, "attention:read") is None:
            raise PermissionError("Invalid or expired remote token")
        return {"attention": self.attention_broker.cards(state)}

    async def remote_decision_action(self, token: str, body: dict[str, Any]):
        state = self._state_obj()
        if state is None:
            raise RuntimeError("No active project")
        receipt = self.remote_session_guard.verify_and_consume(self.remote_protocol, state, token, "decision:act", str(body.get("nonce") or ""))
        if not receipt.accepted:
            raise PermissionError(f"Remote mutation rejected: {receipt.reason}")
        result = self.attention_broker.act(state, str(body.get("id") or ""), str(body.get("action") or ""), selection=body.get("selection"))
        store = self.scheduler.store if self.scheduler is not None else self.projects.store(state.id)
        store.save(state); self.projects.touch(state)
        return {"result": result, "attention": self.attention_broker.cards(state)}

    async def remote_pause(self, token: str, body: dict[str, Any]):
        state = self._state_obj()
        if state is None:
            raise RuntimeError("No active project")
        receipt = self.remote_session_guard.verify_and_consume(self.remote_protocol, state, token, "project:pause", str(body.get("nonce") or ""))
        if not receipt.accepted:
            raise PermissionError(f"Remote mutation rejected: {receipt.reason}")
        paused = body.get("paused")
        if not isinstance(paused, bool):
            raise ValueError("paused must be a boolean")
        return await self.pause(paused)

    async def remote_power(self, token: str, body: dict[str, Any]):
        state = self._state_obj()
        if state is None:
            raise RuntimeError("No active project")
        receipt = self.remote_session_guard.verify_and_consume(self.remote_protocol, state, token, "project:power", str(body.get("nonce") or ""))
        if not receipt.accepted:
            raise PermissionError(f"Remote mutation rejected: {receipt.reason}")
        if "power_percent" not in body:
            raise ValueError("power_percent required")
        return await self.power(int(body["power_percent"]))

    async def pause(self, paused: bool):
        state = self._state_obj()
        if state is None:
            return await self.snapshot()
        state.paused = bool(paused)
        if self.scheduler is not None:
            self.scheduler.store.save(state)
        else:
            self.projects.store(state.id).save(state)
        self.projects.touch(state)
        return await self.snapshot()

    async def cancel_project(self):
        state = self._state_obj()
        if state is None:
            return await self.snapshot()
        from ceo_core.models import TaskStatus, utcnow
        terminal = {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.SUPERSEDED}
        now = utcnow()
        state.cancelled_at = now
        state.cancelled_reason = "operator_cancelled"
        state.paused = True
        state.autonomy_enabled = False
        state.metadata["operator_cancelled"] = True
        state.metadata["operator_cancelled_at"] = now.isoformat()
        state.metadata["suppress_new_internal_recovery"] = True
        state.metadata["operator_productivity_state"] = "CANCELADO"
        for task in state.tasks.values():
            if task.status not in terminal:
                task.status = TaskStatus.SUPERSEDED
                task.metadata["superseded_reason"] = "operator_cancelled"
                task.metadata["cancelled_by_operator_at"] = now.isoformat()
        store = self.scheduler.store if self.scheduler is not None else self.projects.store(state.id)
        store.save(state)
        self.projects.touch(state)
        await self._stop_scheduler(timeout_seconds=4.0)
        self.projects.set_active(None)
        self.state = None
        self.scheduler = None
        self.router = None
        return await self.snapshot()

    async def power(self, value: int):
        state = self._state_obj()
        if state is not None:
            state.power_percent = max(1, min(100, int(value)))
            self.device_fabric.rebalance(state)
            if self.scheduler is not None:
                self.scheduler.store.save(state)
            else:
                self.projects.store(state.id).save(state)
            self.projects.touch(state)
        return await self.snapshot()

    async def activate_project(self, project_id: str):
        project_id = str(project_id or "").strip()
        if not project_id:
            raise ValueError("project_id requerido")
        await self._stop_scheduler()
        store = self.projects.store(project_id)
        state = store.load()
        if state is None:
            raise KeyError(project_id)
        if state.cancelled_at is not None or state.metadata.get("operator_cancelled"):
            raise RuntimeError("Este proyecto fue cancelado. Crea un nuevo objetivo si quieres retomarlo; la cancelación no se revierte automáticamente.")
        state = store.prepare_for_resume(state)
        self.projects.set_active(project_id)
        state.metadata.setdefault("require_goal_audit", True)
        state.metadata.setdefault("strict_goal_completion_gate", True)
        state.metadata.setdefault("min_goal_audit_evidence_refs", 3)
        state.metadata.setdefault("min_goal_audit_grounded_refs", 2)
        state.metadata.setdefault("min_goal_continuity_generations", 3)
        if not (state.goal_success_definition or "").strip():
            state.goal_success_definition = (
                "The locked objective is complete only when concrete implementation or deliverable evidence exists, "
                "independent verification supports it, no blocking work remains, and the strict goal audit passes."
            )
        lower_goal = (state.goal or "").lower()
        if ("ceo" in lower_goal) and any(token in lower_goal for token in ("autónom", "autonom", "uso diario", "continuamente", "trabajador autónomo")):
            state.metadata.setdefault("requires_field_endurance_certification", True)
            state.metadata.setdefault("field_endurance_certified", False)
        migration = self.goal_completion_gate.migrate_invalid_legacy_pass(state)
        if migration.get("changed"):
            state.metadata["grounded_completion_gate_migration"] = migration
        # DEV20 migration: older builds could loop through hundreds of continuity
        # audits whose follow-ups were subsequently deduplicated.  If we reopen such
        # a project with no productive work queued, prime the existing deterministic
        # gap bridge so the next duplicate-only audit immediately returns to real work.
        generation = int(state.metadata.get("goal_continuity_generation", 0) or 0)
        productive_open = [
            t for t in state.leaf_tasks
            if not (t.metadata.get("goal_continuity_audit") or t.metadata.get("autonomy_recovery") or t.metadata.get("control_plane_atomic") or t.metadata.get("continuity_control"))
            and t.status.value not in {"complete", "partial_complete", "complete_with_uncertainty", "superseded", "failed"}
        ]
        if generation >= 8 and not productive_open:
            state.metadata["continuity_nonspawn_rejections"] = max(
                2, int(state.metadata.get("continuity_nonspawn_rejections", 0) or 0)
            )
            state.metadata["dev20_churn_breaker_primed"] = True
        state.paused = not self.execution_enabled
        store.save(state)
        self.projects.touch(state)
        self.state = state
        if self.execution_enabled and state.completed_at is None:
            self.router = self._router()
            self.scheduler = self.ContinuousScheduler(state, None, store, graph=self.Graph(), router=self.router)
            self.scheduler.start()
        return await self.snapshot()

    async def projects_list(self):
        return self.projects.portfolio_list(include_archived=True, total_slots=8)

    async def update_status(self, remote: bool = False):
        return await asyncio.to_thread(self.updater.status, current_version=APP_VERSION, include_remote=bool(remote))

    async def update_config(self, payload: dict[str, Any]):
        return await asyncio.to_thread(
            self.updater.save_config,
            manifest_url=str(payload.get("manifest_url") or ""),
            channel=str(payload.get("channel") or "stable"),
            auto_check=bool(payload.get("auto_check", True)),
        )

    async def update_stage(self):
        return await asyncio.to_thread(self.updater.stage_latest, current_version=APP_VERSION)

    async def update_preflight(self, version: str):
        return await asyncio.to_thread(self.updater.preflight_staged, version, python_executable=sys.executable)

    async def update_activate(self, version: str):
        return await asyncio.to_thread(self.updater.activate, version)

    async def update_view(self, remote: bool = False):
        return await asyncio.to_thread(self.updater.update_view, current_version=APP_VERSION, include_remote=bool(remote))

    async def update_diagnostics(self):
        return await asyncio.to_thread(self.updater.diagnostics)

    async def update_transaction_status(self):
        return await asyncio.to_thread(self.updater.transaction_status)

    async def update_operator_summary(self, remote: bool = False):
        return await asyncio.to_thread(self.updater.operator_summary, current_version=APP_VERSION, include_remote=bool(remote))

    async def internal_release_status(self):
        return await asyncio.to_thread(self.internal_release.status)

    async def activate_prepared_release(self, manifest_url: str):
        return await asyncio.to_thread(self.prepared_release_bridge.activate, manifest_url)

    async def shutdown(self):
        try:
            await self._stop_scheduler()
        finally:
            try:
                self.internal_release.stop()
            except Exception:
                pass
            self.loop.call_soon(self.loop.stop)


class Handler(BaseHTTPRequestHandler):
    engine: CEOEngine

    def log_message(self, fmt, *args):
        try:
            (RESULTS / "CEO_STDLIB_SERVER.log").open("a", encoding="utf-8").write((fmt % args) + "\n")
        except Exception:
            pass

    def _send(self, code: int, data: bytes, content_type: str):
        try:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) in {64, 995, 10053, 10054}:
                return
            raise

    def json(self, obj: Any, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"), "application/json; charset=utf-8")

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def bearer(self) -> str:
        value = str(self.headers.get("Authorization") or "")
        return value[7:].strip() if value.lower().startswith("bearer ") else ""

    def do_GET(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            if path == "/":
                return self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
            if path == "/favicon.ico":
                icon = ROOT / "assets" / "CEO_DE_IAS.ico"
                if icon.is_file():
                    return self._send(200, icon.read_bytes(), "image/x-icon")
                return self._send(204, b"", "image/x-icon")
            if path == "/api/health":
                from ceo_core.core_health_contract_v2 import build_core_health_v2
                pointer = self.engine.updater.current_pointer() or {}
                storage_ready = bool(self.engine.projects.root.exists())
                core_ready = bool(self.engine.loop.is_running() and self.engine.thread.is_alive())
                frontend_ready = bool(HTML and "Goal Engine" in HTML and "/api/state" in HTML)
                payload = build_core_health_v2(
                    version=APP_VERSION,
                    activation_id=pointer.get("activation_id"),
                    storage_ready=storage_ready,
                    runtime_ready=core_ready,
                    frontend_ready=frontend_ready,
                    provider_mode=self.engine.provider_mode,
                    execution_enabled=self.engine.execution_enabled,
                    provider_error=self.engine.gemini_validation_error,
                    provider_validation_in_progress=self.engine.provider_validation_in_progress,
                )
                return self.json(payload, 200 if payload["ok"] else 503)
            if path == "/api/state":
                return self.json(self.engine.call(self.engine.snapshot()))
            if path == "/api/executive-summary":
                return self.json(self.engine.call(self.engine.executive_summary()))
            if path == "/api/projects":
                return self.json(self.engine.call(self.engine.projects_list()))
            if path == "/api/update/status":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                remote = str((query.get("remote") or ["0"])[0]).lower() in {"1","true","yes"}
                return self.json(self.engine.call(self.engine.update_status(remote), timeout=60))
            if path == "/api/update/progress":
                return self.json(self.engine.updater.progress())
            if path == "/api/update/view":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                remote = str((query.get("remote") or ["0"])[0]).lower() in {"1","true","yes"}
                return self.json(self.engine.call(self.engine.update_view(remote), timeout=60))
            if path == "/api/update/diagnostics":
                return self.json(self.engine.call(self.engine.update_diagnostics(), timeout=30))
            if path == "/api/update/transaction":
                return self.json(self.engine.call(self.engine.update_transaction_status(), timeout=30))
            if path == "/api/update/summary":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                remote = str((query.get("remote") or ["0"])[0]).lower() in {"1","true","yes"}
                return self.json(self.engine.call(self.engine.update_operator_summary(remote), timeout=60))
            if path == "/api/internal-release/status":
                return self.json(self.engine.call(self.engine.internal_release_status(), timeout=30))
            if path == "/api/work-queue":
                s = self.engine.call(self.engine.snapshot())
                return self.json({"active": s.get("active", False), "queue": s.get("queue", []), "safety": {"automatic_spending": False, "automatic_candidate_promotion": False, "git_network_allowed": False, "destructive_actions_require_gate": True}})
            if path == "/api/operations":
                s = self.engine.call(self.engine.snapshot())
                return self.json({"active": s.get("active", False), "project_id": s.get("project_id"), "observability": s.get("observability", {})})
            if path == "/api/attention":
                s = self.engine.call(self.engine.snapshot())
                return self.json({"attention": s.get("attention_cards", [])})
            if path == "/api/remote/status":
                return self.json(self.engine.call(self.engine.remote_status(self.bearer())))
            if path == "/api/remote/attention":
                return self.json(self.engine.call(self.engine.remote_attention(self.bearer())))
            return self.json({"error": "not_found"}, 404)
        except Exception as exc:
            return self.json({"error": str(exc)}, 500)

    def do_POST(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/start":
                return self.json(self.engine.call(self.engine.start_project(self.body()), timeout=240))
            if path == "/api/pause":
                return self.json(self.engine.call(self.engine.pause(True)))
            if path == "/api/resume":
                if not self.engine.execution_enabled:
                    return self.json({"error": "IA web no disponible. CEO necesita Chrome/Edge; no requiere ninguna API para reanudar."}, 409)
                return self.json(self.engine.call(self.engine.pause(False)))
            if path == "/api/cancel":
                body = self.body()
                if body.get("confirm") is not True:
                    return self.json({"error": "Cancelar un objetivo requiere confirmación humana explícita."}, 409)
                return self.json(self.engine.call(self.engine.cancel_project(), timeout=30))
            if path == "/api/power":
                return self.json(self.engine.call(self.engine.power(int(self.body().get("power_percent") or 30))))
            if path == "/api/session-key":
                body = self.body()
                return self.json(self.engine.call(self.engine.activate_gemini(str(body.get("key") or ""))))
            if path == "/api/session-key/revalidate":
                return self.json(self.engine.call(self.engine.revalidate_stored_gemini(), timeout=120))
            if path == "/api/session-key/forget":
                forgotten = _forget_windows_dpapi_gemini_key()
                return self.json({"ok": bool(forgotten), "forgotten": bool(forgotten)})
            if path == "/api/project/activate":
                body = self.body()
                return self.json(self.engine.call(self.engine.activate_project(str(body.get("project_id") or "")), timeout=120))
            if path == "/api/attention/action":
                return self.json(self.engine.call(self.engine.attention_action(self.body())))
            if path == "/api/remote/pair":
                body = self.body()
                if body.get("confirm") is not True:
                    return self.json({"error": "Remote pairing requires explicit local human confirmation."}, 409)
                return self.json(self.engine.call(self.engine.remote_pair(body)))
            if path == "/api/remote/decision":
                return self.json(self.engine.call(self.engine.remote_decision_action(self.bearer(), self.body())))
            if path == "/api/remote/pause":
                return self.json(self.engine.call(self.engine.remote_pause(self.bearer(), self.body())))
            if path == "/api/remote/power":
                return self.json(self.engine.call(self.engine.remote_power(self.bearer(), self.body())))
            if path == "/api/internal-release/activate-prepared":
                body = self.body()
                return self.json(self.engine.call(self.engine.activate_prepared_release(str(body.get("manifest_url") or "")), timeout=300))
            if path == "/api/update/config":
                return self.json(self.engine.call(self.engine.update_config(self.body()), timeout=30))
            if path == "/api/update/stage":
                return self.json(self.engine.call(self.engine.update_stage(), timeout=240))
            if path == "/api/update/install":
                body = self.body()
                if body.get("confirm") is not True:
                    return self.json({"error": "La instalación requiere confirmación humana explícita."}, 409)
                version = str(body.get("version") or "")
                preflight = self.engine.call(self.engine.update_preflight(version), timeout=90)
                result = self.engine.call(self.engine.update_activate(version), timeout=30)
                launcher = str(result.get("launcher_path") or "")
                activation_id = str(result.get("activation_id") or "")
                helper = ROOT / "scripts" / "relaunch_after_update.py"
                subprocess.Popen(
                    [
                        sys.executable, str(helper),
                        "--wait-pid", str(os.getpid()),
                        "--launcher", launcher,
                        "--data-root", str(self.engine.data_dir),
                        "--version", version,
                        "--activation-id", activation_id,
                        "--fallback-launcher", str(ROOT / "ABRIR_CEO.cmd"),
                        "--health-timeout", "60",
                    ],
                    cwd=str(ROOT),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                )
                self.json({
                    "status": "RESTARTING_PENDING_HEALTH",
                    "version": version,
                    "activation_id": activation_id,
                    "automatic_promotion": False,
                    "human_confirmed": True,
                    "rollback_armed": True,
                    "preflight": preflight,
                }, 202)
                def _delayed_shutdown():
                    time.sleep(0.45)
                    self.server.shutdown()
                threading.Thread(target=_delayed_shutdown, daemon=True).start()
                return
            return self.json({"error": "not_found"}, 404)
        except Exception as exc:
            return self.json({"error": str(exc)}, 500)


def free_port() -> int:
    for port in range(8765, 8781):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No hay un puerto local libre entre 8765 y 8780")


def open_browser(url: str) -> str:
    if os.getenv("CEO_NO_BROWSER", "").strip().lower() in {"1", "true", "yes"}:
        return "suppressed-by-env"
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        ]
        for exe in candidates:
            try:
                if exe.is_file():
                    subprocess.Popen([str(exe), f"--app={url}", "--start-maximized"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return str(exe)
            except Exception:
                pass
    webbrowser.open(url, new=1)
    return "default-browser"


def _normalize_gemini_key(raw: str | None) -> str | None:
    """Extract one plausible Gemini/Google API key without logging it.

    Clipboard content can contain CR/LF, quotes, labels, rich-text fallbacks or
    zero-width Unicode characters.  Search *within* the text instead of requiring
    the clipboard to contain only the key.  Never return surrounding content.
    """
    if raw is None:
        return None
    text = str(raw)
    # Remove common invisible formatting characters that can be introduced when
    # copying from browsers/password managers while keeping the actual key intact.
    text = text.translate({ord(ch): None for ch in "\u200b\u200c\u200d\ufeff\u2060"})
    # Google API keys used by Gemini normally begin with AIza.  Keep the pattern
    # narrow enough to avoid treating arbitrary clipboard text as a credential.
    matches = re.findall(r"(?<![0-9A-Za-z_-])(AIza[0-9A-Za-z_-]{24,80})(?![0-9A-Za-z_-])", text)
    if len(matches) == 1:
        return matches[0]
    # Also accept an exact key if boundary characters were unusual.
    candidate = text.strip().strip("\"'").strip()
    if re.fullmatch(r"AIza[0-9A-Za-z_-]{24,80}", candidate):
        return candidate
    return None




def _gemini_secret_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "CEO de IAs" / "secrets" / "gemini_api_key.dpapi"


def _gemini_trust_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "CEO de IAs" / "secrets" / "gemini_auth_trust.dpapi"


def _gemini_key_fingerprint(key: str) -> str:
    import hashlib
    return hashlib.sha256(str(key or "").encode("utf-8")).hexdigest()


def _windows_dpapi_protect_text(value: str) -> bytes | None:
    """Encrypt UTF-8 text with Windows DPAPI CurrentUser scope.

    Uses the same optional entropy as the temporary PowerShell launcher used
    during physical validation, so an already-saved key remains compatible.
    """
    if sys.platform != "win32" or not value:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(DATA_BLOB),
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p

        raw = value.encode("utf-8")
        entropy_raw = b"CEO-de-IAs|Gemini|DPAPI|v1"
        raw_buf = ctypes.create_string_buffer(raw, len(raw))
        entropy_buf = ctypes.create_string_buffer(entropy_raw, len(entropy_raw))
        in_blob = DATA_BLOB(len(raw), ctypes.cast(raw_buf, ctypes.POINTER(ctypes.c_byte)))
        entropy_blob = DATA_BLOB(len(entropy_raw), ctypes.cast(entropy_buf, ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()
        ok = crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            "CEO de IAs Gemini key",
            ctypes.byref(entropy_blob),
            None,
            None,
            0,
            ctypes.byref(out_blob),
        )
        if not ok:
            return None
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))
    except Exception:
        return None


def _windows_dpapi_unprotect_text(blob: bytes) -> str | None:
    """Decrypt Windows DPAPI CurrentUser ciphertext with validation entropy."""
    if sys.platform != "win32" or not blob:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(DATA_BLOB), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(DATA_BLOB),
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p

        entropy_raw = b"CEO-de-IAs|Gemini|DPAPI|v1"
        blob_buf = ctypes.create_string_buffer(blob, len(blob))
        entropy_buf = ctypes.create_string_buffer(entropy_raw, len(entropy_raw))
        in_blob = DATA_BLOB(len(blob), ctypes.cast(blob_buf, ctypes.POINTER(ctypes.c_byte)))
        entropy_blob = DATA_BLOB(len(entropy_raw), ctypes.cast(entropy_buf, ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()
        description = ctypes.c_void_p()
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            ctypes.byref(description),
            ctypes.byref(entropy_blob),
            None,
            None,
            0,
            ctypes.byref(out_blob),
        )
        if not ok:
            return None
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8")
        finally:
            if description.value:
                kernel32.LocalFree(description)
            kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))
    except Exception:
        return None


def _plausible_gemini_key(value: str | None) -> str | None:
    """Accept validated-key shapes without assuming every Gemini key starts with AIza."""
    normalized = _normalize_gemini_key(value)
    if normalized:
        return normalized
    candidate = str(value or "").strip().strip("\"'").strip()
    if 20 <= len(candidate) <= 256 and not any(ch.isspace() for ch in candidate):
        return candidate
    return None


def _load_windows_dpapi_gemini_key_via_powershell(path: Path) -> str | None:
    """Fallback for DPAPI blobs created by the physical-validation PowerShell launcher."""
    if sys.platform != "win32" or not path.exists():
        return None
    try:
        import base64
        import subprocess
        script = """
$ErrorActionPreference='Stop'
$p=$env:CEO_GEMINI_DPAPI_FILE
$entropy=[Text.Encoding]::UTF8.GetBytes('CEO-de-IAs|Gemini|DPAPI|v1')
$protected=[Convert]::FromBase64String([IO.File]::ReadAllText($p).Trim())
$plain=[Security.Cryptography.ProtectedData]::Unprotect($protected,$entropy,[Security.Cryptography.DataProtectionScope]::CurrentUser)
try { [Console]::Out.Write([Convert]::ToBase64String($plain)) } finally { [Array]::Clear($plain,0,$plain.Length) }
"""
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        env = os.environ.copy()
        env["CEO_GEMINI_DPAPI_FILE"] = str(path)
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            timeout=12,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        plain = base64.b64decode(proc.stdout.strip(), validate=True).decode("utf-8")
        return _plausible_gemini_key(plain)
    except Exception:
        return None


def _save_windows_dpapi_gemini_key_via_powershell(key: str, path: Path) -> bool:
    """PowerShell DPAPI fallback. The plaintext travels only over stdin."""
    if sys.platform != "win32" or not key:
        return False
    try:
        import base64
        import subprocess
        script = """
$ErrorActionPreference='Stop'
$p=$env:CEO_GEMINI_DPAPI_FILE
$entropy=[Text.Encoding]::UTF8.GetBytes('CEO-de-IAs|Gemini|DPAPI|v1')
$rawB64=[Console]::In.ReadToEnd().Trim()
$plain=[Convert]::FromBase64String($rawB64)
try {
  $protected=[Security.Cryptography.ProtectedData]::Protect($plain,$entropy,[Security.Cryptography.DataProtectionScope]::CurrentUser)
  $dir=[IO.Path]::GetDirectoryName($p)
  [IO.Directory]::CreateDirectory($dir) | Out-Null
  [IO.File]::WriteAllText($p,[Convert]::ToBase64String($protected),[Text.Encoding]::ASCII)
  [Console]::Out.Write('OK')
} finally { [Array]::Clear($plain,0,$plain.Length) }
"""
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        env = os.environ.copy()
        env["CEO_GEMINI_DPAPI_FILE"] = str(path)
        payload = base64.b64encode(key.encode("utf-8")).decode("ascii")
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            input=payload,
            capture_output=True,
            text=True,
            timeout=12,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return proc.returncode == 0 and proc.stdout.strip() == "OK"
    except Exception:
        return False


def _save_windows_dpapi_gemini_key(key: str) -> bool:
    """Persist the already-live-validated key encrypted for the current Windows user."""
    normalized = _plausible_gemini_key(key)
    if not normalized:
        return False
    path = _gemini_secret_path()
    encrypted = _windows_dpapi_protect_text(normalized)
    if encrypted:
        try:
            import base64
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(base64.b64encode(encrypted).decode("ascii"), encoding="ascii")
            os.replace(tmp, path)
            return True
        except Exception:
            pass
    return _save_windows_dpapi_gemini_key_via_powershell(normalized, path)


def _load_windows_dpapi_gemini_key() -> str | None:
    """Load a DPAPI-encrypted Gemini key without exposing it outside this process."""
    if sys.platform != "win32":
        return None
    path = _gemini_secret_path()
    if not path.exists():
        return None
    try:
        import base64
        encrypted = base64.b64decode(path.read_text(encoding="ascii").strip(), validate=True)
        native = _plausible_gemini_key(_windows_dpapi_unprotect_text(encrypted))
        if native:
            return native
    except Exception:
        pass
    return _load_windows_dpapi_gemini_key_via_powershell(path)


def _save_windows_dpapi_gemini_trust(key: str, *, model: str | None = None, source: str = "verified") -> bool:
    if sys.platform != "win32" or not key:
        return False
    payload = json.dumps({
        "schema": 1,
        "fingerprint": _gemini_key_fingerprint(key),
        "model": str(model or ""),
        "source": str(source or "verified"),
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, ensure_ascii=False, sort_keys=True)
    blob = _windows_dpapi_protect_text(payload)
    if not blob:
        return False
    path = _gemini_trust_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(blob)
    tmp.replace(path)
    return True


def _load_windows_dpapi_gemini_trust(key: str) -> dict:
    if sys.platform != "win32" or not key:
        return {}
    path = _gemini_trust_path()
    try:
        if not path.is_file():
            return {}
        raw = _windows_dpapi_unprotect_text(path.read_bytes())
        if not raw:
            return {}
        row = json.loads(raw)
        if not isinstance(row, dict):
            return {}
        if str(row.get("fingerprint") or "") != _gemini_key_fingerprint(key):
            return {}
        return row
    except Exception:
        return {}


def _forget_windows_dpapi_gemini_trust() -> bool:
    path = _gemini_trust_path()
    try:
        if path.exists():
            path.unlink()
        return True
    except Exception:
        return False


def _migrate_legacy_gemini_trust(state, key: str) -> dict:
    """Bootstrap DEV312 trust from prior durable evidence for the current DPAPI key."""
    if not key or state is None:
        return {"migrated": False, "reason": "missing_state_or_key"}
    existing = _load_windows_dpapi_gemini_trust(key)
    if existing:
        return {"migrated": False, "reason": "already_trusted", "trust": existing}
    meta = dict(getattr(state, "metadata", {}) or {})
    prior_saved = bool(meta.get("gemini_dpapi_saved"))
    prior_recognized = bool(meta.get("gemini_key_recognized") or meta.get("gemini_live_verified"))
    if not (prior_saved and prior_recognized):
        return {"migrated": False, "reason": "legacy_evidence_insufficient"}
    model = str(meta.get("gemini_model") or "")
    ok = _save_windows_dpapi_gemini_trust(
        key, model=model or None, source="dev312_legacy_migration"
    )
    return {
        "migrated": bool(ok),
        "reason": "legacy_authenticated_key_bound" if ok else "trust_write_failed",
        "model": model,
    }


def _forget_windows_dpapi_gemini_key() -> bool:
    _forget_windows_dpapi_gemini_trust()
    try:
        path = _gemini_secret_path()
        if path.exists():
            path.unlink()
        return True
    except Exception:
        return False

def _read_windows_clipboard_native() -> str | None:
    """Read CF_UNICODETEXT directly via Win32, with no third-party dependency."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        CF_UNICODETEXT = 13
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
        user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        opened = False
        for _ in range(10):
            if user32.OpenClipboard(None):
                opened = True
                break
            time.sleep(0.05)
        if not opened:
            return None
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return None
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except Exception:
        return None


def _read_windows_clipboard_powershell() -> str | None:
    """Fallback clipboard reader for Windows PowerShell/PowerShell 7."""
    if sys.platform != "win32":
        return None
    ps = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("powershell")
    if not ps:
        return None
    commands = [
        "$v=Get-Clipboard -Raw -ErrorAction Stop; if($null -ne $v){[Console]::Out.Write($v)}",
        "$v=Get-Clipboard -ErrorAction Stop; if($null -ne $v){[Console]::Out.Write(($v -join [Environment]::NewLine))}",
    ]
    for command in commands:
        try:
            cp = subprocess.run(
                [ps, "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if cp.returncode == 0 and cp.stdout:
                return cp.stdout
        except Exception:
            pass
    return None


def _read_windows_clipboard_gemini_key() -> str | None:
    """Try native Win32 first, then PowerShell; return only the extracted key."""
    for reader in (_read_windows_clipboard_native, _read_windows_clipboard_powershell):
        try:
            key = _normalize_gemini_key(reader())
            if key:
                return key
        except Exception:
            pass
    return None


def _gui_gemini_key_prompt() -> str | None:
    """Last-resort GUI paste box. Text is never persisted and the field is masked."""
    if sys.platform != "win32":
        return None
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title("CEO de IAs - Gemini API key")
        root.geometry("560x180")
        root.resizable(False, False)
        tk.Label(root, text="No pude leer la clave del portapapeles automáticamente.", pady=10).pack()
        tk.Label(root, text="Pégala aquí con Ctrl+V. Si Gemini la valida, se guardará cifrada con Windows DPAPI.").pack()
        value = tk.StringVar()
        entry = tk.Entry(root, textvariable=value, show="*", width=70)
        entry.pack(padx=18, pady=12)
        entry.focus_force()
        result = {"key": None}
        def accept(event=None):
            result["key"] = _normalize_gemini_key(value.get())
            root.destroy()
        def cancel(event=None):
            root.destroy()
        buttons = tk.Frame(root)
        buttons.pack()
        tk.Button(buttons, text="Usar clave", command=accept, width=16).pack(side=tk.LEFT, padx=6)
        tk.Button(buttons, text="Continuar sin Gemini", command=cancel, width=20).pack(side=tk.LEFT, padx=6)
        root.bind("<Return>", accept)
        root.bind("<Escape>", cancel)
        root.mainloop()
        return result["key"]
    except Exception:
        return None


def _wait_startup_health(url: str, *, timeout: float = 12.0) -> dict[str, Any]:
    deadline = time.time() + max(1.0, timeout)
    last_error = "startup health unavailable"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/api/health", timeout=1.5) as resp:
                payload = json.loads(resp.read(1024 * 1024).decode("utf-8"))
            if (
                isinstance(payload, dict)
                and payload.get("ok") is True
                and payload.get("storage_ready") is True
                and payload.get("scheduler_component_ready") is True
                and payload.get("frontend_ready") is True
            ):
                return payload
            last_error = f"health not ready: {payload}"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.15)
    raise RuntimeError(last_error)


def main() -> int:
    os.chdir(ROOT)
    os.environ["PYTHONPATH"] = str(ROOT) + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")
    print("=" * 68)
    print("CEO DE IAs - MODO TRABAJO REAL - SERVIDOR SIN FASTAPI/UVICORN")
    print("=" * 68)
    print("No repite 76-85. No instala dependencias web. No modifica Python global.")
    print("La clave Gemini no se guarda en el proyecto; en Windows puede persistirse cifrada con DPAPI.")
    print()
    allow_optional_api = str(os.environ.get("CEO_ALLOW_OPTIONAL_API", "")).strip().lower() in {"1","true","yes","on"}
    key = None
    key_source = "disabled"
    if allow_optional_api:
        key = _normalize_gemini_key(os.environ.get("GEMINI_API_KEY"))
        key_source = "environment" if key else None
        key_in_browser = os.getenv("CEO_KEY_IN_BROWSER", "").strip() == "1"
        if not key and not key_in_browser:
            key = _load_windows_dpapi_gemini_key()
            if key:
                key_source = "windows-dpapi"
                print("[OK] Gemini opcional recuperado de Windows DPAPI.")
        if not key and not key_in_browser:
            key = _read_windows_clipboard_gemini_key()
            if key:
                key_source = "windows-clipboard"
                print("[OK] Gemini opcional detectado en el portapapeles.")
        if not key and not key_in_browser:
            print("[INFO] API opcional habilitada pero sin clave Gemini; CEO seguirá usando IA web.")
        elif not key and key_in_browser:
            print("[INFO] API opcional habilitada; puede configurarse más tarde desde la interfaz.")
    else:
        print("[OK] Modo IA web gratuito: no se solicita ni se necesita ninguna API key.")
    try:
        engine = CEOEngine(key or None)
        Handler.engine = engine
        port = free_port()
        url = f"http://127.0.0.1:{port}"
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        server_thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.4}, name="ceo-stdlib-http", daemon=True)
        server_thread.start()
        startup_health = _wait_startup_health(url)
        # DEV233/234: only after core health is externally observable do we allow
        # provider validation to begin. A 404/429/offline provider cannot make the
        # updater misclassify the new CEO process as dead.
        provider_validation_started = engine.start_provider_validation_background() if allow_optional_api else False
        shell_integration = None
        if os.name == "nt":
            try:
                from ceo_core.windows_shell import ensure_modern_windows_shell
                shell_integration = ensure_modern_windows_shell(ROOT)
            except Exception as shell_exc:
                shell_integration = {"ok": False, "error": f"{type(shell_exc).__name__}: {shell_exc}"}
        write_status({
            "status": "PASS", "url": url, "port": port, "server": "stdlib-http.server",
            "browser": "pending", "execution_enabled": engine.execution_enabled,
            "provider_mode": engine.provider_mode, "key_source": key_source or "none",
            "results_dir": str(RESULTS), "startup_health": startup_health, "shell_integration": shell_integration,
            "provider_validation_started": provider_validation_started,
            "provider_validation_started": provider_validation_started,
            "message": "Backend, almacenamiento y frontend listos; navegador pendiente de apertura.",
        })
        browser = open_browser(url)
        write_status({
            "status": "PASS", "url": url, "port": port, "server": "stdlib-http.server",
            "browser": browser, "execution_enabled": engine.execution_enabled,
            "provider_mode": engine.provider_mode, "key_source": key_source or "none",
            "results_dir": str(RESULTS), "startup_health": startup_health, "shell_integration": shell_integration,
            "message": "CEO listo y navegador abierto tras health check local.",
        })
        print(f"\n[OK] CEO abierto: {url}")
        print(f"[OK] Estado: {STATUS_PATH}")
        print(f"[OK] Diagnostico persistente: {DIAGNOSTICS.latest_path}")
        if not engine.execution_enabled:
            print("[AVISO] Browser AI Worker no disponible: comprueba Chrome/Edge y los recursos de IA web.")
        else:
            print("[OK] Ejecucion IA disponible mediante navegador. API requerida: NO.")
        print("Mantén esta ventana abierta. Ctrl+C detiene el servidor.")
        try:
            while server_thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=3)
            try:
                engine.call(engine.shutdown(), timeout=30)
            except Exception:
                pass
        return 0
    except Exception as exc:
        write_failure(exc)
        print(f"\n[BLOCKED] {exc}")
        print(f"Diagnostico garantizado junto al lanzador: {FAILURE_PATH}")
        return 6
    finally:
        os.environ.pop("GEMINI_API_KEY", None)


if __name__ == "__main__":
    raise SystemExit(main())
