const CACHE='radar-mobile-v1';
const SHELL=['/mobile/','/mobile/manifest.webmanifest'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(url.pathname==='/mobile/dashboard'){
    event.respondWith(fetch(event.request).catch(()=>new Response(JSON.stringify({counts:{prices:0,events:0,runs:0},status:{cloud_enabled:false},intelligence:{},opportunities:{},paper_agents:[],latest_prices:[],latest_events:[]}),{headers:{'Content-Type':'application/json'}})));
    return;
  }
  if(event.request.method==='GET'&&url.origin===location.origin){
    event.respondWith(fetch(event.request).then(r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(event.request,copy));return r}).catch(()=>caches.match(event.request).then(r=>r||caches.match('/mobile/'))));
  }
});
