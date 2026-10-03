"""Global-only, reversible Codex role installer. Python 3.11+, no dependencies."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tomllib
from contextlib import contextmanager

PACKAGE = Path(__file__).resolve().parent
ROLES = ("explorer", "researcher", "worker", "architect")
DESCRIPTIONS = {
    "explorer": "Investigate bounded cross-file code paths and return evidence; no edits.",
    "researcher": "Resolve independent documentation questions using authoritative sources; no edits.",
    "worker": "Implement and validate a bounded task with explicit file ownership.",
    "architect": "Review high-impact decisions, repeated failures, or completed multi-module changes; no edits.",
}
BEGIN = b"<!-- BEGIN CODEX-ORCHESTRATION v1 -->"
END = b"<!-- END CODEX-ORCHESTRATION v1 -->"
STATE = "codex-orchestration"
MANAGED = {"AGENTS.md", *(f"agents/{r}.toml" for r in ROLES)}


class Conflict(Exception):
    pass


def global_home() -> Path:
    # CODEX_HOME selects a global Codex home, never a project installation mode.
    value = os.environ.get("CODEX_HOME")
    path = Path(value).expanduser() if value else Path.home() / ".codex"
    if not path.is_absolute():
        raise Conflict("CODEX_HOME 必須是絕對路徑。")
    return path.resolve()


def read(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def encode(data: bytes | None) -> str | None:
    return base64.b64encode(data).decode("ascii") if data is not None else None


def decode(data: str | None) -> bytes | None:
    return base64.b64decode(data, validate=True) if data is not None else None


def json_bytes(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def safe_path(home: Path, relative: str) -> Path:
    if relative not in MANAGED and relative != f"{STATE}/manifest.json":
        raise Conflict(f"不允許的管理路徑：{relative}")
    path = home / relative
    for part in (home, *path.parents, path):
        if part == home.parent:
            continue
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise Conflict(f"管理路徑不可使用連結：{part}")
    if path.resolve().is_relative_to(home.resolve()) is False:
        raise Conflict(f"管理路徑超出全域目錄：{path}")
    return path


def atomic_write(path: Path, data: bytes | None):
    if data is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".orchestration-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_manifest(home: Path):
    data = read(safe_path(home, f"{STATE}/manifest.json"))
    if data is None:
        return None
    manifest = json.loads(data)
    if manifest.get("version") != 2 or set(manifest.get("roles", {})) != set(ROLES):
        raise Conflict("安裝紀錄不屬於原生角色版；請先用原安裝包解除安裝，現況保留。")
    return manifest


@contextmanager
def lock(home: Path):
    state = home / STATE
    safe_path(home, f"{STATE}/manifest.json")
    state.mkdir(parents=True, exist_ok=True)
    with (state / "lock").open("a+b") as stream:
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
            raise Conflict("有安裝程序正在執行；請結束後重試。") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def recover(home: Path):
    journal = home / STATE / "pending.json"
    if not journal.exists():
        return
    entries = json.loads(journal.read_text(encoding="utf-8"))
    for relative, item in entries.items():
        current = read(safe_path(home, relative))
        if current not in (decode(item["before"]), decode(item["after"])):
            raise Conflict(f"中斷後檔案另有修改，保留待人工處理：{relative}")
    for relative, item in reversed(list(entries.items())):
        atomic_write(safe_path(home, relative), decode(item["before"]))
    journal.unlink()


def transaction(home: Path, changes: dict[str, bytes | None]):
    entries = {}
    for relative, after in changes.items():
        before = read(safe_path(home, relative))
        if before != after:
            entries[relative] = {"before": encode(before), "after": encode(after)}
    if not entries:
        return
    # Keep a recoverable snapshot on each real mutation, including edited role files.
    backup = home / STATE / "backups" / f"{time.time_ns()}.json"
    atomic_write(backup, json_bytes(entries))
    journal = home / STATE / "pending.json"
    atomic_write(journal, json_bytes(entries))
    try:
        for relative, item in entries.items():
            path = safe_path(home, relative)
            if read(path) != decode(item["before"]):
                raise Conflict(f"寫入前偵測到外部修改：{relative}")
            atomic_write(path, decode(item["after"]))
    except BaseException:
        recover(home)
        raise
    journal.unlink()


def settings(package: Path) -> dict:
    data = json.loads((package / "settings.json").read_text(encoding="utf-8-sig"))
    if set(data) != set(ROLES):
        raise Conflict("settings.json 必須包含且僅包含 explorer、researcher、worker、architect。")
    for role, value in data.items():
        if not isinstance(value, dict) or set(value) != {"model", "effort"}:
            raise Conflict(f"{role} 僅接受 model、effort；Fast 使用 Root 設定。")
        if not isinstance(value["model"], str) or not value["model"].strip():
            raise Conflict(f"{role}.model 必須是非空字串。")
        if value["effort"] not in {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}:
            raise Conflict(f"{role}.effort 不支援：{value['effort']}")
    return data


def render_role(package: Path, role: str, value: dict) -> bytes:
    prompt = (package / "prompts" / f"{role}.txt").read_text(encoding="utf-8").strip()
    fields = {
        "name": role, "description": DESCRIPTIONS[role],
        "model": value["model"], "model_reasoning_effort": value["effort"],
        "developer_instructions": prompt,
    }
    text = "# Managed by codex-orchestration; edit settings.json and rerun install.cmd.\n"
    text += "\n".join(f"{k} = {json.dumps(v, ensure_ascii=False)}" for k, v in fields.items()) + "\n"
    tomllib.loads(text)
    return text.encode("utf-8")


def routing_block(package: Path, current: bytes) -> bytes:
    newline = b"\r\n" if b"\r\n" in current else b"\n"
    body = (package / "prompts/routing.md").read_text(encoding="utf-8").strip()
    return newline * 2 + BEGIN + newline + body.encode("utf-8").replace(b"\n", newline) + newline + END + newline


def block_span(current: bytes):
    if current.count(BEGIN) != 1 or current.count(END) != 1:
        raise Conflict("AGENTS.md 管理區塊缺失或重複；保留檔案，請先修復標記。")
    start, end = current.index(BEGIN), current.index(END) + len(END)
    if end < start:
        raise Conflict("AGENTS.md 管理區塊標記順序錯誤。")
    return start, end


def remove_block(current: bytes, manifest: dict) -> bytes | None:
    original = decode(manifest["original_agents"])
    block = decode(manifest["block"])
    if current == (original or b"") + block:
        return original
    block_span(current)
    if current.count(block) == 1:
        return current.replace(block, b"", 1)
    start, end = block_span(current)
    # Keep every byte outside our markers; the full current file is backed up.
    return current[:start] + current[end:]


def preflight(home: Path, manifest):
    config = read(home / "config.toml")
    parsed = tomllib.loads(config.decode("utf-8-sig")) if config else {}
    if read(home / "AGENTS.override.md"):
        raise Conflict("AGENTS.override.md 會遮蔽 AGENTS.md；請先自行處理，安裝器不覆寫。")
    agents = parsed.get("agents", {})
    if agents.get("enabled") is False:
        raise Conflict("全域 agents.enabled=false；請自行啟用原生子代理後再安裝。")
    for role in ROLES:
        if role in agents:
            raise Conflict(f"config.toml 已定義同名角色：{role}，未覆寫。")
    owned = {home / f"agents/{r}.toml" for r in ROLES} if manifest else set()
    for path in (home / "agents").glob("*.toml"):
        if path in owned:
            continue
        name = tomllib.loads(path.read_text(encoding="utf-8-sig")).get("name")
        if name in ROLES:
            raise Conflict(f"已有同名自訂角色 {name}：{path}，未覆寫。")


def install_plan(home: Path, package: Path):
    manifest = load_manifest(home)
    preflight(home, manifest)
    config = settings(package)
    changes = {}
    for role in ROLES:
        relative = f"agents/{role}.toml"
        current = read(safe_path(home, relative))
        if not manifest and current is not None:
            raise Conflict(f"既有檔案衝突，未覆寫：{relative}")
        if manifest and digest(current) != manifest["roles"][role]:
            raise Conflict(f"角色曾被手動修改，保留現況：{relative}。請將設定移至 settings.json，或先解除安裝（會備份）。")
        changes[relative] = render_role(package, role, config[role])
    current = read(safe_path(home, "AGENTS.md"))
    if manifest:
        old_block = decode(manifest["block"])
        if (current or b"").count(old_block) != 1:
            raise Conflict("分工區塊曾被修改；先解除安裝以備份，再重新安裝。")
        block = routing_block(package, current or b"")
        changes["AGENTS.md"] = current.replace(old_block, block, 1)
        original = manifest["original_agents"]
    else:
        if BEGIN in (current or b"") or END in (current or b""):
            raise Conflict("AGENTS.md 已有標記但無安裝紀錄；未修改。")
        block = routing_block(package, current or b"")
        changes["AGENTS.md"] = (current or b"") + block
        original = encode(current)
    config_bytes = read(home / "config.toml")
    global_config = tomllib.loads(config_bytes.decode("utf-8-sig")) if config_bytes else {}
    limit = global_config.get("project_doc_max_bytes", 32768)
    if len(changes["AGENTS.md"]) > limit:
        raise Conflict(f"追加規則後 AGENTS.md 超過 project_doc_max_bytes={limit}，未截斷原文。")
    next_manifest = {
        "version": 2, "original_agents": original, "block": encode(block),
        "roles": {r: digest(changes[f"agents/{r}.toml"]) for r in ROLES},
    }
    changes[f"{STATE}/manifest.json"] = json_bytes(next_manifest)
    return changes


def uninstall_plan(home: Path):
    manifest = load_manifest(home)
    if not manifest:
        return {}
    current = read(safe_path(home, "AGENTS.md"))
    if current is None:
        raise Conflict("AGENTS.md 已被移除；保留其他檔案，請先恢復後重試。")
    changes = {f"agents/{r}.toml": None for r in ROLES}
    changes["AGENTS.md"] = remove_block(current, manifest)
    changes[f"{STATE}/manifest.json"] = None
    return changes


def status(home: Path):
    manifest = load_manifest(home)
    print(f"全域目錄：{home}")
    print("狀態：" + ("已安裝" if manifest else "未安裝"))
    if (home / STATE / "pending.json").exists():
        print("上次操作中斷；下次安裝／解除安裝會先檢查並復原。")
    if manifest:
        for role in ROLES:
            path = safe_path(home, f"agents/{role}.toml")
            content = read(path)
            if content is None:
                print(f"{role}：檔案缺失")
                continue
            data = tomllib.loads(content.decode("utf-8-sig"))
            print(f"{role}：{data.get('model')} / {data.get('model_reasoning_effort')} / Fast 跟隨 Root" + ("（手動修改）" if digest(content) != manifest["roles"][role] else ""))


def main(argv=None):
    parser = argparse.ArgumentParser(description="僅管理全域 Codex 角色；保留 Root、MCP、Hook 與權限設定。")
    parser.add_argument("action", choices=("install", "uninstall", "status"))
    parser.add_argument("--dry-run", action="store_true", help="只檢查並列出變更，不寫入")
    args = parser.parse_args(argv)
    try:
        home = global_home()
        if args.action == "status":
            status(home)
            return 0
        if args.dry_run:
            if (home / STATE / "pending.json").exists():
                raise Conflict("存在未完成操作；dry-run 不復原，請先執行安裝或解除安裝。")
            changes = install_plan(home, PACKAGE) if args.action == "install" else uninstall_plan(home)
        else:
            with lock(home):
                recover(home)
                changes = install_plan(home, PACKAGE) if args.action == "install" else uninstall_plan(home)
                changes = {r: d for r, d in changes.items() if read(safe_path(home, r)) != d}
                transaction(home, changes)
        if args.dry_run:
            changes = {r: d for r, d in changes.items() if read(safe_path(home, r)) != d}
        print(f"{'預覽' if args.dry_run else '完成'}：{len(changes)} 個檔案變更；全域目錄 {home}")
        for relative, data in changes.items():
            print(f"  {'移除' if data is None else '寫入'} {relative}")
        if not args.dry_run and changes:
            print("請開啟新的 Codex 對話載入變更。復原備份：" + str(home / STATE / "backups"))
        return 0
    except (Conflict, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"未完成：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
