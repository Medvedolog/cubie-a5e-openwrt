"""Reject unintended CPU/voltage changes in the final A5E bench FIT DTB."""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from importlib import import_module

base = import_module("check-official-aic8800")
cmd, fdt, require = base.command, base.fdt, base.require
board = import_module("check-a5e-dvfs-dtb")


def verify(dtb):
    nodes = board.parse(dtb.read_bytes())
    board.verify(nodes)
    big = [nodes[f"/cpus/cpu@{i << 8:x}"] for i in range(4, 8)]
    clock_ids = {board.cells(n.get("clocks"), 2) for n in big}
    require(len(clock_ids) == 1, "big cluster must share one clock")
    handle, selector = next(iter(clock_ids))
    provider = nodes["/soc/clock-controller@8817000"]
    require(selector == 9 and board.cells(provider.get("phandle")) == (handle,) and
            provider.get("compatible") == b"allwinner,sun55i-a523-cpu-ccu\x00" and
            board.cells(provider.get("reg"), 2) == (0x08817000, 0x80) and
            board.cells(provider.get("#clock-cells")) == (1,),
            "big clock must resolve to the A523 CPU CCU and its cluster-B output")
    print(f"PASS: only CPU4–7 get the shared clock (selector {selector}) and three exact AXP323 OPPs")



def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("path", type=Path, help="firmware output directory, or a standalone fixture DTB")
    source = args.parse_args().path
    if source.is_file():
        verify(source)
        return
    for fs in ("ext4", "squashfs"):
        image, = source.glob(f"*radxa_cubie-a5e-{fs}-sdcard.img.gz")
        with TemporaryDirectory(prefix="a5e-dvfs-dtb-") as tmp:
            disk, fit, dtb = (Path(tmp) / n for n in ("disk.img", "uImage", "a5e.dtb"))
            with gzip.open(image, "rb") as read, disk.open("wb") as write:
                shutil.copyfileobj(read, write)
            table = json.loads(cmd("sfdisk", "-J", disk))["partitiontable"]
            boot, _ = table["partitions"]
            offset = boot["start"] * table.get("sectorsize", 512)
            subprocess.run(["mcopy", "-i", f"{disk}@@{offset}", "::uImage", fit], check=True)
            nodes = [n for n in cmd("fdtget", "-l", fit, "/images").split() if n.startswith("fdt")]
            require(len(nodes) == 1, "expected one FIT board DTB")
            dtb.write_bytes(bytes(int(v, 16) for v in fdt(fit, f"/images/{nodes[0]}", "data", "bx").split()))
            verify(dtb)


if __name__ == "__main__":
    main()
