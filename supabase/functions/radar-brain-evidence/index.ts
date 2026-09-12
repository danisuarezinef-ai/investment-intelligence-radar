import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
const EXPECTED_HASH="1e96928c7781f339732602234a1047fd510e38de04768d171884166ba5ae91e3";
const sb=createClient(Deno.env.get("SUPABASE_URL")!,Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,{auth:{persistSession:false}});
async function sha(s:string){const d=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(s));return [...new Uint8Array(d)].map(b=>b.toString(16).padStart(2,"0")).join("")}
function res(code:number,p:any){return new Response(JSON.stringify(p),{status:code,headers:{"content-type":"application/json; charset=utf-8","cache-control":"no-store"}})}
Deno.serve(async(req)=>{const started=Date.now();try{
  const token=req.headers.get("x-radar-token")||"";if(!token||await sha(token)!==EXPECTED_HASH)return res(401,{ok:false,error:"unauthorized"});
  if(req.method!=="POST")return res(405,{ok:false,error:"method_not_allowed"});
  const b=await req.json().catch(()=>({}));const action=String(b.action||"");
  if(action==="put"){
    const x=b.snapshot||{};if(!x.id||!x.kind||!x.payload_hash||!x.payload)throw new Error("invalid snapshot");
    if(x.real_trading!==false)throw new Error("real_trading must be false");
    const {data:existing,error:qe}=await sb.from("radar_brain_evidence_snapshots").select("id,payload_hash").eq("id",String(x.id)).maybeSingle();if(qe)throw qe;
    if(existing&&existing.payload_hash!==String(x.payload_hash))throw new Error("content-address collision");
    if(!existing){const {error}=await sb.from("radar_brain_evidence_snapshots").insert({id:String(x.id),kind:String(x.kind),observed_at:x.observed_at||new Date().toISOString(),source_max_evaluated_at:x.source_max_evaluated_at||null,payload:x.payload,payload_hash:String(x.payload_hash),origin_deployment:x.origin_deployment||null,real_trading:false});if(error)throw error}
    return res(200,{ok:true,action,id:String(x.id),inserted:!existing,edge_ms:Date.now()-started,real_trading:false});
  }
  if(action==="latest"){
    const kind=String(b.kind||"").trim();if(!kind)throw new Error("kind required");const limit=Math.max(1,Math.min(50,Number(b.limit||10)));
    const {data,error}=await sb.from("radar_brain_evidence_snapshots").select("id,kind,observed_at,source_max_evaluated_at,payload,payload_hash,origin_deployment,real_trading").eq("kind",kind).order("observed_at",{ascending:false}).limit(limit);if(error)throw error;
    return res(200,{ok:true,action,items:data||[],edge_ms:Date.now()-started,real_trading:false});
  }
  if(action==="stats"){
    const {count,error}=await sb.from("radar_brain_evidence_snapshots").select("id",{count:"exact",head:true});if(error)throw error;
    return res(200,{ok:true,action,count:count||0,durable_backend:"SUPABASE",edge_ms:Date.now()-started,real_trading:false});
  }
  return res(400,{ok:false,error:"unknown_action",edge_ms:Date.now()-started,real_trading:false});
}catch(e){return res(500,{ok:false,error:String((e as any)?.message||e),edge_ms:Date.now()-started,real_trading:false})}});
