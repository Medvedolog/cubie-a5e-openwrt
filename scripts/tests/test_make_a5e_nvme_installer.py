"""Offline package tests; no block or MTD nodes are opened."""
import gzip
import hashlib
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "scripts/make-a5e-nvme-installer.py"
SPEC = importlib.util.spec_from_file_location("nvme_pack", SOURCE)
PACK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACK)
RUNTIME = REPO / "files/usr/sbin/a5e-install-nvme"
TOOLS = ("sfdisk", "mkfs.vfat", "mkfs.ext4", "mcopy", "mkimage", "debugfs", "e2fsck")


class DiskIds(unittest.TestCase):
    def test_keep_boot_code_mbr_table_and_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "disk"
            sample = bytearray(b"\x05" * 512)
            sample[510:] = b"\x55\xaa"
            image.write_bytes(sample)
            for old in (0x5452574f, 0xa5e51201, 0xa5e51202, 0xffffffff):
                sd_id, nvme_id = PACK.installer_signatures(old)
                self.assertEqual(len({old, sd_id, nvme_id, 0}), 4)
                for disk_id in (sd_id, nvme_id):
                    PACK.write_mbr_signature(image, disk_id)
                    self.assertEqual(PACK.mbr_signature(image), disk_id)
                    observed = image.read_bytes()
                    self.assertEqual(observed[:440], sample[:440])
                    self.assertEqual(observed[444:], sample[444:])

    def test_reject_missing_and_zero_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "disk"
            image.write_bytes(bytes(512))
            with self.assertRaisesRegex(RuntimeError, "DOS boot sector"):
                PACK.mbr_signature(image)
            image.write_bytes(bytes(510) + b"\x55\xaa")
            with self.assertRaisesRegex(RuntimeError, "signature is zero"):
                PACK.mbr_signature(image)

    def test_media_scoped_boot_flow(self):
        for media in ("mmc", "nvme"):
            script = PACK.boot_script(media)
            self.assertIn(f'test "${{devtype}}" = "{media}"', script)
            self.assertIn('test "${distro_bootpart}" = 1', script)
            self.assertIn(f"part uuid {media} ${{devnum}}:2 a5erootuuid", script)
            self.assertIn(f"fatload {media} ${{devnum}}:1 ${{kernel_comp_addr_r}} uImage", script)
            self.assertIn("root=PARTUUID=${a5erootuuid}", script)
            self.assertNotIn("mmc_bootdev", script)
        with self.assertRaises(ValueError):
            PACK.boot_script("usb")


class RuntimeCli(unittest.TestCase):
    def test_non_writing_modes_and_argument_rejections(self):
        for args in ([], ["--flash-spi"], ["--check", "--flash-spi"],
                     ["--check", "--install", "/dev/nvme0n1"],
                     ["--install", "/dev/mmcblk0"],
                     ["--install", "/dev/nvme0n1p2"],
                     ["--install", "/dev/nvme0n1p2n2"],
                     ["--install", "/dev/nvme0n1", "--check"],
                     ["--install", "/dev/nvme0n1", "--install", "/dev/nvme0n2"]):
            with self.subTest(args=args):
                result = subprocess.run(["sh", str(RUNTIME), *args], text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertRegex(result.stderr, r"ERROR: (--|duplicate)")
        result = subprocess.run(["sh", str(RUNTIME), "--help"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Read-only", result.stdout)
        self.assertIn("separate confirmation", result.stdout)


@unittest.skipUnless(all(shutil.which(tool) for tool in TOOLS),
                     "real host disk-format tools missing")
class PackageFixture(unittest.TestCase):
    def test_real_ext4_fat_and_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            disk, boot_fs, root_fs = (work / x for x in ("disk", "boot.vfat", "root.ext4"))
            with disk.open("wb") as fd:
                fd.truncate(60 * 1024 * 1024)
            spec = ("label: dos\nlabel-id: 0x5452574f\nunit: sectors\n\n"
                    "start=2048, size=40960, type=c\nstart=45056, size=65536, type=83\n")
            subprocess.run(["sfdisk", str(disk)], input=spec, text=True, check=True)
            with boot_fs.open("wb") as fd:
                fd.truncate(40960 * 512)
            with root_fs.open("wb") as fd:
                fd.truncate(65536 * 512)
            subprocess.run(["mkfs.vfat", "-F", "16", str(boot_fs)], check=True)
            fake_fit = work / "uImage"
            fake_fit.write_bytes(struct.pack(">I", 0xd00dfeed) + b"synthetic FIT fixture\n")
            subprocess.run(["mcopy", "-i", str(boot_fs), str(fake_fit), "::uImage"], check=True)
            fsdir = work / "root"
            runtime = fsdir / "usr/sbin/a5e-install-nvme"
            runtime.parent.mkdir(parents=True)
            runtime.write_text("#!/bin/sh\n", encoding="ascii")
            runtime.chmod(0o755)
            subprocess.run(["mkfs.ext4", "-F", "-q", "-d", str(fsdir), str(root_fs)], check=True)
            PACK.copy_back(boot_fs, disk, 2048 * 512)
            PACK.copy_back(root_fs, disk, 45056 * 512)
            with disk.open("r+b") as fd:
                fd.seek((45056 + 65536) * 512)
                fd.write(b"small OpenWrt metadata fixture")
                fd.truncate()
            base = work / "input.img.gz"
            PACK.gzip_file(disk, base)
            before = PACK.sha256(base)
            donor = work / "fake-donor.bin"
            donor_image = b"0000eGON.BT0" + bytes(120000)
            donor.write_bytes(donor_image)
            args = [str(SOURCE), "--openwrt", str(base), "--uboot", str(donor)]
            out = work / "full"
            with mock.patch.object(sys, "argv", args + ["--out", str(work / "bad")]):
                with self.assertRaises(SystemExit):
                    PACK.main()
            with mock.patch.object(sys, "argv", args + ["--out", str(out)]), \
                 mock.patch.object(PACK, "ARMBIAN_UBOOT_SHA256", hashlib.sha256(donor_image).hexdigest()), \
                 mock.patch.object(PACK, "ARMBIAN_UBOOT_BYTES", len(donor_image)):
                PACK.main()
            self.assertEqual(PACK.sha256(base), before)
            nvme = out / "payload/a5e-nvme-openwrt.img.gz"
            hosts = (
                ("mmc", out / "a5e-hybrid-microsd-installer.img.gz"),
                ("nvme", nvme),
            )
            results = []
            for media, compressed in hosts:
                with gzip.open(compressed, "rb") as stream, (work / f"{media}.img").open("wb") as fd:
                    shutil.copyfileobj(stream, fd)
                raw = work / f"{media}.img"
                self.assertEqual(raw.stat().st_size, (45056 + 65536) * 512)
                results.append(PACK.mbr_signature(raw))
                self.assertEqual(PACK.partition_info(raw), [
                    {**p, "node": f"{raw}{i}"} for i, p in enumerate(PACK.partition_info(disk), 1)
                ])
                with raw.open("rb") as fd:
                    fd.seek(PACK.SD_SPL_OFFSET)
                    self.assertEqual(fd.read(len(donor_image)),
                                     donor_image if media == "mmc" else bytes(len(donor_image)))
                script = work / f"{media}.scr"
                subprocess.run(["mcopy", "-i", f"{raw}@@{2048*512}", "::boot.scr", str(script)], check=True)
                self.assertIn(PACK.boot_script(media).encode("ascii"), script.read_bytes())
                fs = work / f"{media}.ext4"
                PACK.copy_region(raw, 45056 * 512, 65536 * 512, fs)
                item = work / f"{media}-embedded.gz"
                subprocess.run(["debugfs", "-R", f"dump /opt/a5e-installer/{nvme.name} {item}", str(fs)], check=True)
                if media == "mmc":
                    self.assertEqual(PACK.sha256(nvme), PACK.sha256(item))
                else:
                    self.assertFalse(item.exists())
                    self.assertEqual((out / "payload/IMAGE_SHA256").read_text().strip(), PACK.sha256(raw))
            self.assertEqual(len({PACK.mbr_signature(disk), *results}), 3)
            subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=out, check=True)


if __name__ == "__main__":
    unittest.main()
