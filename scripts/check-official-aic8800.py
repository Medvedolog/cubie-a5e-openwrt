"""Inspect each stock-reference/pwrseq candidate's embedded FIT DTB."""
import argparse
import gzip
import json
import re
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



LUCI_PACKAGES = {"luci", "luci-base", "uhttpd", "luci-theme-footstrap", "luci-theme-bootstrap"}


def verify_luci(ext4):
    config = command("debugfs", "-R", "cat /etc/config/luci", ext4)
    # Read the main/core stanza only; the theme registry is populated on boot.
    main = re.search(r"(?m)^config[ 	]+core[ 	]+'main'[ 	]*\n(.*?)(?=^config[ 	]|\Z)",
                     config, re.S)
    require(main is not None, "LuCI main config in firmware")
    themes = re.findall(r"(?m)^[ 	]*option[ 	]+mediaurlbase[ 	]+'([^']+)'[ 	]*$",
                        main.group(1))
    require(themes == ["/luci-static/footstrap"], "Footstrap must be the LuCI default")
    for theme in ("footstrap", "bootstrap"):
        for asset in (f"/www/luci-static/{theme}/cascade.css",
                      f"/usr/share/ucode/luci/template/themes/{theme}/header.ut"):
            # LuCI can install compiled ucode templates under the .ut name.
            # Inspect the inode without treating the resource bytes as text.
            stat = command("debugfs", "-R", f"stat {asset}", ext4)
            require(re.search(r"\bType:\s+regular\b", stat)
                    and re.search(r"\bSize:\s+[1-9][0-9]*\b", stat),
                    f"missing, empty or non-regular LuCI asset {asset}")
    # debugfs returns success even when a requested path does not exist.
    status = command("debugfs", "-R", "stat /etc/rc.d/S50uhttpd", ext4)
    require("Type: symlink" in status and "init.d/uhttpd" in status,
            "uhttpd must be enabled at boot")


def verify_aic_recovery(ext4):
    tool = "/usr/sbin/aic8800-recover"
    stat = command("debugfs", "-R", f"stat {tool}", ext4)
    require("Type: regular" in stat and re.search(r"\bMode:\s+0755\b", stat),
            "manual AIC8800 recovery executable")
    script = command("debugfs", "-R", f"cat {tool}", ext4)
    require(all(token in script for token in (". /lib/aic8800.sh", "--check", "--run")),
            "AIC8800 recovery includes manual check and run commands")
    require("99-cubie-a5e-test-config" not in script,
            "AIC8800 recovery must not run legacy first-boot settings")
    helpers = command("debugfs", "-R", "cat /lib/aic8800.sh", ext4)
    require("AIC_CONTROLLER=4021000.mmc" in helpers and "aic_no_storage_on_host" in helpers,
            "AIC8800 recovery must target only the onboard Wi-Fi controller")
    for path in ("/etc/init.d/aic8800-recover", "/etc/crontabs/aic8800-recover",
                 "/etc/uci-defaults/99-cubie-a5e-test-config"):
        inode = subprocess.check_output(
            ["debugfs", "-R", f"stat {path}", str(ext4)], text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        require(not inode, f"unexpected automatic recovery or legacy settings at {path}")


def verify_board_ui(ext4):
    rpc = "/usr/libexec/rpcd/luci.a5e-board"
    stat = command("debugfs", "-R", f"stat {rpc}", ext4)
    require("Type: regular" in stat and re.search(r"\bMode:\s+0755\b", stat),
            "A5E LuCI board RPC executable")
    for path in ("/usr/share/rpcd/acl.d/luci-app-a5e-board.json",
                 "/usr/share/luci/menu.d/luci-app-a5e-board.json"):
        raw = command("debugfs", "-R", f"cat {path}", ext4)
        require(bool(raw) and isinstance(json.loads(raw), dict), f"A5E board UI data missing at {path}")
    for path in ("/www/luci-static/resources/view/status/include/15_a5e_board.js",
                 "/www/luci-static/resources/view/a5e-board/cpufreq.js"):
        require(bool(command("debugfs", "-R", f"cat {path}", ext4)), f"missing A5E board view {path}")


def verify_rootfs(disk, tmp, root, sector_size, feed_url, public_key,
                  require_luci=False, require_recovery=False, require_board=False):
    ext4 = tmp / "root.ext4"
    # Avoid copying any padding or data past the root partition.
    with disk.open("rb") as read, ext4.open("wb") as write:
        read.seek(root["start"] * sector_size)
        pending = root["size"] * sector_size
        while pending:
            data = read.read(min(4 * 1024 * 1024, pending))
            require(data, "truncated root filesystem partition")
            write.write(data)
            pending -= len(data)
    repos = command("debugfs", "-R", "cat /etc/apk/repositories.d/distfeeds.list", ext4)
    entries = [line.strip() for line in repos.splitlines()
               if line.strip() and not line.lstrip().startswith("#")]
    require(entries == [feed_url], "firmware must only use its immutable signed feed")
    bundled = subprocess.check_output(
        ["debugfs", "-R", "cat /etc/apk/keys/public-key.pem", str(ext4)]
    )
    require(bundled == public_key.read_bytes(), "matching trusted APK signing key in firmware")
    defaults = command("debugfs", "-R", "cat /etc/apk/repositories.d/customfeeds.list", ext4)
    require(not any(line.strip() and not line.lstrip().startswith("#")
                    for line in defaults.splitlines()), "no unexpected additional feed")
    if require_luci:
        verify_luci(ext4)
    if require_recovery:
        verify_aic_recovery(ext4)
    if require_board:
        verify_board_ui(ext4)


def verify(image, variant, feed_url=None, public_key=None, require_luci=False,
           require_recovery=False, require_board=False):
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
        if feed_url and image.name.endswith("-ext4-sdcard.img.gz"):
            verify_rootfs(disk, tmp, root, table.get("sectorsize", 512),
                          feed_url, public_key, require_luci, require_recovery, require_board)
            print(f"PASS {image.name}: immutable APK feed and matching public key in ext4 rootfs")
            if require_luci:
                print(f"PASS {image.name}: LuCI starts with Footstrap default and Bootstrap available")
            if require_recovery:
                print(f"PASS {image.name}: manual-only AIC8800 recovery present")
            if require_board:
                print(f"PASS {image.name}: A5E CPU and temperature LuCI board UI present")
        print(f"PASS {image.name}: {variant} FIT, SDIO host limited to 35 MHz")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build_output", type=Path)
    parser.add_argument("variant", choices=("pwrseq-950", "stock-dtb"))
    parser.add_argument("--filesystem", choices=("ext4", "squashfs"), action="append")
    parser.add_argument("--feed-url")
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--require-luci-footstrap", action="store_true")
    parser.add_argument("--require-aic-recovery", action="store_true")
    parser.add_argument("--require-board-ui", action="store_true")
    args = parser.parse_args()
    if bool(args.feed_url) != bool(args.public_key):
        parser.error("--feed-url and --public-key must be set together")
    filesystems = args.filesystem or ("ext4", "squashfs")
    if args.feed_url and "ext4" not in filesystems:
        parser.error("signed feed verification requires the ext4 image")
    if (args.require_luci_footstrap or args.require_aic_recovery or args.require_board_ui) and not args.feed_url:
        parser.error("LuCI and recovery checks require signed ext4 rootfs verification")
    device = list(args.build_output.glob("*-radxa_cubie-a5e.manifest"))
    common = list(args.build_output.glob("*-sunxi-cortexa53.manifest"))
    candidates = device or common
    require(len(candidates) == 1, "expected a unique device or common manifest")
    manifest = candidates[0]
    packages = {line.split()[0] for line in manifest.read_text().splitlines() if line.split()}
    expected = {"kmod-aic8800-sdio", "aic8800-sdio-firmware", "wpad-mbedtls"}
    if args.require_luci_footstrap:
        expected |= LUCI_PACKAGES
    if args.require_aic_recovery:
        expected.add("aic8800-recovery")
    if args.require_board_ui:
        expected.add("luci-app-a5e-board")
    require(expected <= packages, f"missing packages: {sorted(expected-packages)}")
    for fs in filesystems:
        image, = args.build_output.glob(f"*radxa_cubie-a5e-{fs}-sdcard.img.gz")
        verify(image, args.variant, args.feed_url, args.public_key,
               args.require_luci_footstrap, args.require_aic_recovery, args.require_board_ui)
    print("PASS image structure and package manifest; hardware status: NOT_TESTED")


if __name__ == "__main__":
    main()
