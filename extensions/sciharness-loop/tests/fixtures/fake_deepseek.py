"""Local API fixture around the production DeepSeek runner, no external API."""
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.path == "/chat/completions"
        assert self.headers["Authorization"] == "Bearer unused-fixture-key"
        schema = request["tools"][-1]["function"]["parameters"]
        prompt = request["messages"][1]["content"]
        is_plan = "title" in schema["properties"]
        prior = [v for v in request["messages"] if v["role"] == "tool"]
        if not prior:
            name = "shell"
            command = "python3 /opt/sciharness/assert_isolation.py"
            if "HANG" in prompt:
                print(json.dumps({"type": "fixture_hanging"}), flush=True)
                command += "; sleep 60"
            arguments = {"command": command, "timeout_seconds": 60}
        elif not is_plan and len(prior) == 1:
            name, arguments = "write_file", {"path": "proposal.md", "content": "Synthetic pilot; no scientific conclusion."}
        elif not is_plan and len(prior) == 2:
            name, arguments = "write_file", {"path": "artifacts/log.txt", "content": "read-only input enforced\n"}
        elif not is_plan and "SYMLINK" in prompt and len(prior) == 3:
            name, arguments = "shell", {"command": "ln -s /input/project/docs/STATE.md /work/artifacts/escape", "timeout_seconds": 2}
        else:
            name = "finish"
            arguments = ({"title": "Isolated pilot", "task": "SYMLINK" if "SYMLINK" in prompt else "pilot",
                          "rationale": "Exercise the isolated executor"} if is_plan else {
                              "summary": "Isolated pilot", "limitations": "Synthetic fixture",
                              "checks": ["read-only input enforced"], "needs_human_review": True})
            if "action" in schema["properties"]:
                arguments["action"] = "explore"
        message = {"role": "assistant", "content": None, "tool_calls": [{
            "id": "call-" + str(len(prior)), "type": "function", "function": {
                "name": name, "arguments": json.dumps(arguments)}}]}
        data = json.dumps({"model": "fixture-model", "choices": [{"finish_reason": "tool_calls",
                            "message": message}], "usage": {"total_tokens": 1}}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 17651), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
spec = importlib.util.spec_from_file_location("production_runner", "/opt/sciharness/deepseek_production.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.main()
