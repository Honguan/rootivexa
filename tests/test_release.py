import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_release


class ReleaseTests(unittest.TestCase):
    def test_source_archive_and_checksum_are_reproducible(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            first = build_release.build(root, output / "first")
            second = build_release.build(root, output / "second")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(
                first.with_suffix(".zip.sha256").read_text(encoding="ascii"),
                f"{hashlib.sha256(first.read_bytes()).hexdigest()}  {first.name}\n",
            )
            with zipfile.ZipFile(first) as package:
                self.assertIsNone(package.testzip())
                self.assertEqual(package.namelist(), [
                    f"rootivexa/{name}" for name in build_release.FILES
                ])
                for name in build_release.FILES:
                    self.assertEqual(package.read(f"rootivexa/{name}"),
                                     (root / name).read_bytes())
