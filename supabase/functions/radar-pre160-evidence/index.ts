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

async function freezeContexts(node:string,contexts:Record<string,unknown>[]){let inserted=0,seen=0;
  for(const raw of contexts){
    const source=String(raw.source_key||"");const tradeId=Number(raw.trade_id);const tradeTs=iso(raw.trade_ts);const key=String(raw.competitor_key||"");const symbol=String(raw.symbol||"");const side=String(raw.side||"");
    if(!source||!Number.isInteger(tradeId)||!tradeTs||!key||!symbol||!side)continue;seen++;
    const row={origin_node:node,source_key:source,trade_id:tradeId,trade_ts:tradeTs,competitor_key:key,symbol,side,
      regime_ts:iso(raw.regime_ts),regime:text(raw.regime),regime_confidence:finite(raw.regime_confidence),regime_features:obj(raw.regime_features),
      status:String(raw.status||"PIT_REGIME_NOT_CAPTURED"),payload:raw,real_trading:false};
    const {error}=await sb.from("radar_pre160_decision_contexts").upsert(row,{onConflict:"origin_node,source_key,trade_id",ignoreDuplicates:true});if(error)throw error;inserted++;
  }
  return {seen,inserted};
}

async function appendProspectiveChain(node:string){
  const {data:decisions,error}=await sb.from("radar_strategy_decision_outcomes")
    .select("competitor_key,decision_fingerprint,exit_ts,symbol,realized_pnl,return_pct,costs,evidence_class,forward_eligible,payload")
    .eq("origin_node",node).eq("forward_eligible",true).eq("evidence_class","PROSPECTIVE_PAPER_CLOSE").order("exit_ts",{ascending:true}).limit(1000);if(error)throw error;
  let appended=0;
  for(const d of decisions||[]){
    const fp=String(d.decision_fingerprint||"");if(!fp)continue;
    const {data:exists,error:ee}=await sb.from("radar_pre160_evidence_chain").select("id").eq("origin_node",node).eq("decision_fingerprint",fp).maybeSingle();if(ee)throw ee;if(exists)continue;
    const {data:tail,error:te}=await sb.from("radar_pre160_evidence_chain").select("record_hash").eq("origin_node",node).order("id",{ascending:false}).limit(1).maybeSingle();if(te)throw te;
    const prev=tail?.record_hash?String(tail.record_hash):null;
    const body={prev_hash:prev,origin_node:node,decision_fingerprint:fp,competitor_key:String(d.competitor_key||""),exit_ts:iso(d.exit_ts),symbol:String(d.symbol||""),realized_pnl:finite(d.realized_pnl),return_pct:finite(d.return_pct),costs:finite(d.costs),payload:d.payload||{}};
    const recordHash=await sha(canonical(body));
    const {error:ie}=await sb.from("radar_pre160_evidence_chain").insert({origin_node:node,decision_fingerprint:fp,competitor_key:body.competitor_key,exit_ts:body.exit_ts,prev_hash:prev,record_hash:recordHash,payload:body,real_trading:false});
    if(ie){if(String(ie.message||"").toLowerCase().includes("duplicate"))continue;throw ie;}appended++;
  }
  return {eligible:(decisions||[]).length,appended};
}

async function persistSnapshot(node:string,body:Record<string,unknown>){
  if(body.real_trading!==false)throw new Error("real_trading boundary invalid");const snapshot=obj(body.snapshot);if(snapshot.real_trading!==false)throw new Error("snapshot real_trading boundary invalid");
  const observed=iso(snapshot.observed_at)||new Date().toISOString();const day=observed.slice(0,10);const contexts=arr(snapshot.contexts_to_freeze);const frozen=await freezeContexts(node,contexts);const chain=await appendProspectiveChain(node);
  const readiness=obj(snapshot.readiness_1_6);const blockers=Array.isArray(readiness.blockers)?readiness.blockers:[];const clientHash=String(snapshot.snapshot_hash||"");
  const serverHash=await sha(canonical(Object.fromEntries(Object.entries(snapshot).filter(([k])=>k!=="snapshot_hash"))));
  const {data:existing,error:re}=await sb.from("radar_pre160_evidence_daily").select("first_observed_at").eq("origin_node",node).eq("day",day).maybeSingle();if(re)throw re;
  const row={origin_node:node,day,first_observed_at:existing?.first_observed_at||observed,last_observed_at:observed,snapshot_hash:serverHash,
    readiness_score:finite(readiness.score_pct),blockers,snapshot,audit:{contexts:frozen,chain,client_snapshot_hash:clientHash,server_snapshot_hash:serverHash,setup_allowed:false,automatic_release:false},real_trading:false};
  const {error:we}=await sb.from("radar_pre160_evidence_daily").upsert(row,{onConflict:"origin_node,day"});if(we)throw we;
  return {ok:true,status:"PRE160_EVIDENCE_PERSISTED",day,snapshot_hash:serverHash,client_snapshot_hash:clientHash,contexts:frozen,chain,setup_allowed:false,can_trade:false,real_trading:false};
}

async function evidenceStatus(node:string,days:number){
  const since=new Date(Date.now()-Math.max(1,Math.min(365,days))*86400000).toISOString().slice(0,10);
  const {data:daily,error:de}=await sb.from("radar_pre160_evidence_daily").select("*").eq("origin_node",node).gte("day",since).order("day",{ascending:true});if(de)throw de;
  const {data:contexts,error:ce}=await sb.from("radar_pre160_decision_contexts").select("*").eq("origin_node",node).order("trade_ts",{ascending:false}).limit(1000);if(ce)throw ce;
  const {data:chain,error:he}=await sb.from("radar_pre160_evidence_chain").select("id,decision_fingerprint,competitor_key,exit_ts,observed_at,prev_hash,record_hash,payload,real_trading").eq("origin_node",node).order("id",{ascending:true}).limit(2000);if(he)throw he;
  let valid=true;let prev:string|null=null;
  for(const row of chain||[]){if((row.prev_hash||null)!==prev){valid=false;break;}const p=obj(row.payload);const computed=await sha(canonical(p));if(computed!==row.record_hash){valid=false;break;}prev=String(row.record_hash);}
  return {ok:true,status:"PRE160_EVIDENCE_AUTHORITY",daily:daily||[],contexts:contexts||[],chain:chain||[],chain_integrity:valid?"VERIFIED":"FAILED",chain_records:(chain||[]).length,
    backfilled:false,setup_allowed:false,automatic_release:false,can_trade:false,real_trading:false};
}

Deno.serve(async(req)=>{try{
  const token=req.headers.get("x-radar-token")||"";if(!token||await sha(token)!==EXPECTED_HASH)return reply(401,{ok:false,error:"unauthorized"});if(req.method!=="POST")return reply(405,{ok:false,error:"method_not_allowed"});
  const body=await req.json() as Record<string,unknown>;const node=String(body.node_id||"cloud-primary");const action=String(body.action||"");
  if(action==="persist_evidence_snapshot")return reply(200,await persistSnapshot(node,body));if(action==="evidence_status")return reply(200,await evidenceStatus(node,Number(body.days||90)));
  return reply(400,{ok:false,error:"unsupported_action",setup_allowed:false,can_trade:false,real_trading:false});
}catch(error){return reply(500,{ok:false,error:String((error as Error)?.message||error),setup_allowed:false,can_trade:false,real_trading:false});}});
