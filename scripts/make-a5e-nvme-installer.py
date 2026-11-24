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
import re
import shutil
import subprocess
import tempfile

SECTOR = 512
SD_SPL_OFFSET = 8192
MBR_SIGNATURE_OFFSET = 440
ARMBIAN_UBOOT_SHA256 = "99ad69e2ededdf66fb15accfa003c1ec5986807e50d11d544c17c074682c6e98"
ARMBIAN_UBOOT_BYTES = 926161
PAYLOAD_NAMES = ("a5e-nvme-openwrt.img.gz", "armbian-u-boot-sunxi-with-spl.bin", "IMAGE_BYTES",
                 "IMAGE_SHA256")


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
    if table["label"] != "dos" or table.get("sectorsize") != SECTOR or len(entries) != 2:
        raise RuntimeError("expected 2-partition, 512-byte-sector DOS/MBR OpenWrt disk image")
    if entries[0]["start"] != 2048 or entries[0]["type"].lower() not in ("c", "0c", "0x0c"):
        raise RuntimeError("unexpected FAT boot partition")
    if entries[1]["type"].lower() not in ("83", "0x83"):
        raise RuntimeError("unexpected ext4 root partition")
    if entries[1]["start"] < entries[0]["start"] + entries[0]["size"]:
        raise RuntimeError("partition overlap")
    if any(part["size"] <= 0 for part in entries):
        raise RuntimeError("nonpositive partition size")
    return entries


def mbr_signature(image):
    with image.open("rb") as fd:
        first_sector = fd.read(SECTOR)
    if len(first_sector) != SECTOR or first_sector[-2:] != b"\x55\xaa":
        raise RuntimeError("missing DOS boot sector")
    signature = int.from_bytes(first_sector[MBR_SIGNATURE_OFFSET:MBR_SIGNATURE_OFFSET + 4], "little")
    if not signature:
        raise RuntimeError("source disk signature is zero; root PARTUUID unavailable")
    return signature


def write_mbr_signature(image, signature):
    if not 0 < signature < (1 << 32):
        raise ValueError("invalid MBR signature")
    with image.open("r+b") as fd:
        fd.seek(MBR_SIGNATURE_OFFSET)
        fd.write(signature.to_bytes(4, "little"))
    if mbr_signature(image) != signature:
        raise RuntimeError("disk signature readback differs")


def installer_signatures(source_signature):
    # Keep all three IDs distinct: staging SD, installed SSD, and a clean
    # stock SD (even when inserted later to recover an already installed SSD).
    used = {0, source_signature}
    signatures = []
    for mask in (0xA5E51201, 0xA5E51202):
        signature = source_signature ^ mask
        while signature in used:
            signature = (signature + 1) & 0xffffffff
        used.add(signature)
        signatures.append(signature)
    return tuple(signatures)


def boot_script(media):
    if media not in ("mmc", "nvme"):
        raise ValueError("unsupported boot medium")
    # Armbian's script boot method and distro boot both supply these vars.
    # Read root UUID and the FIT from the very device which loaded boot.scr.
    return (
        f"# Cubie A5E: {media} FAT boot -> same disk ext4 root\n"
        f'if test "${{devtype}}" = "{media}" && test -n "${{devnum}}" && test "${{distro_bootpart}}" = 1; then\n'
        "  if test -n \"${kernel_comp_addr_r}\"; then\n"
        f"    if part uuid {media} ${{devnum}}:2 a5erootuuid; then\n"
        "      setenv bootargs console=ttyS0,115200 root=PARTUUID=${a5erootuuid} rootwait fw_devlink=rpm\n"
        f"      if fatload {media} ${{devnum}}:1 ${{kernel_comp_addr_r}} uImage; then\n"
        "        bootm ${kernel_comp_addr_r}\n"
        "      fi\n"
        "    fi\n"
        "  fi\n"
        "fi\n"
        f"echo ERROR: Cubie A5E {media} boot failed\n"
        "false\n"
    )


def write_fat_bootscript(image, partition, media, scratch):
    source = scratch / f"{media}-boot.cmd"
    compiled = scratch / f"{media}-boot.scr"
    source.write_text(boot_script(media), encoding="ascii")
    execute("mkimage", "-A", "arm64", "-O", "linux", "-T", "script", "-C", "none",
            "-n", f"Cubie A5E OpenWrt {media} root", "-d", str(source), str(compiled))
    fat_offset = partition["start"] * SECTOR
    fat_spec = f"{image}@@{fat_offset}"
    fit = scratch / f"{media}-uImage"
    execute("mcopy", "-i", fat_spec, "::uImage", str(fit))
    with fit.open("rb") as fd:
        if fd.read(4) != b"\xd0\x0d\xfe\xed":
            raise RuntimeError("uImage in boot partition is not a FIT image")
    execute("mcopy", "-o", "-i", fat_spec, str(compiled), "::boot.scr")
    readback = scratch / f"{media}-readback.scr"
    execute("mcopy", "-i", fat_spec, "::boot.scr", str(readback))
    if compiled.read_bytes() != readback.read_bytes():
        raise RuntimeError("FAT boot.scr readback mismatch")
    print(f"{media} boot script verified:", source.read_text().strip())
    return sha256(fit)


def e2fs_write(fs, src, dest):
    execute("debugfs", "-w", "-R", f"write {src} {dest}", str(fs))
    with tempfile.TemporaryDirectory(prefix="a5e-readback-") as temp:
        output = Path(temp) / "payload"
        execute("debugfs", "-R", f"dump {dest} {output}", str(fs))
        if not output.is_file() or output.stat().st_size != src.stat().st_size or sha256(output) != sha256(src):
            raise RuntimeError(f"ext4 payload readback mismatch: {dest}")


def install_payload(sd_image, partition, payload):
    with tempfile.TemporaryDirectory(prefix="a5e-root-") as temp:
        fs = Path(temp) / "root.ext4"
        offset = partition["start"] * SECTOR
        length = partition["size"] * SECTOR
        copy_region(sd_image, offset, length, fs)
        installer = capture("debugfs", "-R", "stat /usr/sbin/a5e-install-nvme", str(fs))
        if "Type: regular" not in installer or not re.search(r"\bMode:\s+0755\b", installer):
            raise RuntimeError("expected executable /usr/sbin/a5e-install-nvme in the source image")
        # OpenWrt mkfs image can contain benign uninitialised inode-bitmap
        # padding. Fix it in this TEMPORARY extraction before copying back.
        fsck = subprocess.run(["e2fsck", "-fy", str(fs)], check=False)
        # e2fsck 1 means repairs were made; 0 means already clean.
        if fsck.returncode not in (0, 1):
            raise RuntimeError(f"e2fsck repair failed: exit {fsck.returncode}")
        execute("e2fsck", "-fn", str(fs))
        execute("debugfs", "-w", "-R", "mkdir /opt", str(fs))  # okay if exists
        execute("debugfs", "-w", "-R", "mkdir /opt/a5e-installer", str(fs))
        for filename in (*PAYLOAD_NAMES, "SHA256SUMS"):
            e2fs_write(fs, payload / filename, "/opt/a5e-installer/" + filename)
        # OpenWrt mkfs image can contain benign uninitialised inode-bitmap
        # padding. Fix it in this TEMPORARY extraction before copying back.
        fsck = subprocess.run(["e2fsck", "-fy", str(fs)], check=False)
        # e2fsck 1 means repairs were made; 0 means already clean.
        if fsck.returncode not in (0, 1):
            raise RuntimeError(f"e2fsck repair failed: exit {fsck.returncode}")
        execute("e2fsck", "-fn", str(fs))
        copy_back(fs, sd_image, offset)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--openwrt", required=True, type=Path, help="source *.img.gz")
    ap.add_argument("--uboot", required=True, type=Path, help="Armbian u-boot-sunxi-with-spl.bin")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if any(args.out.iterdir()):
        ap.error("output directory must be empty")
    boot = args.uboot.read_bytes()
    if not (len(boot) == ARMBIAN_UBOOT_BYTES and boot[4:12] == b"eGON.BT0"
            and hashlib.sha256(boot).hexdigest() == ARMBIAN_UBOOT_SHA256):
        ap.error("unexpected Armbian A5E eGON SPL/U-Boot: pinned binary required")
    with tempfile.TemporaryDirectory(prefix="a5e-installer-") as temporary:
        work = Path(temporary)
        original = work / "base.img"
        with gzip.open(args.openwrt, "rb") as fi, original.open("wb") as fo:
            shutil.copyfileobj(fi, fo, 4 * 1024 * 1024)
        partitions = partition_info(original)
        root = partitions[1]
        sd_signature, nvme_signature = installer_signatures(mbr_signature(original))
        if len(boot) + SD_SPL_OFFSET >= partitions[0]["start"] * SECTOR:
            raise RuntimeError("Armbian U-Boot would overlap boot partition")
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
        write_mbr_signature(nvme_raw, nvme_signature)
        # NVMe is booted by SPI U-Boot; remove the stock SD SPL from its gap.
        with nvme_raw.open("r+b") as fd:
            fd.seek(SECTOR)
            fd.write(bytes(partitions[0]["start"] * SECTOR - SECTOR))
        nvme_fit = write_fat_bootscript(nvme_raw, partitions[0], "nvme", work)
        if mbr_signature(nvme_raw) != nvme_signature:
            raise RuntimeError("NVMe disk signature changed")
        payload = args.out / "payload"
        payload.mkdir(exist_ok=True)
        nvme_gz = payload / "a5e-nvme-openwrt.img.gz"
        gzip_file(nvme_raw, nvme_gz)
        (payload / "IMAGE_BYTES").write_text(str(nvme_raw.stat().st_size) + "\n")
        (payload / "IMAGE_SHA256").write_text(sha256(nvme_raw) + "\n")
        spi_bin = payload / "armbian-u-boot-sunxi-with-spl.bin"
        spi_bin.write_bytes(boot)
        (payload / "SHA256SUMS").write_text(
            "".join(f"{sha256(payload / name)}  {name}\n" for name in PAYLOAD_NAMES)
        )
        sd_raw = work / "sd-installer.img"
        shutil.copyfile(original, sd_raw)
        write_mbr_signature(sd_raw, sd_signature)
        with sd_raw.open("r+b") as fd:
            # Clear the old SPL/staging area, then install the pinned Armbian blob.
            fd.seek(SECTOR)
            fd.write(bytes(partitions[0]["start"] * SECTOR - SECTOR))
            fd.seek(SD_SPL_OFFSET)
            fd.write(boot)
            fd.flush()
            os.fsync(fd.fileno())
        with sd_raw.open("rb") as fd:
            fd.seek(SD_SPL_OFFSET)
            if fd.read(len(boot)) != boot:
                raise RuntimeError("hybrid SD Armbian U-Boot readback mismatch")
        if write_fat_bootscript(sd_raw, partitions[0], "mmc", work) != nvme_fit:
            raise RuntimeError("SD and NVMe FIT images differ")
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
        print(f"SD root PARTUUID: {sd_signature:08x}-02; NVMe root PARTUUID: {nvme_signature:08x}-02")


if __name__ == "__main__":
    main()

