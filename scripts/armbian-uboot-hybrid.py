#!/usr/bin/env python3
"""Safely replace only the Allwinner bootloader area in a Cubie A5E SD image.

The original OpenWrt kernel, partitions, rootfs, and DRAM-profile metadata
are kept byte-for-byte. This does *not* guarantee that Armbian U-Boot can boot
the OpenWrt FIT; hardware/serial-console testing is mandatory.
"""
import argparse
import gzip
import hashlib
import os
from pathlib import Path
import struct
import tempfile

OFFSET = 8192
SECTOR = 512


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--uboot", type=Path, required=True)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    boot = args.uboot.read_bytes()
    if len(boot) < 65536 or boot[4:12] != b"eGON.BT0":
        p.error("Armbian U-Boot is not a valid Allwinner eGON SPL image")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        raw = Path(work) / "image.img"
        with gzip.open(args.input, "rb") as fi, raw.open("wb") as fo:
            for block in iter(lambda: fi.read(1024 * 1024), b""):
                fo.write(block)
        with raw.open("r+b") as f:
            mbr = f.read(SECTOR)
            if mbr[510:512] != b"\x55\xaa":
                p.error("Input image does not contain a valid DOS partition table")
            first_start = min(
                struct.unpack_from("<I", mbr, 446 + i * 16 + 8)[0]
                for i in range(4)
                if mbr[446 + i * 16 + 4] != 0
            )
            partition_offset = first_start * SECTOR
            if OFFSET + len(boot) > partition_offset:
                p.error("Bootloader overlaps first partition: refuses to write")
            f.seek(OFFSET)
            old = f.read(len(boot))
            f.seek(OFFSET)
            f.write(boot)
            f.flush()
            os.fsync(f.fileno())
            f.seek(OFFSET)
            if f.read(len(boot)) != boot:
                p.error("Bootloader readback mismatch")
            f.seek(0)
            if f.read(SECTOR) != mbr:
                p.error("Partition table was unexpectedly modified")
        # gzip reproducibly (mtime=0, no original filename)
        with raw.open("rb") as fi, args.output.open("wb") as fo:
            with gzip.GzipFile(fileobj=fo, mode="wb", filename="", mtime=0, compresslevel=6) as gz:
                for block in iter(lambda: fi.read(1024 * 1024), b""):
                    gz.write(block)
        print("Armbian SPL/U-Boot bytes:", len(boot))
        print("First partition LBA:", first_start)
        print("Changed raw range:", OFFSET, "through", OFFSET + len(boot))
        print("Original image:", sha256(args.input))
        print("Hybrid image:", sha256(args.output))


if __name__ == "__main__":
    main()
