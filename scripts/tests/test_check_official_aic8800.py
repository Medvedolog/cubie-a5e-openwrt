"""Exercise the LuCI image gate against real ext4 without mounting it."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


CHECKER_PATH = Path(__file__).resolve().parents[1] / "check-official-aic8800.py"
SPEC = importlib.util.spec_from_file_location("a5e_check", CHECKER_PATH)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class LuCIImageTest(unittest.TestCase):
    def setUp(self):
        work = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.root = work / "root"
        self.image = work / "root.ext4"
        self.config = self.root / "etc/config/luci"
        self.config.parent.mkdir(parents=True)
        self.config.write_text(
            "config core 'main'\n\toption mediaurlbase '/luci-static/footstrap'\n",
            encoding="utf-8",
        )
        init = self.root / "etc/init.d/uhttpd"
        init.parent.mkdir()
        init.write_text("#!/bin/sh\n", encoding="utf-8")
        self.startup = self.root / "etc/rc.d/S50uhttpd"
        self.startup.parent.mkdir()
        self.startup.symlink_to("../init.d/uhttpd")
        for theme in ("footstrap", "bootstrap"):
            css = self.root / f"www/luci-static/{theme}/cascade.css"
            css.parent.mkdir(parents=True)
            css.write_bytes(b"body { color: black; }\n")
            header = self.root / f"usr/share/ucode/luci/template/themes/{theme}/header.ut"
            header.parent.mkdir(parents=True)
            header.write_bytes(b"\x1buc\x00\x85\xff")
        self.header = self.root / "usr/share/ucode/luci/template/themes/footstrap/header.ut"

    def verify(self):
        with self.image.open("wb") as stream:
            stream.truncate(8 * 1024 * 1024)
        subprocess.run(["mkfs.ext4", "-q", "-F", "-d", self.root, self.image], check=True)
        CHECKER.verify_luci(self.image)

    def test_binary_headers(self):
        self.verify()

    def test_missing_asset(self):
        self.header.unlink()
        with self.assertRaisesRegex(SystemExit, "footstrap/header.ut"):
            self.verify()

    def test_empty_asset(self):
        self.header.write_bytes(b"")
        with self.assertRaisesRegex(SystemExit, "footstrap/header.ut"):
            self.verify()

    def test_directory_is_not_asset(self):
        self.header.unlink()
        self.header.mkdir()
        (self.header / "child").write_bytes(b"not a theme")
        with self.assertRaisesRegex(SystemExit, "footstrap/header.ut"):
            self.verify()

    def test_wrong_default_theme(self):
        self.config.write_text(
            "config core 'main'\n\toption mediaurlbase '/luci-static/bootstrap'\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(SystemExit, "Footstrap must be"):
            self.verify()

    def test_missing_boot_link(self):
        self.startup.unlink()
        with self.assertRaisesRegex(SystemExit, "uhttpd must be enabled"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
