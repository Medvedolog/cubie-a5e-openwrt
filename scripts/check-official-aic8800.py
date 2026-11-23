"""Inspect each stock-reference/pwrseq candidate's embedded FIT DTB."""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def command(*args):
    return subprocess.check_output([str(x) for x in args], text=True).strip()


def fdt(path, node, prop, kind="s"):
    return command("fdtget", "-t", kind, path, node, prop)


def require(ok, info):
    if not ok:
        raise SystemExit(f"image check failed: {info}")


def verify(image, variant):
    with tempfile.TemporaryDirectory(prefix="cubie-a5e-image-") as folder:
        tmp = Path(folder)
        disk, fit, dtb = [tmp / name for name in ("disk.img", "uImage", "board.dtb")]
        with gzip.open(image, "rb") as stream, disk.open("wb") as output:
            shutil.copyfileobj(stream, output)
        table = json.loads(command("sfdisk", "-J", disk))["partitiontable"]
        parts = table["partitions"]
        require(len(parts) == 2, "expected boot and root partitions")
        boot, root = parts
        require(root["start"] > boot["start"] and root["size"] > 0, "partition layout")
        offset = boot["start"] * table.get("sectorsize", 512)
        subprocess.run(["mcopy", "-i", f"{disk}@@{offset}", "::uImage", str(fit)], check=True)
        images = command("fdtget", "-l", fit, "/images").split()
        nodes = [name for name in images if name.startswith("fdt")]
        require(len(nodes) == 1, "expected one DTS in kernel FIT")
        encoded = fdt(fit, f"/images/{nodes[0]}", "data", "bx")
        dtb.write_bytes(bytes(int(byte, 16) for byte in encoded.split()))
        require("radxa,cubie-a5e" in fdt(dtb, "/", "compatible").split(), "Cubie A5E identity")
        host = fdt(dtb, "/aliases", "ethernet2").rsplit("/", 1)[0]
        require(host.endswith("/mmc@4021000"), "onboard SDIO host path")
        require(fdt(dtb, host, "status") == "okay", "onboard SDIO enabled")
        require(fdt(dtb, host, "bus-width", "u") == "4", "4-bit SDIO")
        require(fdt(dtb, host, "max-frequency", "u") == "35000000", "35 MHz SDIO clock cap")
        require(bool(fdt(dtb, host, "vmmc-supply", "u")), "SDIO PL7 power supply")
        props = set(command("fdtget", "-p", dtb, host).split())
        if variant == "pwrseq-950":
            node = "/wifi-pwrseq"
            require(fdt(dtb, node, "compatible") == "mmc-pwrseq-simple", "pwrseq provider")
            require(fdt(dtb, node, "reset-gpios", "u").split()[1:] == ["1", "1", "1"],
                    "PM1 active-low reset")
            require(fdt(dtb, node, "post-power-on-delay-ms", "u") == "200", "200 ms reset delay")
            require(fdt(dtb, host, "mmc-pwrseq", "u") == fdt(dtb, node, "phandle", "u"),
                    "SDIO points to correct power sequence")
            require("vqmmc-supply" in props, "1.8 V SDIO I/O rail reference")
        else:
            require(not ({"mmc-pwrseq", "vqmmc-supply"} & props),
                    "stock DTB must lack custom SDIO power properties")
        print(f"PASS {image.name}: {variant} FIT, SDIO host limited to 35 MHz")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build_output", type=Path)
    parser.add_argument("variant", choices=("pwrseq-950", "stock-dtb"))
    args = parser.parse_args()
    device = list(args.build_output.glob("*-radxa_cubie-a5e.manifest"))
    common = list(args.build_output.glob("*-sunxi-cortexa53.manifest"))
    candidates = device or common
    require(len(candidates) == 1, "expected a unique device or common manifest")
    manifest = candidates[0]
    packages = {line.split()[0] for line in manifest.read_text().splitlines() if line.split()}
    expected = {"kmod-aic8800-sdio", "aic8800-sdio-firmware", "wpad-mbedtls"}
    require(expected <= packages, f"missing packages: {sorted(expected-packages)}")
    for fs in ("ext4", "squashfs"):
        image, = args.build_output.glob(f"*radxa_cubie-a5e-{fs}-sdcard.img.gz")
        verify(image, args.variant)
    print("PASS image structure and package manifest; hardware status: NOT_TESTED")


if __name__ == "__main__":
    main()
