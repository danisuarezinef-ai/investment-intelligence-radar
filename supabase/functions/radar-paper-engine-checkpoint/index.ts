import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const EXPECTED_HASH="1e96928c7781f339732602234a1047fd510e38de04768d171884166ba5ae91e3";
const sb=createClient(Deno.env.get("SUPABASE_URL")!,Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,{auth:{persistSession:false}});

async function sha(value:string){const digest=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(value));return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,"0")).join("");}
function reply(status:number,payload:unknown){return new Response(JSON.stringify(payload),{status,headers:{"content-type":"application/json; charset=utf-8","cache-control":"no-store"}});}

function validCheckpoint(value:unknown){
  if(!value||typeof value!=="object")return false;
  const cp=value as Record<string,unknown>;
  const schema=Number(cp.schema_version);
  if(cp.real_trading!==false||![1,2].includes(schema))return false;
  if(typeof cp.state_hash!=="string"||String(cp.state_hash).length!==64)return false;
  if(!cp.tables||typeof cp.tables!=="object")return false;
  const tables=cp.tables as Record<string,unknown>;
  const core=["paper_agents","paper_agent_positions","paper_agent_trades","paper_agent_marks","champion_paper_account","champion_paper_positions","champion_paper_trades","champion_paper_marks"];
  if(core.some(k=>!Array.isArray(tables[k])))return false;
  if(schema===2&&!Array.isArray(tables.paper_decision_envelopes_local))return false;
  return true;
}

async function persist(node:string,body:Record<string,unknown>){
  const checkpoint=body.checkpoint;
  if(!validCheckpoint(checkpoint))throw new Error("invalid PAPER engine checkpoint");
  const cp=checkpoint as Record<string,unknown>;const schema=Number(cp.schema_version);
  const row={origin_node:node,observed_at:String(cp.observed_at||new Date().toISOString()),schema_version:schema,payload:cp,real_trading:false,updated_at:new Date().toISOString()};
  const {error}=await sb.from("radar_paper_engine_checkpoints").upsert(row,{onConflict:"origin_node"});
  if(error)throw error;
  return {ok:true,status:"PERSISTED_EXACT_PAPER_ENGINE",state_hash:String(cp.state_hash),schema_version:schema,observed_at:row.observed_at,can_trade:false,real_trading:false};
}

async function rehydrate(node:string){
  const {data,error}=await sb.from("radar_paper_engine_checkpoints").select("observed_at,schema_version,payload,real_trading").eq("origin_node",node).maybeSingle();
  if(error)throw error;
  if(!data)return {ok:true,status:"NO_DURABLE_PAPER_CHECKPOINT",checkpoint:null,backfill_used:false,reconstructed:false,can_trade:false,real_trading:false};
  if(data.real_trading!==false||![1,2].includes(Number(data.schema_version))||!validCheckpoint(data.payload))throw new Error("stored PAPER engine checkpoint failed safety validation");
  return {ok:true,status:"DURABLE_PAPER_CHECKPOINT_FOUND",checkpoint:data.payload,observed_at:data.observed_at,schema_version:Number(data.schema_version),backfill_used:false,reconstructed:false,can_trade:false,real_trading:false};
}

Deno.serve(async(req)=>{
  try{
    const token=req.headers.get("x-radar-token")||"";
    if(!token||await sha(token)!==EXPECTED_HASH)return reply(401,{ok:false,error:"unauthorized"});
    if(req.method!=="POST")return reply(405,{ok:false,error:"method_not_allowed"});
    const body=await req.json() as Record<string,unknown>;
    const node=String(body.node_id||"cloud-primary");
    const action=String(body.action||"");
    if(action==="persist_engine_checkpoint")return reply(200,await persist(node,body));
    if(action==="rehydrate_engine_checkpoint")return reply(200,await rehydrate(node));
    return reply(400,{ok:false,error:"unsupported_action",can_trade:false,real_trading:false});
  }catch(error){
    return reply(500,{ok:false,error:String((error as Error)?.message||error),backfill_used:false,reconstructed:false,can_trade:false,real_trading:false});
  }
});