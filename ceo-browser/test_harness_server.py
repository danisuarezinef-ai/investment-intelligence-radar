from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>CEO browser harness</title></head>
<body>
  <div id="prompt-textarea" role="textbox" contenteditable="true"></div>
  <button data-testid="send-button" id="send">Send</button>
  <div id="messages"></div>
<script>
document.getElementById('send').addEventListener('click', () => {
  const prompt = document.getElementById('prompt-textarea').innerText ||
                 document.getElementById('prompt-textarea').textContent || '';
  const stop = document.createElement('button');
  stop.dataset.testid='stop-button';
  stop.textContent='Stop';
  document.body.appendChild(stop);
  setTimeout(() => {
    const msg=document.createElement('div');
    msg.setAttribute('data-message-author-role','assistant');
    msg.textContent='HARNESS_RESPONSE: '+prompt+' <CEO_DONE>true</CEO_DONE>';
    document.getElementById('messages').appendChild(msg);
    stop.remove();
  }, 500);
});
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        raw = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
