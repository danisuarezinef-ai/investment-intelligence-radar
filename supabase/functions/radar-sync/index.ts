import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const EXPECTED_HASH="1e96928c7781f339732602234a1047fd510e38de04768d171884166ba5ae91e3";
const sb=createClient(Deno.env.get("SUPABASE_URL")!,Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,{auth:{persistSession:false}});
const WRITE_CONCURRENCY=20;
const READ_CHUNK=100;
const WRITE_CHUNK=100;

async function sha(s:string){const d=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(s));return [...new Uint8Array(d)].map(b=>b.toString(16).padStart(2,"0")).join("")}
function res(code:number,p:any){return new Response(JSON.stringify(p),{status:code,headers:{"content-type":"application/json; charset=utf-8","cache-control":"no-store"}})}
function sameNumeric(a:any,b:any,tolerance=1e-6){if(a==null||b==null)return a==null&&b==null;const x=Number(a),y=Number(b);return Number.isFinite(x)&&Number.isFinite(y)&&Math.abs(x-y)<=tolerance}
function chunks<T>(items:T[],size=WRITE_CHUNK){const out:T[][]=[];for(let i=0;i<items.length;i+=Math.max(1,size))out.push(items.slice(i,i+Math.max(1,size)));return out}
async function mapConcurrent<T,R>(items:T[],limit:number,fn:(item:T)=>Promise<R>):Promise<R[]>{const out:R[]=[];const size=Math.max(1,Math.min(50,Number(limit)||1));for(let i=0;i<items.length;i+=size){const chunk=items.slice(i,i+size);out.push(...await Promise.all(chunk.map(fn)))}return out}
async function agentMap(){const {data,error}=await sb.from("paper_agents").select("id,slug");if(error)throw error;const m:any={};for(const r of data||[])m[r.slug]=r.id;return m}
async function bulkUpsert(table:string,input:any[],options:any){let written=0;for(const chunk of chunks(input)){const {error}=await sb.from(table).upsert(chunk,options);if(error)throw error;written+=chunk.length}return written}
async function bulkInsert(table:string,input:any[]){let written=0;for(const chunk of chunks(input)){const {error}=await sb.from(table).insert(chunk);if(error)throw error;written+=chunk.length}return written}

async function filterNewEvents(events:any[],node:string){
  const batchSeen=new Set<string>();const deduped:any[]=[];
  for(const x of events){
    if(!x?.title)continue;
    if(x.url){const k=String(x.source||"unknown")+"\u0000"+String(x.url);if(batchSeen.has(k))continue;batchSeen.add(k)}
    deduped.push(x);
  }
  const groups=new Map<string,Set<string>>();
  for(const x of deduped){if(!x.url)continue;const source=String(x.source||"unknown");if(!groups.has(source))groups.set(source,new Set());groups.get(source)!.add(String(x.url))}
  const jobs:{source:string,urls:string[]}[]=[];for(const [source,urls] of groups)for(const part of chunks([...urls],READ_CHUNK))jobs.push({source,urls:part});
  const found=await mapConcurrent(jobs,WRITE_CONCURRENCY,async job=>{const {data,error}=await sb.from("information_events").select("source,url").eq("source",job.source).in("url",job.urls);if(error)throw error;return data||[]});
  const existing=new Set<string>();for(const rows of found)for(const r of rows)existing.add(String(r.source)+"\u0000"+String(r.url));
  const fresh=deduped.filter(x=>!x.url||!existing.has(String(x.source||"unknown")+"\u0000"+String(x.url)));
  return fresh.map(x=>({ts:x.ts,source:x.source||"unknown",title:x.title,url:x.url||null,category:x.category||null,symbols:x.symbols||[],topic:x.topic||null,sentiment:x.sentiment??null,novelty:x.novelty??null,metadata:x.metadata||{},origin_node:x.origin_node||node,origin_id:x.origin_id??x.id??null}));
}

async function reconcilePortfolioMarks(rows:any[]){
  const byNatural=new Map<string,any>();
  for(const row of rows){const key=String(row.agent_id)+"\u0000"+String(row.ts);const prior=byNatural.get(key);if(prior){if(!sameNumeric(prior.equity,row.equity)||!sameNumeric(prior.cash,row.cash)||!sameNumeric(prior.invested,row.invested)||!sameNumeric(prior.drawdown,row.drawdown,1e-9))throw new Error(`portfolio_values duplicate batch mismatch agent=${row.agent_id} ts=${row.ts}`);continue}byNatural.set(key,row)}
  const unique=[...byNatural.values()];
  const byAgent=new Map<string,string[]>();for(const row of unique){const k=String(row.agent_id);if(!byAgent.has(k))byAgent.set(k,[]);byAgent.get(k)!.push(String(row.ts))}
  const naturalJobs:{agent:string,times:string[]}[]=[];for(const [agent,times] of byAgent)for(const part of chunks([...new Set(times)],READ_CHUNK))naturalJobs.push({agent,times:part});
  const naturalReads=await mapConcurrent(naturalJobs,WRITE_CONCURRENCY,async job=>{const {data,error}=await sb.from("portfolio_values").select("id,agent_id,ts,equity,cash,invested,drawdown,origin_node,origin_id").eq("agent_id",job.agent).in("ts",job.times);if(error)throw error;return data||[]});
  const existingNatural=new Map<string,any>();for(const batch of naturalReads)for(const r of batch)existingNatural.set(String(r.agent_id)+"\u0000"+String(r.ts),r);
  const fresh:any[]=[];let existingCount=0;
  for(const row of unique){const key=String(row.agent_id)+"\u0000"+String(row.ts);const existing=existingNatural.get(key);if(existing){existingCount++;if(!sameNumeric(existing.equity,row.equity)||!sameNumeric(existing.cash,row.cash)||!sameNumeric(existing.invested,row.invested)||!sameNumeric(existing.drawdown,row.drawdown,1e-9))throw new Error(`portfolio_values immutable mismatch agent=${row.agent_id} ts=${row.ts}`);continue}fresh.push(row)}
  const byOrigin=new Map<string,string[]>();for(const row of fresh){const node=String(row.origin_node);if(!byOrigin.has(node))byOrigin.set(node,[]);byOrigin.get(node)!.push(String(row.origin_id))}
  const originJobs:{node:string,ids:string[]}[]=[];for(const [node,ids] of byOrigin)for(const part of chunks([...new Set(ids)],READ_CHUNK))originJobs.push({node,ids:part});
  const originReads=await mapConcurrent(originJobs,WRITE_CONCURRENCY,async job=>{const {data,error}=await sb.from("portfolio_values").select("origin_node,origin_id").eq("origin_node",job.node).in("origin_id",job.ids);if(error)throw error;return data||[]});
  const originExisting=new Set<string>();for(const batch of originReads)for(const r of batch)originExisting.add(String(r.origin_node)+"\u0000"+String(r.origin_id));
  for(const row of fresh){const key=String(row.origin_node)+"\u0000"+String(row.origin_id);if(originExisting.has(key))throw new Error(`portfolio_values origin collision node=${row.origin_node} origin_id=${String(row.origin_id)}`)}
  const inserted=await bulkInsert("portfolio_values",fresh);
  return {input:rows.length,unique:unique.length,existing:existingCount,inserted,natural_query_batches:naturalJobs.length,origin_query_batches:originJobs.length};
}

Deno.serve(async(req)=>{const started=Date.now();try{
  const token=req.headers.get("x-radar-token")||"";if(!token||await sha(token)!==EXPECTED_HASH)return res(401,{ok:false,error:"unauthorized"});
  if(req.method==="GET"){const [{count:market},{count:events},{count:runs},{count:alerts},{data:agents}]=await Promise.all([sb.from("market_snapshots").select("id",{count:"exact",head:true}),sb.from("information_events").select("id",{count:"exact",head:true}),sb.from("system_runs").select("id",{count:"exact",head:true}),sb.from("silence_alerts").select("id",{count:"exact",head:true}),sb.from("paper_agents").select("slug,name,profile,initial_cash,cash,enabled,updated_at,last_rebalance").order("slug")]);return res(200,{ok:true,counts:{market:market||0,events:events||0,runs:runs||0,alerts:alerts||0},agents:agents||[],edge_ms:Date.now()-started})}
  if(req.method!=="POST")return res(405,{ok:false,error:"method_not_allowed"});
  const b=await req.json().catch(()=>({}));const node=String(b.node_id||"cloud");const out:any={ok:true,write_concurrency:WRITE_CONCURRENCY,read_chunk:READ_CHUNK,write_chunk:WRITE_CHUNK};
  const market=Array.isArray(b.market_snapshots)?b.market_snapshots.slice(0,1000):[];if(market.length){const rows=market.map((x:any)=>({ts:x.ts,symbol:x.symbol,price:x.price,volume:x.volume??null,source:x.source||"unknown",currency:x.currency??null,metadata:x.metadata||{},origin_node:x.origin_node||node,origin_id:x.origin_id??x.id??null}));out.market_snapshots=await bulkUpsert("market_snapshots",rows,{onConflict:"origin_node,origin_id",ignoreDuplicates:true})}
  const rawEvents=Array.isArray(b.information_events)?b.information_events.slice(0,1000):[];if(rawEvents.length){const rows=await filterNewEvents(rawEvents,node);out.information_events=await bulkUpsert("information_events",rows,{onConflict:"origin_node,origin_id",ignoreDuplicates:true});out.information_events_existing_or_duplicate=rawEvents.length-rows.length}
  const runs=Array.isArray(b.system_runs)?b.system_runs.slice(0,1000):[];if(runs.length){const rows=runs.map((x:any)=>({ts:x.ts,node_id:x.node_id||b.node_id||null,kind:x.kind||x.job||"unknown",status:x.status||"unknown",message:x.message||x.detail||null,metrics:x.metrics||{},origin_node:x.origin_node||node,origin_id:x.origin_id??x.id??null}));out.system_runs=await bulkUpsert("system_runs",rows,{onConflict:"origin_node,origin_id",ignoreDuplicates:true})}
  const reps=Array.isArray(b.source_reputation)?b.source_reputation:[];if(reps.length){const rows=reps.map((r:any)=>({source:r.source,topic:r.topic||"global",horizon:r.horizon||"global",observations:r.events??r.observations??0,hits:r.actionable??r.hits??0,misses:Math.max(0,Number(r.events??r.observations??0)-Number(r.actionable??r.hits??0)),score:r.score??0,lead_time_hours:r.lead_time_hours??null,updated_at:r.updated_at||new Date().toISOString(),metadata:{avg_abs_move:r.avg_abs_move??null,precision_proxy:r.precision_proxy??null,confidence:r.confidence??null}})).filter((r:any)=>r.source);out.source_reputation=await bulkUpsert("source_reputation",rows,{onConflict:"source,topic,horizon"})}
  const alerts=Array.isArray(b.silence_alerts)?b.silence_alerts.slice(0,1000):[];if(alerts.length){const rows=alerts.map((a:any)=>({created_at:a.ts||a.created_at||new Date().toISOString(),symbol:a.symbol,severity:a.severity||(Math.abs(Number(a.z_score||a.zscore||0))>=3?"HIGH":"MEDIUM"),zscore:a.z_score??a.zscore??null,price_change:a.return_pct??a.price_change??null,volume_anomaly:a.volume_anomaly??null,catalyst_found:Boolean(a.recent_public_catalyst??a.catalyst_found??false),status:String(a.status||"OPEN").toLowerCase(),explanation:a.detail||a.explanation||null,metadata:a.metadata||{},origin_node:a.origin_node||node,origin_id:a.origin_id??a.id??null})).filter((a:any)=>a.symbol);out.silence_alerts=await bulkUpsert("silence_alerts",rows,{onConflict:"origin_node,origin_id",ignoreDuplicates:true})}
  const notifs=Array.isArray(b.notifications)?b.notifications.slice(0,1000):[];if(notifs.length){const rows=notifs.map((n:any)=>({created_at:n.ts||n.created_at||new Date().toISOString(),kind:n.kind||"info",severity:n.severity||"info",title:n.title||"Radar",body:n.body||null,read_at:n.read?(n.read_at||n.ts||new Date().toISOString()):null,metadata:{symbol:n.symbol??null,dedupe_key:n.dedupe_key??null},origin_node:n.origin_node||node,origin_id:n.origin_id??n.id??null}));out.notifications=await bulkUpsert("notifications",rows,{onConflict:"origin_node,origin_id",ignoreDuplicates:true})}
  const agents=Array.isArray(b.paper_agents)?b.paper_agents:[];if(agents.length){const rows=agents.map((a:any)=>({slug:a.agent_id||a.slug,name:a.name||a.agent_id||a.slug,profile:a.strategy||a.profile||a.agent_id||a.slug,initial_cash:a.initial_cash??a.initial??200,cash:a.cash??a.initial_cash??200,enabled:a.enabled!==false&&a.enabled!==0,last_rebalance:a.last_rebalance||null,updated_at:new Date().toISOString(),settings:a.settings||{}}));out.paper_agents=await bulkUpsert("paper_agents",rows,{onConflict:"slug"})}
  const amap=await agentMap();
  const pos=Array.isArray(b.paper_positions)?b.paper_positions:[];if(pos.length){const rows=pos.map((p:any)=>({agent_id:amap[p.agent_id],symbol:p.symbol,qty:p.qty,avg_price:p.avg_price,updated_at:p.updated_at||new Date().toISOString()})).filter((p:any)=>p.agent_id&&p.symbol);out.paper_positions=await bulkUpsert("paper_positions",rows,{onConflict:"agent_id,symbol"})}
  const trades=Array.isArray(b.paper_trades)?b.paper_trades.slice(0,1000):[];if(trades.length){const rows=trades.map((t:any)=>({agent_id:amap[t.agent_id],ts:t.ts,symbol:t.symbol,side:String(t.side||'').toUpperCase(),qty:t.qty,price:t.price,fee:t.fees??t.fee??0,spread_cost:t.spread_cost??0,fx_cost:t.fx_cost??0,reason:t.reason||null,metadata:{gross_value:t.gross_value??null},origin_node:t.origin_node||node,origin_id:t.origin_id??t.id??null})).filter((t:any)=>t.agent_id&&t.symbol&&(t.side==='BUY'||t.side==='SELL'));out.paper_trades=await bulkUpsert("paper_trades",rows,{onConflict:"origin_node,origin_id",ignoreDuplicates:true})}
  const rawMarks=Array.isArray(b.portfolio_values)?b.portfolio_values.slice(0,1000):[];const mappedMarks=rawMarks.map((m:any)=>({agent_id:amap[m.agent_id],ts:m.ts,equity:m.total??m.equity,cash:m.cash,invested:m.invested??0,drawdown:m.drawdown_pct??m.drawdown??null,sharpe:m.sharpe??null,benchmark_value:m.benchmark_value??null,origin_node:m.origin_node||node,origin_id:m.origin_id??m.id??null})).filter((m:any)=>m.agent_id&&m.equity!=null&&m.cash!=null);if(mappedMarks.length)out.portfolio_values=await reconcilePortfolioMarks(mappedMarks);
  const nodes=Array.isArray(b.nodes)?b.nodes:[];if(nodes.length){await mapConcurrent(nodes,WRITE_CONCURRENCY,async(n:any)=>{if(!n?.node_id)return 0;let caps:any=n.capabilities||{};if(typeof caps==="string"){try{caps=JSON.parse(caps)}catch{caps=[caps]}}const {error}=await sb.from("radar_nodes").upsert({node_id:n.node_id,node_type:n.node_type||"other",name:n.name||null,enabled:true,app_version:n.app_version||null,last_seen:n.last_seen||new Date().toISOString(),capabilities:caps,metadata:{detail:n.detail||null}},{onConflict:"node_id"});if(error)throw error;return 1});out.nodes=nodes.length}
  if(b.node?.node_id){const n=b.node;const {error}=await sb.from("radar_nodes").upsert({node_id:n.node_id,node_type:n.node_type||"other",name:n.name||null,enabled:n.enabled!==false,app_version:n.app_version||null,last_seen:n.last_seen||new Date().toISOString(),capabilities:n.capabilities||{},metadata:n.metadata||{}},{onConflict:"node_id"});if(error)throw error;out.node=n.node_id}
  out.edge_ms=Date.now()-started;out.input_counts={market:market.length,events:rawEvents.length,runs:runs.length,agents:agents.length,positions:pos.length,trades:trades.length,marks:rawMarks.length,nodes:nodes.length};return res(200,out)
}catch(e){return res(500,{ok:false,error:String((e as any)?.message||e),edge_ms:Date.now()-started})}});
