from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>CEO browser harness</title></head>
<body>
  <div id="auth"></div>
  <div id="composer"></div>
  <button data-testid="send-button" id="send">Send</button>
  <div id="messages"></div>
<script>
const params=new URLSearchParams(location.search);
if(params.get('seed')==='1'){localStorage.setItem('ceo_session','logged-in')}
const logged=localStorage.getItem('ceo_session')==='logged-in';
const auth=document.getElementById('auth');
if(logged){
  const p=document.createElement('button');
  p.dataset.testid='profile-button';
  p.setAttribute('aria-label','Profile');
  p.textContent='Profile';
  auth.appendChild(p);
}else{
  const a=document.createElement('a');
  a.href='/auth/login';
  a.dataset.testid='login-button';
  a.textContent='Log in';
  auth.appendChild(a);
}
const variant=params.get('variant')||'normal';
const composer=document.getElementById('composer');
let input;
if(variant==='normal'){
  input=document.createElement('div');
  input.id='prompt-textarea';
  input.setAttribute('role','textbox');
  input.setAttribute('contenteditable','true');
  input.setAttribute('aria-label','Message ChatGPT');
}else if(variant==='fallback'){
  input=document.createElement('div');
  input.setAttribute('role','textbox');
  input.setAttribute('contenteditable','true');
  input.setAttribute('aria-label','Message ChatGPT');
}else if(variant==='semantic'){
  input=document.createElement('div');
  input.setAttribute('contenteditable','true');
  input.setAttribute('aria-label','Ask anything');
  input.setAttribute('data-randomized-composer','x9');
}else{
  input=document.createElement('textarea');
  input.placeholder='Message';
}
composer.appendChild(input);

const send=document.getElementById('send');

function clearComposer(){
  if(input.tagName==='TEXTAREA' || input.tagName==='INPUT'){
    input.value='';
  }else{
    input.textContent='';
  }
  input.dispatchEvent(new Event('input',{bubbles:true}));
}

function submitPrompt(){
  const prompt=input.innerText || input.textContent || input.value || '';
  if(!prompt.trim()) return;
  clearComposer();

  if(params.get('conversation')==='transition' && !location.pathname.startsWith('/c/')){
    history.pushState({},'', '/c/ceo-b09-b14');
  }

  const stop=document.createElement('button');
  stop.dataset.testid='stop-button';
  stop.textContent='Stop';
  document.body.appendChild(stop);

  const msg=document.createElement('div');
  msg.setAttribute('data-message-author-role','assistant');

  if(params.get('stream')==='1'){
    document.getElementById('messages').appendChild(msg);
    const chunks=[
      'HARNESS_RESPONSE: ',
      prompt,
      ' <CEO_DONE>true</CEO_DONE>',
      ' COMPLETE_TAIL'
    ];
    let i=0;
    const timer=setInterval(() => {
      msg.textContent += chunks[i++];
      if(i>=chunks.length){
        clearInterval(timer);
        stop.remove();
      }
    },250);
  }else{
    setTimeout(() => {
      msg.textContent='HARNESS_RESPONSE: '+prompt+' <CEO_DONE>true</CEO_DONE> COMPLETE_TAIL';
      document.getElementById('messages').appendChild(msg);
      stop.remove();
    },300);
  }
}

if(variant==='enter'){
  send.remove();
  input.addEventListener('keydown',(event)=>{
    if(event.key==='Enter' && !event.shiftKey){
      event.preventDefault();
      submitPrompt();
    }
  });
}else{
  send.addEventListener('click', submitPrompt);
}
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/auth/login"):
            raw = b"<html><body>Manual login placeholder</body></html>"
        else:
            raw = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
