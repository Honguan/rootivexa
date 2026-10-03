"""Build the source release using only Python's standard library."""
import hashlib
from pathlib import Path
import zipfile

VERSION = "1.0.1"
FILES = (
    ".gitignore", "LICENSE", "README.md", "VALIDATION.md", "CHANGELOG.md",
    "build_release.py", "manage.py", "settings.json",
    "install.cmd", "uninstall.cmd", "configure.cmd", "status.cmd",
    "prompts/architect.txt", "prompts/explorer.txt", "prompts/researcher.txt",
    "prompts/worker.txt", "prompts/routing.md",
    "tests/test_manage.py", "tests/probe_native.py", "tests/test_release.py",
)


def build(root: Path, output: Path) -> Path:
    sources = {name: (root / name).read_bytes() for name in FILES}
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"rootivexa-{VERSION}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, data in sources.items():
            entry = zipfile.ZipInfo(f"rootivexa/{name}", (2026, 10, 3, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(entry, data)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(
        f"{checksum}  {archive.name}\n", encoding="ascii"
    )
    return archive


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    print(build(root, root / "dist"))
