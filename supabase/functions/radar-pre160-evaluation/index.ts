import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const EXPECTED_HASH="1e96928c7781f339732602234a1047fd510e38de04768d171884166ba5ae91e3";
const sb=createClient(Deno.env.get("SUPABASE_URL")!,Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,{auth:{persistSession:false}});
async function sha(v:string){const d=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(v));return [...new Uint8Array(d)].map(b=>b.toString(16).padStart(2,"0")).join("");}
function reply(status:number,payload:unknown){return new Response(JSON.stringify(payload),{status,headers:{"content-type":"application/json; charset=utf-8","cache-control":"no-store"}});}
function finite(v:unknown){const n=Number(v);return Number.isFinite(n)?n:null;}
function text(v:unknown){return v===null||v===undefined?null:String(v);}
function iso(v:unknown){const d=new Date(String(v||""));return Number.isNaN(d.getTime())?null:d.toISOString();}

async function ensureState(node:string){
  const {data,error}=await sb.from("radar_strategy_evaluation_state").select("*").eq("origin_node",node).maybeSingle();if(error)throw error;
  if(data)return data;
  const row={origin_node:node,capture_started_at:new Date().toISOString(),schema_version:1,updated_at:new Date().toISOString(),real_trading:false};
  const {data:created,error:createError}=await sb.from("radar_strategy_evaluation_state").insert(row).select("*").single();if(createError)throw createError;return created;
}

async function persist(node:string,body:Record<string,unknown>){
  if(body.real_trading!==false)throw new Error("real_trading boundary invalid");
  const state=await ensureState(node);const boundary=new Date(String(state.capture_started_at));const now=new Date().toISOString();
  const evaluations=Array.isArray(body.evaluations)?body.evaluations as Record<string,unknown>[]:[];let daily=0,decisions=0,prospective=0;
  for(const ev of evaluations){
    const key=String(ev.competitor_key||"");if(!key)continue;
    const observed=iso(ev.observed_at)||now;const day=observed.slice(0,10);const vc=(ev.v_components&&typeof ev.v_components==="object")?ev.v_components as Record<string,unknown>:{};
    const row={origin_node:node,competitor_key:key,day,observed_at:observed,v_score:finite(ev.v_score),v_confidence:finite(ev.v_confidence),
      decision_quality:finite(vc.decision_quality),risk_control:finite(vc.risk_control),generalization:finite(vc.generalization),
      stability_score:finite(ev.stability_score),transfer_score:finite(ev.transfer_score),anti_overfitting_score:finite(ev.anti_overfitting_score),
      data_quality_score:finite(ev.data_quality_score),promotion_readiness:finite(ev.promotion_readiness),evaluation:ev,real_trading:false};
    const {error}=await sb.from("radar_strategy_evaluation_daily").upsert(row,{onConflict:"origin_node,competitor_key,day"});if(error)throw error;daily++;
    const outcomes=Array.isArray(ev.closed_decisions)?ev.closed_decisions as Record<string,unknown>[]:[];
    for(const d of outcomes){
      const fp=String(d.decision_fingerprint||"");const exit=iso(d.exit_ts);const sym=String(d.symbol||"");if(!fp||!exit||!sym)continue;
      const eligible=new Date(exit)>=boundary;const outcome={origin_node:node,competitor_key:key,decision_fingerprint:fp,first_observed_at:now,
        entry_ts:iso(d.entry_ts),exit_ts:exit,symbol:sym,qty:finite(d.qty),entry_price:finite(d.entry_price),exit_price:finite(d.exit_price),
        entry_capital:finite(d.entry_capital),exit_value_net:finite(d.exit_value_net),realized_pnl:finite(d.realized_pnl),return_pct:finite(d.return_pct),
        costs:finite(d.costs),duration_hours:finite(d.duration_hours),outcome_class:text(d.outcome_class),entry_reason:text(d.entry_reason),exit_reason:text(d.exit_reason),
        evidence_class:eligible?"PROSPECTIVE_PAPER_CLOSE":"DERIVED_PREEXISTING",forward_eligible:eligible,payload:d,real_trading:false};
      const {error:oe}=await sb.from("radar_strategy_decision_outcomes").upsert(outcome,{onConflict:"origin_node,competitor_key,decision_fingerprint",ignoreDuplicates:true});if(oe)throw oe;
      decisions++;if(eligible)prospective++;
    }
  }
  await sb.from("radar_strategy_evaluation_state").update({updated_at:now}).eq("origin_node",node);
  return {ok:true,status:"PERSISTED_PRE160_EVALUATION",capture_started_at:state.capture_started_at,evaluations:daily,decision_rows_seen:decisions,prospective_rows_seen:prospective,can_trade:false,real_trading:false};
}

async function persistLesson(node:string,body:Record<string,unknown>){
  const lesson=(body.lesson&&typeof body.lesson==="object")?body.lesson as Record<string,unknown>:{};const id=String(lesson.lesson_id||"");if(!id)throw new Error("lesson_id required");
  const row={origin_node:node,lesson_id:id,subject:String(lesson.subject||""),claim:String(lesson.claim||""),status:String(lesson.status||"HYPOTHESIS"),
    created_at:iso(lesson.created_at)||new Date().toISOString(),updated_at:new Date().toISOString(),regime:text(lesson.regime),horizon:text(lesson.horizon),confidence:text(lesson.confidence),
    supporting_evidence:lesson.supporting_evidence||{},validation:lesson,real_trading:false};
  const {error}=await sb.from("radar_learning_journal").upsert(row,{onConflict:"origin_node,lesson_id"});if(error)throw error;
  return {ok:true,status:"LEARNING_JOURNAL_PERSISTED",lesson_id:id,automatic_strategy_change:false,can_trade:false,real_trading:false};
}

async function persistArchiveCandidate(node:string,body:Record<string,unknown>){
  const candidate=(body.candidate&&typeof body.candidate==="object")?body.candidate as Record<string,unknown>:{};
  const id=String(candidate.archive_id||candidate.candidate_id||"");const key=String(candidate.competitor_key||candidate.lineage||"");
  const kind=String(candidate.archive_kind||"");if(!id||!key||!["HALL_CANDIDATE","GRAVEYARD_CANDIDATE"].includes(kind))throw new Error("invalid archive candidate");
  const now=new Date().toISOString();const row={origin_node:node,candidate_id:id,competitor_key:key,archive_kind:kind,
    last_observed_at:now,eligible:candidate.eligible===true,reason:text(candidate.reason),payload:candidate,reviewed:false,applied:false,real_trading:false};
  const {data:existing,error:readError}=await sb.from("radar_strategy_archive_candidates").select("first_observed_at").eq("origin_node",node).eq("candidate_id",id).maybeSingle();if(readError)throw readError;
  const write={...row,first_observed_at:existing?.first_observed_at||now};
  const {error}=await sb.from("radar_strategy_archive_candidates").upsert(write,{onConflict:"origin_node,candidate_id"});if(error)throw error;
  return {ok:true,status:"ARCHIVE_CANDIDATE_PERSISTED",candidate_id:id,archive_kind:kind,applied:false,automatic_strategy_change:false,can_trade:false,real_trading:false};
}

async function status(node:string,days:number){
  const state=await ensureState(node);const since=new Date(Date.now()-Math.max(1,Math.min(365,days))*86400000).toISOString();
  const {data:daily,error}=await sb.from("radar_strategy_evaluation_daily").select("*").eq("origin_node",node).gte("observed_at",since).order("observed_at",{ascending:true});if(error)throw error;
  const {data:decisions,error:de}=await sb.from("radar_strategy_decision_outcomes").select("competitor_key,decision_fingerprint,first_observed_at,entry_ts,exit_ts,symbol,qty,entry_price,exit_price,entry_capital,exit_value_net,realized_pnl,return_pct,costs,duration_hours,outcome_class,entry_reason,exit_reason,evidence_class,forward_eligible,payload").eq("origin_node",node).gte("exit_ts",since).order("exit_ts",{ascending:false}).limit(500);if(de)throw de;
  const {data:lessons,error:le}=await sb.from("radar_learning_journal").select("lesson_id,subject,claim,status,created_at,updated_at,regime,horizon,confidence,validation").eq("origin_node",node).order("updated_at",{ascending:false}).limit(100);if(le)throw le;
  const {data:archive,error:ae}=await sb.from("radar_strategy_archive_candidates").select("candidate_id,competitor_key,archive_kind,first_observed_at,last_observed_at,eligible,reason,reviewed,applied,payload").eq("origin_node",node).order("last_observed_at",{ascending:false}).limit(100);if(ae)throw ae;
  return {ok:true,status:"PRE160_EVALUATION_AUTHORITY",capture_started_at:state.capture_started_at,daily:daily||[],decisions:decisions||[],lessons:lessons||[],archive_candidates:archive||[],backfilled:false,can_trade:false,real_trading:false};
}

Deno.serve(async(req)=>{
  try{
    const token=req.headers.get("x-radar-token")||"";if(!token||await sha(token)!==EXPECTED_HASH)return reply(401,{ok:false,error:"unauthorized"});
    if(req.method!=="POST")return reply(405,{ok:false,error:"method_not_allowed"});
    const body=await req.json() as Record<string,unknown>;const node=String(body.node_id||"cloud-primary");const action=String(body.action||"");
    if(action==="persist_pre160_evaluation")return reply(200,await persist(node,body));
    if(action==="persist_learning_lesson")return reply(200,await persistLesson(node,body));
    if(action==="persist_archive_candidate")return reply(200,await persistArchiveCandidate(node,body));
    if(action==="pre160_evaluation_status")return reply(200,await status(node,Number(body.days||30)));
    return reply(400,{ok:false,error:"unsupported_action",can_trade:false,real_trading:false});
  }catch(error){return reply(500,{ok:false,error:String((error as Error)?.message||error),can_trade:false,real_trading:false});}
});
