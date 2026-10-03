"""Exercise native role spawning against a loopback Responses fixture."""
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


def probe(executable, role, fast):
    captured = []
    child_done = threading.Event()
    root_calls = 0

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def do_POST(self):
            nonlocal root_calls
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            captured.append(body)
            is_child = body["reasoning"]["effort"] != "low"
            response_id = "resp_" + uuid.uuid4().hex
            item = {"type": "message", "id": "msg_" + uuid.uuid4().hex,
                    "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": "fixture complete", "annotations": []}]}
            if not is_child:
                root_calls += 1
                if root_calls == 1:
                    item = {"type": "function_call", "id": "fc_" + uuid.uuid4().hex,
                            "call_id": "call_" + uuid.uuid4().hex, "name": "spawn_agent", "namespace": "collaboration",
                            "arguments": json.dumps({"agent_type": role, "task_name": "fixture_child",
                                                     "fork_turns": "none", "message": "Return fixture complete. 保留中文任務。"}),
                            "status": "completed"}
                else:
                    child_done.wait(5)
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
            self.wfile.flush()
            if is_child:
                child_done.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="codex-native-fixture-") as temporary:
            home = Path(temporary) / "home"
            workspace = Path(temporary) / "workspace"
            home.mkdir()
            workspace.mkdir()
            config = f'''model = "gpt-6-astra"
model_reasoning_effort = "low"
model_provider = "fixture"
service_tier = "{'fast' if fast else 'default'}"
[agents]
enabled = true
[features]
js_repl = false
fast_mode = true
[model_providers.fixture]
name = "Loopback fixture"
base_url = "http://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
'''.encode()
            (home / "config.toml").write_bytes(config)
            with manage.lock(home):
                manage.transaction(home, manage.install_plan(home, manage.PACKAGE))
            result = subprocess.run([executable, "exec", "--ephemeral", "--skip-git-repo-check", "--json",
                                     "--cd", str(workspace), "--sandbox", "read-only", "-"],
                                    input=f"Delegate this fixture to {role}. Return its result.",
                                    env=dict(os.environ, CODEX_HOME=str(home)), cwd=workspace,
                                    capture_output=True, text=True, encoding="utf-8", timeout=45)
            assert result.returncode == 0, result.stdout + result.stderr
            children = [body for body in captured if body["reasoning"]["effort"] != "low"]
            assert len(children) == 1, result.stdout + result.stderr
            child = children[0]
            expected = manage.settings(manage.PACKAGE)[role]
            assert child["model"] == expected["model"], child["model"]
            assert child["reasoning"]["effort"] == expected["effort"]
            assert child.get("service_tier") == ("priority" if fast else None)
            content = json.dumps(child, ensure_ascii=False)
            assert "保留中文任務。" in content
            assert (manage.PACKAGE / f"prompts/{role}.txt").read_text(encoding="utf-8").splitlines()[0] in content
            assert (home / "config.toml").read_bytes() == config
            with manage.lock(home):
                manage.transaction(home, manage.uninstall_plan(home))
            assert (home / "config.toml").read_bytes() == config
            assert not any((home / "agents").glob("*.toml"))
            print(f"PASS native {role}={expected['model']}/{expected['effort']} Root fast={fast}")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("codex", help="Absolute path to codex.exe")
    args = parser.parse_args()
    for role in manage.ROLES:
        for fast in (False, True):
            probe(args.codex, role, fast)
