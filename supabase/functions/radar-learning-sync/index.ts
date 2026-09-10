import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const EXPECTED_HASH = "1e96928c7781f339732602234a1047fd510e38de04768d171884166ba5ae91e3";
const sb = createClient(Deno.env.get("SUPABASE_URL")!,Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,{auth:{persistSession:false}});
const INSERT_ONLY_TABLES=["predictions","learning_cycles","model_evaluations","market_regimes","causal_edges","thesis_history","portfolio_recommendations","signal_weak_events","audit_events","historical_lab_runs","historical_fold_results","historical_challenger_results","brain_evidence","brain_transfer","brain_vault_events","brain_generation_runs","decision_research_ledger","decision_committee_votes","decision_negative_results","decision_audit_bundles"] as const;

async function sha(value:string){const digest=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(value));return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,"0")).join("");}
function response(status:number,payload:unknown){return new Response(JSON.stringify(payload),{status,headers:{"content-type":"application/json; charset=utf-8","cache-control":"no-store"}});}
function rows(body:Record<string,unknown>,table:string,node:string){const input=Array.isArray(body[table])?(body[table] as Record<string,unknown>[]).slice(0,2000):[];return input.map(row=>({...row,origin_node:row.origin_node||node}));}
async function insertOnly(table:string,input:Record<string,unknown>[]){if(!input.length)return 0;const {error}=await sb.from(table).upsert(input,{onConflict:table==="predictions"?"origin_node,origin_id,horizon":"origin_node,origin_id",ignoreDuplicates:true});if(error)throw new Error(`${table}: ${error.message}`);return input.length;}
async function converge(table:string,input:Record<string,unknown>[],naturalKey:string){if(!input.length)return 0;const {error}=await sb.from(table).upsert(input,{onConflict:naturalKey});if(error)throw new Error(`${table}: ${error.message}`);return input.length;}
function observedAt(row:Record<string,unknown>){return String(row.finished_at||row.completed_at||row.started_at||row.ts||row.updated_at||row.created_at||new Date().toISOString());}

async function persistAutonomy(body:Record<string,unknown>,node:string){
  const state=(body.state&&typeof body.state==="object")?body.state as Record<string,unknown>:null;
  if(state){const {error}=await sb.from("radar_autonomy_state").upsert({origin_node:node,updated_at:String(state.updated_at||new Date().toISOString()),payload:state,real_trading:false},{onConflict:"origin_node"});if(error)throw error;}
  const specs=[["runs","radar_autonomy_runs"],["experiments","radar_autonomy_experiments"],["soak_ticks","radar_autonomy_soak_ticks"]] as const;
  const out:Record<string,unknown>={ok:true,state:state?1:0};
  for(const [key,table] of specs){const input=Array.isArray(body[key])?(body[key] as Record<string,unknown>[]).slice(0,2000):[];const packed=input.filter(r=>r&&r.id!=null).map(r=>({origin_node:node,origin_id:String(r.id),observed_at:observedAt(r),payload:r,real_trading:false}));if(packed.length){const {error}=await sb.from(table).upsert(packed,{onConflict:"origin_node,origin_id"});if(error)throw error;}out[key]=packed.length;}
  return out;
}

async function paperEquityDaily(body:Record<string,unknown>,node:string){
  const requested=Number(body.days||30);const days=Math.min(90,Math.max(1,Number.isFinite(requested)?Math.trunc(requested):30));
  const {data,error}=await sb.rpc("radar_paper_equity_daily",{p_days:days,p_origin_node:node});
  if(error)throw new Error(`paper_equity_daily: ${error.message}`);
  return {ok:true,action:"paper_equity_daily",window_days:days,daily_equity:data||[],source:"SUPABASE_PERSISTED_PAPER_AGENT_MARKS",backfilled:false,reconstructed:false,real_trading:false};
}

async function rehydrate(node:string){
  const {data:forward,error:fe}=await sb.from("decision_forward_ledger").select("origin_node,origin_id,created_at,symbol,horizon,target_date,model_version,prediction_hash,payload,outcome,evaluated_at,local_prediction_id,feature_fingerprint,thesis_fingerprint,confidence,uncertainty,decision_state,paper_allocation,data_cutoff,known_at_boundary,provenance_snapshot").order("created_at",{ascending:true}).limit(5000);if(fe)throw fe;
  const {data:state,error:se}=await sb.from("radar_autonomy_state").select("payload").eq("origin_node",node).limit(1);if(se)throw se;
  async function exact(table:string){const {data,error}=await sb.from(table).select("payload").eq("origin_node",node).order("observed_at",{ascending:true}).limit(5000);if(error)throw error;return data||[];}
  return {ok:true,action:"rehydrate_authority",decision_forward_ledger:forward||[],autonomy_state:state||[],autonomy_runs:await exact("radar_autonomy_runs"),autonomy_experiments:await exact("radar_autonomy_experiments"),autonomy_soak_ticks:await exact("radar_autonomy_soak_ticks"),backfill_used:false,reconstructed:false,real_trading:false};
}

Deno.serve(async(req)=>{
 try{
  const token=req.headers.get("x-radar-token")||"";if(!token||await sha(token)!==EXPECTED_HASH)return response(401,{ok:false,error:"unauthorized"});if(req.method!=="POST")return response(405,{ok:false,error:"method_not_allowed"});
  const body=await req.json() as Record<string,unknown>;const node=String(body.node_id||"cloud-primary");const action=String(body.action||"sync");
  if(action==="rehydrate_authority")return response(200,await rehydrate(node));
  if(action==="persist_autonomy")return response(200,await persistAutonomy(body,node));
  if(action==="paper_equity_daily")return response(200,await paperEquityDaily(body,node));
  const out:Record<string,unknown>={ok:true};
  const models=rows(body,"model_versions",node);if(models.length){const {error}=await sb.from("model_versions").upsert(models,{onConflict:"version"});if(error)throw new Error(`model_versions: ${error.message}`);}out.model_versions=models.length;
  for(const table of INSERT_ONLY_TABLES){const input=rows(body,table,node);out[table]=await insertOnly(table,input);}
  for(const [table,key] of [["brain_lineages","lineage"],["brain_meta_methods","method"],["brain_vault_registry","vault_key"],["brain_hall_of_fame","lineage"],["brain_graveyard","lineage"]] as const){const input=rows(body,table,node);out[table]=await converge(table,input,key);}
  const reputation=rows(body,"source_reputation_dimensions",node).map(({origin_node:_node,origin_id:_id,...row})=>row);if(reputation.length){const {error}=await sb.from("source_reputation_dimensions").upsert(reputation,{onConflict:"source,topic,horizon"});if(error)throw new Error(`source_reputation_dimensions: ${error.message}`);}out.source_reputation_dimensions=reputation.length;
  const outcomes=rows(body,"prediction_outcomes",node);let outcomeCount=0;for(const outcome of outcomes){const {data:prediction,error:findError}=await sb.from("predictions").select("id").eq("origin_node",outcome.origin_node).eq("origin_id",outcome.prediction_id).eq("horizon",outcome.horizon).maybeSingle();if(findError)throw findError;if(!prediction)continue;const row={...outcome,prediction_id:prediction.id};const {error}=await sb.from("prediction_outcomes").upsert(row,{onConflict:"origin_node,origin_id",ignoreDuplicates:true});if(error)throw error;outcomeCount++;}out.prediction_outcomes=outcomeCount;
  const forward=rows(body,"decision_forward_ledger",node);let forwardOutcomes=0;if(forward.length){const inserts=forward.map(({outcome:_outcome,evaluated_at:_evaluated,...row})=>row);const {error}=await sb.from("decision_forward_ledger").upsert(inserts,{onConflict:"origin_node,origin_id",ignoreDuplicates:true});if(error)throw new Error(`decision_forward_ledger: ${error.message}`);for(const item of forward){if(item.outcome==null)continue;const {error:updateError}=await sb.from("decision_forward_ledger").update({outcome:item.outcome,evaluated_at:item.evaluated_at}).eq("origin_node",item.origin_node).eq("origin_id",item.origin_id).is("outcome",null);if(updateError)throw new Error(`decision_forward_outcome: ${updateError.message}`);forwardOutcomes++;}}out.decision_forward_ledger=forward.length;out.decision_forward_outcomes=forwardOutcomes;
  const thesis=rows(body,"decision_thesis_events",node);out.decision_thesis_events=await insertOnly("decision_thesis_events",thesis);
  const shadow=rows(body,"brain_shadow_predictions",node);let shadowOutcomes=0;if(shadow.length){const inserts=shadow.map(({outcome:_outcome,evaluated_at:_evaluated,...row})=>row);const {error}=await sb.from("brain_shadow_predictions").upsert(inserts,{onConflict:"origin_node,origin_id",ignoreDuplicates:true});if(error)throw new Error(`brain_shadow_predictions: ${error.message}`);for(const item of shadow){if(item.outcome==null)continue;const {error:updateError}=await sb.from("brain_shadow_predictions").update({outcome:item.outcome,evaluated_at:item.evaluated_at}).eq("origin_node",item.origin_node).eq("origin_id",item.origin_id).is("outcome",null);if(updateError)throw new Error(`brain_shadow_outcome: ${updateError.message}`);shadowOutcomes++;}}out.brain_shadow_predictions=shadow.length;out.brain_shadow_outcomes=shadowOutcomes;
  return response(200,out);
 }catch(error){return response(500,{ok:false,error:String((error as Error)?.message||error)});}
});
