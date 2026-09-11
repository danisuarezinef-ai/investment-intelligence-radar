import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const EXPECTED_HASH="1e96928c7781f339732602234a1047fd510e38de04768d171884166ba5ae91e3";
const sb=createClient(Deno.env.get("SUPABASE_URL")!,Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,{auth:{persistSession:false}});

async function sha(value:string){const d=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(value));return [...new Uint8Array(d)].map(b=>b.toString(16).padStart(2,"0")).join("");}
function reply(status:number,payload:unknown){return new Response(JSON.stringify(payload),{status,headers:{"content-type":"application/json; charset=utf-8","cache-control":"no-store"}});}
function obj(v:unknown):Record<string,unknown>{return v&&typeof v==="object"&&!Array.isArray(v)?v as Record<string,unknown>:{};}
function arr(v:unknown):Record<string,unknown>[] {return Array.isArray(v)?v.filter(x=>x&&typeof x==="object") as Record<string,unknown>[]:[];}
function text(v:unknown){return v===null||v===undefined?null:String(v);}
function finite(v:unknown){const n=Number(v);return Number.isFinite(n)?n:null;}
function iso(v:unknown){const d=new Date(String(v||""));return Number.isNaN(d.getTime())?null:d.toISOString();}
function stable(v:unknown):unknown{if(Array.isArray(v))return v.map(stable);if(v&&typeof v==="object"){const x=v as Record<string,unknown>;return Object.fromEntries(Object.keys(x).sort().map(k=>[k,stable(x[k])]));}return v;}
function canonical(v:unknown){return JSON.stringify(stable(v));}

async function appendCheckpoint(node:string,snapshot:Record<string,unknown>){
  const observed=iso(snapshot.observed_at)||new Date().toISOString();const snapshotHash=String(snapshot.snapshot_hash||"");
  if(!snapshotHash)throw new Error("snapshot_hash required");
  const snapshotWithoutHash=Object.fromEntries(Object.entries(snapshot).filter(([k])=>k!=="snapshot_hash"));
  const expected=await sha(canonical(snapshotWithoutHash));if(expected!==snapshotHash)throw new Error("hardening snapshot hash mismatch");
  const {data:existing,error:xe}=await sb.from("radar_pre160_evidence_checkpoints").select("id,record_hash").eq("origin_node",node).eq("snapshot_hash",snapshotHash).maybeSingle();if(xe)throw xe;
  if(existing)return {appended:false,id:existing.id,record_hash:existing.record_hash,snapshot_hash:snapshotHash};
  const {data:tail,error:te}=await sb.from("radar_pre160_evidence_checkpoints").select("id,record_hash").eq("origin_node",node).order("id",{ascending:false}).limit(1).maybeSingle();if(te)throw te;
  const prev=tail?.record_hash?String(tail.record_hash):null;const payload={prev_hash:prev,origin_node:node,observed_at:observed,snapshot_hash:snapshotHash};const recordHash=await sha(canonical(payload));
  const {data:inserted,error:ie}=await sb.from("radar_pre160_evidence_checkpoints").insert({origin_node:node,observed_at:observed,snapshot_hash:snapshotHash,prev_hash:prev,record_hash:recordHash,snapshot,real_trading:false}).select("id").single();if(ie)throw ie;
  return {appended:true,id:inserted.id,record_hash:recordHash,snapshot_hash:snapshotHash};
}

async function freezeEnvelopes(node:string,envelopes:Record<string,unknown>[]){let seen=0,inserted=0,versionMissing=0;
  for(const env of envelopes){
    const source=String(env.source_key||"");const tradeId=Number(env.trade_id);const tradeTs=iso(env.trade_ts);const key=String(env.competitor_key||"");const symbol=String(env.symbol||"");const side=String(env.side||"");const fp=String(env.decision_fingerprint||"");const eh=String(env.envelope_hash||"");
    if(!source||!Number.isInteger(tradeId)||!tradeTs||!key||!symbol||!side||!fp||!eh)continue;seen++;
    if(!env.strategy_version)versionMissing++;
    const row={origin_node:node,source_key:source,trade_id:tradeId,trade_ts:tradeTs,competitor_key:key,strategy_identity:String(env.strategy_identity||key),strategy_version:text(env.strategy_version),decision_fingerprint:fp,
      symbol,side,regime_ts:iso(env.regime_ts),regime:text(env.regime),regime_confidence:finite(env.regime_confidence),benchmark_snapshot:obj(env.benchmark_snapshot),cost_snapshot:obj(env.cost_snapshot),provider_snapshot:obj(env.provider_snapshot),
      provenance:obj(env.provenance),envelope_hash:eh,payload:env,real_trading:false};
    const {data:existing,error:re}=await sb.from("radar_pre160_decision_envelopes").select("id").eq("origin_node",node).eq("source_key",source).eq("trade_id",tradeId).maybeSingle();if(re)throw re;
    if(existing)continue;
    const {error}=await sb.from("radar_pre160_decision_envelopes").insert(row);if(error)throw error;inserted++;
  }
  return {seen,inserted,strategy_versions_missing:versionMissing};
}

async function persistGuard(node:string,snapshot:Record<string,unknown>,checkpointId:number|null,checkpointHash:string|null){
  const g=obj(snapshot.guard_state);const row={origin_node:node,updated_at:new Date().toISOString(),last_checkpoint_id:checkpointId,last_checkpoint_hash:checkpointHash,
    consecutive_degraded_days:Number(g.consecutive_degraded_days||0),cooldown_until:g.cooldown_until||null,payload:g,real_trading:false};
  const {error}=await sb.from("radar_pre160_guard_state").upsert(row,{onConflict:"origin_node"});if(error)throw error;return row;
}

async function persist(node:string,body:Record<string,unknown>){
  if(body.real_trading!==false)throw new Error("real_trading boundary invalid");const snapshot=obj(body.snapshot);if(snapshot.real_trading!==false)throw new Error("snapshot real_trading boundary invalid");
  const checkpoint=await appendCheckpoint(node,snapshot);const envelopes=await freezeEnvelopes(node,arr(snapshot.envelopes_to_freeze));await persistGuard(node,snapshot,Number(checkpoint.id||0)||null,checkpoint.record_hash?String(checkpoint.record_hash):null);
  return {ok:true,status:"PRE160_HARDENING_PERSISTED",checkpoint,envelopes,setup_allowed:false,automatic_release:false,automatic_promotion:false,automatic_demotion:false,can_trade:false,real_trading:false};
}

async function status(node:string,limit:number){
  const lim=Math.max(1,Math.min(2000,limit||500));
  const {data:checkpoints,error:ce}=await sb.from("radar_pre160_evidence_checkpoints").select("id,origin_node,observed_at,snapshot_hash,prev_hash,record_hash,snapshot,real_trading").eq("origin_node",node).order("id",{ascending:true}).limit(lim);if(ce)throw ce;
  const {data:envelopes,error:ee}=await sb.from("radar_pre160_decision_envelopes").select("id,source_key,trade_id,trade_ts,competitor_key,strategy_identity,strategy_version,decision_fingerprint,symbol,side,regime_ts,regime,regime_confidence,benchmark_snapshot,cost_snapshot,provider_snapshot,provenance,envelope_hash,payload,real_trading").eq("origin_node",node).order("trade_ts",{ascending:false}).limit(lim);if(ee)throw ee;
  const {data:guard,error:ge}=await sb.from("radar_pre160_guard_state").select("*").eq("origin_node",node).maybeSingle();if(ge)throw ge;
  let prev:string|null=null;let integrity=true;
  for(const row of checkpoints||[]){if((row.prev_hash||null)!==prev){integrity=false;break;}const payload={prev_hash:row.prev_hash||null,origin_node:row.origin_node,observed_at:new Date(row.observed_at).toISOString(),snapshot_hash:row.snapshot_hash};const computed=await sha(canonical(payload));if(computed!==row.record_hash){integrity=false;break;}prev=String(row.record_hash);}
  const missingVersion=(envelopes||[]).filter(x=>!x.strategy_version).length;
  return {ok:true,status:"PRE160_HARDENING_AUTHORITY",checkpoints:checkpoints||[],checkpoint_records:(checkpoints||[]).length,checkpoint_integrity:integrity?"VERIFIED":"FAILED",envelopes:envelopes||[],envelope_records:(envelopes||[]).length,strategy_versions_missing:missingVersion,guard:guard||null,
    setup_allowed:false,automatic_release:false,automatic_promotion:false,automatic_demotion:false,can_trade:false,real_trading:false};
}

Deno.serve(async(req)=>{try{
  const token=req.headers.get("x-radar-token")||"";if(!token||await sha(token)!==EXPECTED_HASH)return reply(401,{ok:false,error:"unauthorized"});if(req.method!=="POST")return reply(405,{ok:false,error:"method_not_allowed"});
  const body=await req.json() as Record<string,unknown>;const node=String(body.node_id||"cloud-primary");const action=String(body.action||"");
  if(action==="persist_hardening_snapshot")return reply(200,await persist(node,body));if(action==="hardening_status")return reply(200,await status(node,Number(body.limit||500)));
  return reply(400,{ok:false,error:"unsupported_action",setup_allowed:false,can_trade:false,real_trading:false});
}catch(error){return reply(500,{ok:false,error:String((error as Error)?.message||error),setup_allowed:false,can_trade:false,real_trading:false});}});
