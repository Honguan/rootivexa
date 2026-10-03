"""Installed CLI worker integration tests; loopback responses, zero paid inference."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import manage


def probe(executable, role, fast, empty=False):
    captured = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def do_POST(self):
            captured.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            response_id = "resp_" + uuid.uuid4().hex
            item = {"type": "message", "id": "msg_" + uuid.uuid4().hex,
                    "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": "" if empty else "fixture complete", "annotations": []}]}
            events = [
                {"type": "response.created", "response": {"id": response_id, "object": "response", "status": "in_progress", "output": []}},
                {"type": "response.output_item.done", "output_index": 0, "item": item},
                {"type": "response.completed", "response": {"id": response_id, "object": "response", "status": "completed", "output": [item], "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}}},
            ]
            output = "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="codex-orchestration-cli-") as temporary:
            home = Path(temporary) / "home"
            workspace = Path(temporary) / "workspace"
            home.mkdir()
            workspace.mkdir()
            config = f'''model = "gpt-6-astra"
model_reasoning_effort = "low"
model_provider = "fixture"
service_tier = "{'default' if fast else 'fast'}"
[model_providers.fixture]
name = "Loopback fixture"
base_url = "http://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
'''.encode()
            (home / "config.toml").write_bytes(config)
            with manage.lock(home):
                manage.transaction(home, manage.install_plan(home, manage.PACKAGE))
            selected = dict(manage.settings(manage.PACKAGE)[role], fast=fast)
            state = home / manage.STATE
            (state / f"agents/{role}.toml").write_bytes(manage.render_role(manage.PACKAGE, role, selected))
            task = workspace / "brief.txt"
            brief = "Return fixture complete. Do not use tools. 保留中文任務。"
            task.write_text(brief, encoding="utf-8")
            result = subprocess.run([sys.executable, str(state / "runner.py"), role,
                                     "--cwd", str(workspace), "--task-file", str(task), "--codex", executable],
                                    env=dict(os.environ, CODEX_HOME=str(home)), cwd=workspace,
                                    capture_output=True, text=True, encoding="utf-8", timeout=45)
            assert result.returncode == (1 if empty else 0), result.stdout + result.stderr
            assert len(captured) == 1, f"Unexpected request count: {len(captured)}"
            body = captured[0]
            encoded = json.dumps(body, ensure_ascii=False)
            assert "CODEX_ORCHESTRATION_CHILD" in encoded
            assert brief in encoded, "UTF-8 brief was not delivered"
            assert (manage.PACKAGE / f"prompts/{role}.txt").read_text(encoding="utf-8").splitlines()[0] in encoded
            assert body["model"] == selected["model"], body["model"]
            assert body["reasoning"]["effort"] == selected["effort"], body["reasoning"]
            assert body.get("service_tier") == ("priority" if fast else None), body.get("service_tier")
            run_dir = next((state / "runs").iterdir())
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            assert status["status"] == ("failed" if empty else "completed"), status
            if not empty:
                assert (run_dir / "result.md").read_text(encoding="utf-8").strip() == "fixture complete"
            else:
                assert b"no final response" in (run_dir / "stderr.log").read_bytes()
            assert (home / "config.toml").read_bytes() == config
            with manage.lock(home):
                manage.transaction(home, manage.uninstall_plan(home))
            assert not (state / "runner.py").exists()
            assert run_dir.exists(), "Uninstall must preserve result artifacts"
            assert (home / "config.toml").read_bytes() == config
            print(f"PASS {role}={selected['model']}/{selected['effort']} fast={fast}" + (" empty-output rejected" if empty else ""))
    finally:
        server.shutdown()
        server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("codex", help="Absolute path to codex.exe")
    args = parser.parse_args()
    for role in manage.ROLES:
        for fast in (False, True):
            probe(args.codex, role, fast)
    probe(args.codex, "explorer", False, empty=True)


if __name__ == "__main__":
    main()
