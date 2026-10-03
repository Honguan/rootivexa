"""Execute one installed role in a separate Codex CLI process."""
from contextlib import contextmanager
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib
import uuid

ROLES = ("explorer", "researcher", "worker", "architect")
MAX_PARALLEL = 3


@contextmanager
def file_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if os.fstat(stream.fileno()).st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise BlockingIOError(f"Busy: {path}") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def find_codex(explicit=None):
    selected = explicit or os.environ.get("CODEX_ORCHESTRATION_CODEX")
    if selected:
        path = Path(selected).expanduser()
        if not path.is_absolute() or not path.is_file() or (os.name == "nt" and path.suffix.lower() != ".exe"):
            raise ValueError("--codex / CODEX_ORCHESTRATION_CODEX 必須是 codex.exe 的完整路徑。")
        return str(path)
    found = shutil.which("codex")
    if found:
        path = Path(found)
        if os.name != "nt" or path.suffix.lower() == ".exe":
            return str(path)
        # Resolve the official npm Windows package to an executable, avoiding cmd.exe argument parsing.
        package = path.parent / "node_modules/@openai/codex/node_modules/@openai"
        candidates = list(package.glob("codex-win32-*/vendor/*/bin/codex.exe"))
        if len(candidates) == 1:
            return str(candidates[0])
    raise ValueError("找不到 Codex CLI；請安裝官方 CLI，或設定 CODEX_ORCHESTRATION_CODEX 指向桌面版內附 codex.exe。")


def command(executable, role, config, workspace, output):
    tier = config["service_tier"]
    if tier not in ("default", "fast"):
        raise ValueError("角色 service_tier 只接受 default 或 fast。")
    return [executable, "exec", "--ephemeral", "--skip-git-repo-check", "--color", "never", "--json",
            "--cd", str(workspace), "--model", config["model"],
            "--sandbox", "workspace-write" if role == "worker" else "read-only",
            "-c", "approval_policy=\"never\"", "-c", "agents.enabled=false",
            "-c", "features.fast_mode=true",
            "-c", "model_reasoning_effort=" + json.dumps(config["model_reasoning_effort"]),
            "-c", "service_tier=" + json.dumps(tier),
            "--output-last-message", str(output), "-"]


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        process.terminate()
    process.wait(timeout=10)


def run(state, role, workspace, brief, executable, timeout):
    if os.environ.get("CODEX_ORCHESTRATION_CHILD") == "1":
        raise ValueError("角色程序不可再次啟動角色程序。")
    started = time.monotonic()
    # Queue without model polling. Holding the slot protects the running task from uninstall.
    while True:
        slot = None
        try:
            with file_lock(state / "lock"):
                if not (state / "manifest.json").exists():
                    raise ValueError("此全域目錄尚未安裝角色，請先執行 install.cmd。")
                for number in range(MAX_PARALLEL):
                    candidate = file_lock(state / f"slots/{number}.lock")
                    try:
                        candidate.__enter__()
                    except BlockingIOError:
                        continue
                    slot = candidate
                    break
                if slot:
                    config = tomllib.loads((state / f"agents/{role}.toml").read_text(encoding="utf-8-sig"))
        except BlockingIOError:
            pass
        except BaseException:
            if slot:
                slot.__exit__(*sys.exc_info())
            raise
        if slot:
            break
        if time.monotonic() - started >= timeout:
            raise TimeoutError("等待可用角色名額逾時。")
        time.sleep(0.25)
    process = None
    try:
        run_dir = state / "runs" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:10])
        run_dir.mkdir(parents=True)
        output = run_dir / "result.md"
        args = command(executable, role, config, workspace, output)
        task = "CODEX_ORCHESTRATION_CHILD\nRole: " + role + "\n" + config["developer_instructions"]
        task += "\nDo not launch further agents or role runners. Follow the brief's requested response language.\n\nAssigned task:\n" + brief
        metadata = {"role": role, "model": config["model"], "effort": config["model_reasoning_effort"],
                    "fast": config["service_tier"] == "fast", "workspace": str(workspace), "status": "running"}
        status = run_dir / "status.json"
        status.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"角色：{role}；結果目錄：{run_dir}", flush=True)
        events, errors = b"", b""
        try:
            process = subprocess.Popen(args, cwd=workspace, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=dict(os.environ, CODEX_HOME=str(state.parent), CODEX_ORCHESTRATION_CHILD="1"))
            remaining = max(0.1, timeout - (time.monotonic() - started))
            events, errors = process.communicate(task.encode("utf-8"), timeout=remaining)
            exit_code = process.returncode
            if exit_code == 0 and (not output.exists() or not output.read_bytes().strip()):
                exit_code = 1
                errors += b"\nCodex returned no final response; task marked failed.\n"
            metadata.update(status="completed" if exit_code == 0 else "failed", exit_code=exit_code)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            if process:
                stop_process(process)
                try:
                    events, errors = process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    events = getattr(exc, "output", None) or b""
                    errors = getattr(exc, "stderr", None) or b""
            metadata.update(status="interrupted", exit_code=130)
            raise
        except BaseException:
            if process:
                stop_process(process)
            metadata.update(status="failed", exit_code=1)
            raise
        finally:
            (run_dir / "events.jsonl").write_bytes(events)
            (run_dir / "stderr.log").write_bytes(errors)
            status.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{'完成' if exit_code == 0 else '失敗'}：{output if exit_code == 0 else run_dir / 'stderr.log'}")
        return exit_code
    finally:
        slot.__exit__(None, None, None)


def main(argv=None):
    parser = argparse.ArgumentParser(description="每個角色獨立模型／effort／Fast；最多三個並行程序。")
    parser.add_argument("role", choices=ROLES)
    parser.add_argument("--cwd", required=True, type=Path)
    parser.add_argument("--task-file", required=True, type=Path)
    parser.add_argument("--codex", help="codex.exe 完整路徑；預設自動尋找官方 CLI")
    parser.add_argument("--timeout", type=int, default=1800, help="含排隊時間的秒數，預設 1800")
    args = parser.parse_args(argv)
    try:
        if not args.cwd.is_absolute() or not args.cwd.is_dir() or not args.task_file.is_absolute() or args.timeout <= 0:
            raise ValueError("工作目錄與任務檔必須是完整路徑；工作目錄須存在，timeout 必須大於零。")
        brief = args.task_file.read_text(encoding="utf-8-sig").strip()
        if not brief:
            raise ValueError("任務檔不可空白。")
        return run(Path(__file__).resolve().parent, args.role, args.cwd.resolve(), brief,
                   find_codex(args.codex), args.timeout)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print(f"角色執行未完成：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
