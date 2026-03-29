from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

from src.models.state import MergeState
from src.web.app import WebApp

logger = logging.getLogger(__name__)


class MergeUIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for merge UI."""

    app: WebApp

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/status":
            self._json_response(self.app.get_status())
        elif path == "/api/files":
            self._json_response(self.app.get_files())
        elif path.startswith("/api/files/"):
            file_path = path[len("/api/files/") :]
            detail = self.app.get_file_detail(file_path)
            if detail is None:
                self._json_response({"error": "Not found"}, status=404)
            else:
                self._json_response(detail)
        elif path == "/api/report":
            self._json_response(self.app.get_report())
        elif path == "" or path == "/":
            self._serve_index()
        else:
            self._json_response({"error": "Not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        content_length = int(self.headers.get("Content-Length", 0))
        body = (
            self.rfile.read(content_length).decode("utf-8")
            if content_length > 0
            else "{}"
        )

        try:
            data: dict[str, Any] = json.loads(body)
        except json.JSONDecodeError:
            self._json_response({"error": "Invalid JSON"}, status=400)
            return

        if path == "/api/decisions":
            result = self.app.submit_decision(
                file_path=data.get("file_path", ""),
                decision=data.get("decision", ""),
                reviewer_name=data.get("reviewer_name"),
                reviewer_notes=data.get("reviewer_notes"),
                custom_content=data.get("custom_content"),
            )
            status = 200 if result.get("success") else 400
            self._json_response(result, status=status)
        elif path == "/api/decisions/batch":
            result = self.app.submit_batch_decisions(
                file_paths=data.get("file_paths", []),
                decision=data.get("decision", ""),
                reviewer_name=data.get("reviewer_name"),
                reviewer_notes=data.get("reviewer_notes"),
            )
            status = 200 if result.get("success") else 400
            self._json_response(result, status=status)
        else:
            self._json_response({"error": "Not found"}, status=404)

    def _json_response(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_index(self) -> None:
        html = _INDEX_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        logger.info(format, *args)


def start_server(state: MergeState, host: str = "localhost", port: int = 8080) -> None:
    """Start the merge UI web server."""
    app = WebApp(state)
    MergeUIHandler.app = app
    server = HTTPServer((host, port), MergeUIHandler)
    logger.info("Merge UI available at http://%s:%d", host, port)
    print(f"Merge UI available at http://{host}:{port}")  # noqa: T201
    print("Press Ctrl+C to stop")  # noqa: T201
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")  # noqa: T201
        server.shutdown()


_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CodeMergeSystem - Decision UI</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: system-ui, sans-serif; background: #f5f5f5; color: #333;
         padding: 2rem; }
  h1 { margin-bottom: 1rem; }
  .status { background: #fff; padding: 1rem; border-radius: 8px;
            margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
  .file-list { list-style: none; }
  .file-item { background: #fff; padding: 1rem; margin-bottom: .5rem;
               border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.1);
               cursor: pointer; }
  .file-item:hover { background: #f0f7ff; }
  .file-item.decided { opacity: 0.6; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
           font-size: .85em; }
  .badge-pending { background: #fff3cd; color: #856404; }
  .badge-done { background: #d4edda; color: #155724; }
  .modal { display: none; position: fixed; top: 0; left: 0; right: 0;
           bottom: 0; background: rgba(0,0,0,.5); z-index: 10; }
  .modal.active { display: flex; align-items: center;
                  justify-content: center; }
  .modal-content { background: #fff; padding: 2rem; border-radius: 12px;
                   max-width: 600px; width: 90%; max-height: 80vh;
                   overflow-y: auto; }
  .btn { padding: .5rem 1rem; border: none; border-radius: 6px;
         cursor: pointer; font-size: 1em; margin: .25rem; }
  .btn-primary { background: #007bff; color: #fff; }
  .btn-secondary { background: #6c757d; color: #fff; }
  .btn:hover { opacity: .9; }
  #detail-options .opt-btn { display: block; width: 100%; text-align: left;
                             padding: .75rem; margin: .5rem 0;
                             background: #f8f9fa; border: 1px solid #dee2e6;
                             border-radius: 6px; cursor: pointer; }
  #detail-options .opt-btn:hover { background: #e2e6ea; }
</style>
</head>
<body>
<h1>CodeMergeSystem</h1>
<div id="status" class="status">Loading...</div>
<ul id="files" class="file-list"></ul>

<div id="modal" class="modal">
  <div class="modal-content">
    <h2 id="detail-file"></h2>
    <p id="detail-context" style="margin:1rem 0;"></p>
    <p><strong>Recommendation:</strong> <span id="detail-rec"></span></p>
    <p><strong>Rationale:</strong> <span id="detail-rationale"></span></p>
    <div id="detail-options" style="margin:1rem 0;"></div>
    <button class="btn btn-secondary" onclick="closeModal()">Close</button>
  </div>
</div>

<script>
async function load() {
  var statusData = await (await fetch('/api/status')).json();
  var el = document.getElementById('status');
  el.textContent = '';
  var parts = [
    'Status: ' + statusData.status,
    'Files: ' + statusData.total_files,
    'Auto-merged: ' + statusData.auto_merged,
    'Human required: ' + statusData.human_required
  ];
  el.textContent = parts.join(' | ');

  var files = await (await fetch('/api/files')).json();
  var ul = document.getElementById('files');
  ul.textContent = '';
  files.forEach(function(f) {
    var li = document.createElement('li');
    li.className = 'file-item' + (f.decided ? ' decided' : '');
    var strong = document.createElement('strong');
    strong.textContent = f.file_path;
    li.appendChild(strong);
    li.appendChild(document.createTextNode(' '));
    var badge = document.createElement('span');
    badge.className = f.decided ? 'badge badge-done' : 'badge badge-pending';
    badge.textContent = f.decided ? f.decision : 'pending';
    li.appendChild(badge);
    li.appendChild(document.createTextNode(
      ' \\u2014 ' + f.analyst_recommendation +
      ' (' + (f.analyst_confidence * 100).toFixed(0) + '%)'
    ));
    li.onclick = function() { showDetail(f.file_path); };
    ul.appendChild(li);
  });
}

async function showDetail(fp) {
  var d = await (await fetch('/api/files/' + encodeURIComponent(fp))).json();
  document.getElementById('detail-file').textContent = d.file_path;
  document.getElementById('detail-context').textContent = d.context_summary;
  document.getElementById('detail-rec').textContent =
    d.analyst_recommendation +
    ' (' + (d.analyst_confidence * 100).toFixed(0) + '%)';
  document.getElementById('detail-rationale').textContent =
    d.analyst_rationale;
  var opts = document.getElementById('detail-options');
  opts.textContent = '';
  d.options.forEach(function(o) {
    var btn = document.createElement('button');
    btn.className = 'opt-btn';
    btn.textContent = o.key + ': ' + o.decision + ' \\u2014 ' + o.description;
    btn.onclick = function() { submitDecision(fp, o.decision); };
    opts.appendChild(btn);
  });
  document.getElementById('modal').classList.add('active');
}

function closeModal() {
  document.getElementById('modal').classList.remove('active');
}

async function submitDecision(fp, decision) {
  await fetch('/api/decisions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({file_path: fp, decision: decision})
  });
  closeModal();
  load();
}

load();
</script>
</body>
</html>"""
