#!/usr/bin/env python3
"""Create the experimental, offline, SD-booted Cubie A5E NVMe installer.

Inputs: fresh OpenWrt ext4 SD image and the *actual* Armbian A5E U-Boot
u-boot-sunxi-with-spl.bin. Produces:
 - NVMe OpenWrt full-disk image with a native nvme: boot.scr;
 - hybrid SD image with Armbian loader and both payloads in ext4 /opt;
 - verification checksums and provenance. Does not flash any hardware.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

SECTOR = 512
SD_SPL_OFFSET = 8192


def execute(*args):
    subprocess.run(args, check=True)


def capture(*args):
    return subprocess.check_output(args, text=True).strip()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def gzip_file(source, target):
    with open(source, "rb") as fi, open(target, "wb") as fo:
        with gzip.GzipFile(fileobj=fo, mode="wb", filename="", mtime=0, compresslevel=6) as gz:
            shutil.copyfileobj(fi, gz, 4 * 1024 * 1024)


def copy_region(source, start, length, target):
    with open(source, "rb") as fi, open(target, "wb") as fo:
        fi.seek(start)
        while length:
            data = fi.read(min(4 * 1024 * 1024, length))
            if not data:
                raise RuntimeError("disk image truncated")
            fo.write(data)
            length -= len(data)


def copy_back(source, target, offset):
    with open(source, "rb") as fi, open(target, "r+b") as fo:
        fo.seek(offset)
        shutil.copyfileobj(fi, fo, 4 * 1024 * 1024)
        fo.flush()
        os.fsync(fo.fileno())


def partition_info(path):
    table = json.loads(capture("sfdisk", "-J", str(path)))["partitiontable"]
    entries = table["partitions"]
    if table["label"] != "dos" or len(entries) != 2:
        raise RuntimeError("expected 2-partition DOS/MBR OpenWrt disk image")
    if entries[0]["start"] != 2048 or entries[0]["type"].lower() not in ("c", "0c", "0x0c"):
        raise RuntimeError("unexpected FAT boot partition")
    if entries[1]["type"].lower() not in ("83", "0x83"):
        raise RuntimeError("unexpected ext4 root partition")
    if entries[1]["start"] <= entries[0]["start"] + entries[0]["size"]:
        raise RuntimeError("partition overlap")
    return entries


def write_fat_bootscript(image, partition, scratch):
    source = scratch / "nvme-boot.cmd"
    compiled = scratch / "boot.scr"
    source.write_text(
        "# Native SPI U-Boot -> NVMe FAT -> OpenWrt ext4 root\n"
        "if part uuid nvme 0:2 a5erootuuid; then\n"
        "  setenv bootargs console=ttyS0,115200 root=PARTUUID=${a5erootuuid} rootwait fw_devlink=rpm\n"
        "  if fatload nvme 0:1 ${kernel_comp_addr_r} uImage; then\n"
        "    bootm ${kernel_comp_addr_r}\n"
        "  fi\n"
        "fi\n"
        "echo ERROR: NVMe root PARTUUID or uImage missing\n"
        "false\n",
        encoding="ascii",
    )
    execute("mkimage", "-A", "arm64", "-O", "linux", "-T", "script", "-C", "none",
            "-n", "Cubie A5E OpenWrt NVMe root", "-d", str(source), str(compiled))
    fat_offset = partition["start"] * SECTOR
    fat_spec = f"{image}@@{fat_offset}"
    execute("mcopy", "-o", "-i", fat_spec, str(compiled), "::boot.scr")
    readback = scratch / "boot-readback.scr"
    execute("mcopy", "-i", fat_spec, "::boot.scr", str(readback))
    if compiled.read_bytes() != readback.read_bytes():
        raise RuntimeError("FAT boot.scr readback mismatch")
    print("NVMe boot script:", source.read_text().strip())


def e2fs_write(fs, src, dest):
    execute("debugfs", "-w", "-R", f"write {src} {dest}", str(fs))
    stat = capture("debugfs", "-R", f"stat {dest}", str(fs))
    if "Inode:" not in stat:
        raise RuntimeError(f"ext4 payload missing: {dest}")


def install_payload(sd_image, partition, payload):
    with tempfile.TemporaryDirectory(prefix="a5e-root-") as temp:
        fs = Path(temp) / "root.ext4"
        offset = partition["start"] * SECTOR
        length = partition["size"] * SECTOR
        copy_region(sd_image, offset, length, fs)
        # OpenWrt mkfs image can contain benign uninitialised inode-bitmap
        # padding. Fix it in this TEMPORARY extraction before copying back.
        execute("e2fsck", "-fy", str(fs))
        execute("e2fsck", "-fn", str(fs))
        execute("debugfs", "-w", "-R", "mkdir /opt", str(fs))  # okay if exists
        execute("debugfs", "-w", "-R", "mkdir /opt/a5e-installer", str(fs))
        for filename in (
            "a5e-nvme-openwrt.img.gz",
            "armbian-u-boot-sunxi-with-spl.bin",
            "IMAGE_BYTES",
            "SHA256SUMS",
        ):
            e2fs_write(fs, payload / filename, "/opt/a5e-installer/" + filename)
        # OpenWrt mkfs image can contain benign uninitialised inode-bitmap
        # padding. Fix it in this TEMPORARY extraction before copying back.
        execute("e2fsck", "-fy", str(fs))
        execute("e2fsck", "-fn", str(fs))
        copy_back(fs, sd_image, offset)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--openwrt", required=True, type=Path, help="source *.img.gz")
    ap.add_argument("--uboot", required=True, type=Path, help="Armbian u-boot-sunxi-with-spl.bin")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    boot = args.uboot.read_bytes()
    if not (65536 < len(boot) < 1048576 - SD_SPL_OFFSET and boot[4:12] == b"eGON.BT0"):
        ap.error("invalid/unexpected Armbian A5E eGON SPL/U-Boot")
    with tempfile.TemporaryDirectory(prefix="a5e-installer-") as temporary:
        work = Path(temporary)
        original = work / "base.img"
        with gzip.open(args.openwrt, "rb") as fi, original.open("wb") as fo:
            shutil.copyfileobj(fi, fo, 4 * 1024 * 1024)
        partitions = partition_info(original)
        root = partitions[1]
        # OpenWrt SD images may carry a short fwtool metadata trailer AFTER
        # the second partition. It is not part of the block-device image.
        disk_end = (root["start"] + root["size"]) * SECTOR
        source_size = original.stat().st_size
        if source_size < disk_end or source_size > disk_end + 65536:
            raise RuntimeError("unexpected size beyond MBR partitions")
        if source_size > disk_end:
            print(f"Discarding {source_size - disk_end} OpenWrt fwtool trailer bytes")
            with original.open("r+b") as stream:
                stream.truncate(disk_end)
        nvme_raw = work / "nvme.img"
        shutil.copyfile(original, nvme_raw)
        write_fat_bootscript(nvme_raw, partitions[0], work)
        payload = args.out / "payload"
        payload.mkdir(exist_ok=True)
        nvme_gz = payload / "a5e-nvme-openwrt.img.gz"
        gzip_file(nvme_raw, nvme_gz)
        (payload / "IMAGE_BYTES").write_text(str(nvme_raw.stat().st_size) + "\n")
        spi_bin = payload / "armbian-u-boot-sunxi-with-spl.bin"
        spi_bin.write_bytes(boot)
        names = ("a5e-nvme-openwrt.img.gz", "armbian-u-boot-sunxi-with-spl.bin", "IMAGE_BYTES")
        (payload / "SHA256SUMS").write_text(
            "".join(f"{sha256(payload / name)}  {name}\n" for name in names)
        )
        sd_raw = work / "sd-installer.img"
        shutil.copyfile(original, sd_raw)
        with sd_raw.open("r+b") as fd:
            fd.seek(SD_SPL_OFFSET)
            fd.write(boot)
            fd.flush()
            os.fsync(fd.fileno())
        install_payload(sd_raw, root, payload)
        installer_gz = args.out / "a5e-hybrid-microsd-installer.img.gz"
        gzip_file(sd_raw, installer_gz)
        (args.out / "SHA256SUMS").write_text(
            f"{sha256(installer_gz)}  {installer_gz.name}\n"
            f"{sha256(nvme_gz)}  payload/{nvme_gz.name}\n"
            f"{sha256(spi_bin)}  payload/{spi_bin.name}\n"
        )
        for fname in (installer_gz, nvme_gz, spi_bin):
            print(fname, fname.stat().st_size, sha256(fname))
        print("SD SPL offset:", SD_SPL_OFFSET, "SPI SPL offset: 0")
        print("NVMe partition UUID is resolved by boot.scr from nvme 0:2")


if __name__ == "__main__":
    main()
