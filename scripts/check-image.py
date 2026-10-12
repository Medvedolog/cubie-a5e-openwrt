#!/usr/bin/env python3
"""Checks of a built Cubie A5E image, run by CI after the build.

Looks into the sdcard image itself, not into the build tree:
  - partition table: boot and rootfs partitions of a sane size
  - the bootloader at 8 KiB is our U-Boot
  - the DTB inside the FIT kernel image (boot partition, uImage):
    board compatible, Wi-Fi on mmc1 with its power sequence, both GMACs,
    the USB2 host controllers, the PCIe / USB3 combo PHY
  - the ext4 rootfs: aic8800 modules and firmware, wpad, NVMe, apk key,
    board.d network entry
  - the kernel config: options the board depends on

Needs: sfdisk, mtools (mcopy), dtc tools (fdtget), e2fsprogs (debugfs).
"""
import argparse
import glob
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile

FAILED = []


def check(ok, what):
    print(("  OK      " if ok else "  FAIL    ") + what)
    if not ok:
        FAILED.append(what)
    return ok


def run(*cmd):
    return subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True).stdout


def fdtget(dtb, node, prop, typ=None, default=None):
    cmd = ["fdtget"] + (["-t", typ] if typ else []) + [dtb, node, prop]
    try:
        return run(*cmd).strip()
    except subprocess.CalledProcessError:
        return default


def fit_dtb(uimage, out):
    """Extract the first fdt image of a FIT (itself a flattened device tree)."""
    images = run("fdtget", "-l", uimage, "/images").split()
    fdt = [i for i in images if i.startswith("fdt")]
    if not fdt:
        return None
    raw = run("fdtget", "-t", "bx", uimage, "/images/" + fdt[0], "data")
    with open(out, "wb") as f:
        f.write(bytes(int(b, 16) for b in raw.split()))
    return out


def check_dtb(dtb):
    print("== DTB in the FIT kernel image ==")
    compat = fdtget(dtb, "/", "compatible") or ""
    print("  compatible: " + compat)
    check("radxa,cubie-a5e" in compat, "board compatible radxa,cubie-a5e")
    status = lambda n: fdtget(dtb, n, "status", default="(missing)")
    nodes = {
        "/soc/mmc@4020000": "mmc0 (microSD)",
        "/soc/mmc@4021000": "mmc1 (AIC8800 Wi-Fi, SDIO)",
        "/soc/ethernet@4500000": "gmac0 (eth0, LAN)",
        "/soc/ethernet@4510000": "gmac1 (eth1, WAN)",
        "/soc/usb@4101000": "ehci0",
        "/soc/usb@4101400": "ohci0",
        "/soc/usb@4200000": "ehci1 (USB-A port, USB2)",
        "/soc/usb@4200400": "ohci1",
        "/soc/phy@4f00000": "PCIe/USB3 combo PHY",
        "/soc/pcie@4800000": "PCIe (M.2 NVMe)",
    }
    for node, what in nodes.items():
        check(status(node) == "okay", "%s %s: %s" % (what, node, status(node)))
    check(fdtget(dtb, "/soc/mmc@4021000", "mmc-pwrseq") is not None, "mmc1 has mmc-pwrseq")
    check(fdtget(dtb, "/soc/mmc@4021000", "vmmc-supply") is not None, "mmc1 has vmmc-supply")
    check(fdtget(dtb, "/wifi-pwrseq", "compatible") == "mmc-pwrseq-simple", "wifi-pwrseq node")
    # reset-gpios = <&r_pio 1 1 GPIO_ACTIVE_LOW>: bank M (1), pin 1, active low
    rg = (fdtget(dtb, "/wifi-pwrseq", "reset-gpios", "u") or "").split()
    check(rg[1:] == ["1", "1", "1"], "wifi-pwrseq reset-gpios is PM1 active low (%s)" % " ".join(rg))
    print("  INFO    combo PHY phy_use_sel = %s (0: PCIe, 1: USB3)"
          % fdtget(dtb, "/soc/phy@4f00000", "phy_use_sel", "u", "?"))
    print("  INFO    USB3 SuperSpeed controller (usb@4d00000): %s" % status("/soc/usb@4d00000"))


def check_rootfs(ext4):
    print("== rootfs (ext4 image) ==")

    def ls(path):
        try:
            out = run("debugfs", "-R", "ls -p " + path, ext4)
        except subprocess.CalledProcessError:
            return []
        names = []
        for line in out.splitlines():
            parts = line.strip("/").split("/")
            if len(parts) >= 5 and parts[4] not in (".", ".."):
                names.append(parts[4])
        return names

    def cat(path):
        try:
            return run("debugfs", "-R", "cat " + path, ext4)
        except subprocess.CalledProcessError:
            return ""

    kvers = ls("/lib/modules")
    check(len(kvers) == 1, "one kernel module directory: %s" % kvers)
    mods = ls("/lib/modules/" + kvers[0]) if kvers else []
    for m in ("aic8800_bsp.ko", "aic8800_fdrv.ko", "nvme.ko", "nvme-core.ko"):
        check(m in mods, "module " + m)
    check(not any("btlpm" in m or "aic_btusb" in m for m in mods), "no AIC8800 Bluetooth modules")
    fw = ls("/lib/firmware/aic8800/sdio")
    for f in ("fmacfw_8800d80_u02.bin", "fw_patch_8800d80_u02.bin",
              "lmacfw_rf_8800d80_u02.bin", "aic_userconfig_8800d80.txt"):
        check(f in fw, "firmware aic8800/sdio/" + f)
    check(any(n.startswith("aic8800") for n in ls("/etc/modules.d")), "modules.d autoload entry for aic8800")
    check("wpad" in ls("/usr/sbin") or "hostapd" in ls("/usr/sbin"), "wpad / hostapd")
    keys = ls("/etc/apk/keys")
    check(len(keys) > 0, "apk keys: %s" % keys)
    check("radxa,cubie-a5e" in cat("/etc/board.d/02_network"), "board.d/02_network knows radxa,cubie-a5e")
    rel = cat("/etc/openwrt_release")
    print("  INFO    " + " ".join(l for l in rel.splitlines() if l.startswith(("DISTRIB_RELEASE", "DISTRIB_REVISION"))))
    for f in ls("/etc/apk/repositories.d"):
        for line in cat("/etc/apk/repositories.d/" + f).splitlines():
            if line and not line.startswith("#"):
                print("  INFO    repository (%s): %s" % (f, line))


def check_image(img_gz, tmp):
    print("######## " + os.path.basename(img_gz))
    img = os.path.join(tmp, "img")
    with gzip.open(img_gz, "rb") as src, open(img, "wb") as dst:
        shutil.copyfileobj(src, dst)
    # sysupgrade images carry metadata after the gzip stream; gzip reads it fine
    parts = json.loads(run("sfdisk", "-J", img))["partitiontable"]["partitions"]
    for i, p in enumerate(parts, 1):
        print("  part%d start %d size %d MiB type %s" % (i, p["start"], p["size"] * 512 >> 20, p["type"]))
    check(len(parts) == 2, "two partitions (boot, rootfs)")
    boot, root = parts[0], parts[1]
    check(16 <= boot["size"] * 512 >> 20 <= 64, "boot partition 16..64 MiB")
    check(100 <= root["size"] * 512 >> 20 <= 1024, "rootfs partition 100..1024 MiB (no 10 GB partitions)")
    with open(img, "rb") as f:
        head = f.read(boot["start"] * 512)
    check(b"U-Boot SPL 2026" in head, "U-Boot SPL at the start of the image")
    check(b"retrying with alternative parameters" in head,
          "U-Boot SPL has the DRAM alternative-parameter fallback")
    uimage = os.path.join(tmp, "uImage")
    subprocess.run(["mcopy", "-o", "-i", "%s@@%d" % (img, boot["start"] * 512), "::uImage", uimage], check=True)
    dtb = fit_dtb(uimage, os.path.join(tmp, "fit.dtb"))
    if check(dtb is not None, "FIT image has a device tree"):
        check_dtb(dtb)
    if "ext4" in os.path.basename(img_gz):
        ext4 = os.path.join(tmp, "root.ext4")
        with open(img, "rb") as f, open(ext4, "wb") as o:
            f.seek(root["start"] * 512)
            left = root["size"] * 512
            while left:
                b = f.read(min(left, 1 << 22))
                if not b:
                    break
                o.write(b)
                left -= len(b)
        check_rootfs(ext4)
    os.unlink(img)


def check_kconfig(build_dir):
    print("== kernel config ==")
    cfgs = glob.glob(os.path.join(build_dir, "linux-sunxi_*", "linux-*", ".config"))
    if not check(len(cfgs) == 1, "kernel .config found"):
        return
    cfg = open(cfgs[0]).read().splitlines()
    want = {
        "CONFIG_PWRSEQ_SIMPLE": "y",
        "CONFIG_MMC_SUNXI": "y",
        "CONFIG_DWMAC_SUN55I": "y",
        "CONFIG_DWMAC_SUN8I": "y",
        "CONFIG_SUN55I_A523_CCU": "y",
        "CONFIG_PINCTRL_SUN55I_A523": "y",
        "CONFIG_PINCTRL_SUN55I_A523_R": "y",
        "CONFIG_AW_INNO_COMBOPHY": "y",
        "CONFIG_PCIE_SUN55I_RC": "y",
        "CONFIG_USB_EHCI_HCD": "y",
        "CONFIG_USB_OHCI_HCD": "y",
    }
    for k, v in want.items():
        check("%s=%s" % (k, v) in cfg, "%s=%s" % (k, v))
    # with RESET_GPIO, pwrseq-simple asks the reset framework for its GPIO,
    # which handles 2-cell GPIO specifiers only (sunxi has 3): the Wi-Fi
    # power sequence would fail to probe
    check("CONFIG_RESET_GPIO=y" not in cfg and "CONFIG_RESET_GPIO=m" not in cfg,
          "CONFIG_RESET_GPIO off (pwrseq-simple GPIO fallback)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="bin/targets/sunxi/cortexa55")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--build-dir", required=True, help="build_dir/target-...")
    a = ap.parse_args()

    imgs = sorted(glob.glob(os.path.join(a.out, "*%s*sdcard.img.gz" % a.profile)))
    check(any("ext4" in i for i in imgs) and any("squashfs" in i for i in imgs),
          "ext4 and squashfs sdcard images: %s" % [os.path.basename(i) for i in imgs])
    man = glob.glob(os.path.join(a.out, "*%s.manifest" % a.profile))
    if check(len(man) == 1, "manifest"):
        pkgs = dict(l.split(" - ", 1) for l in open(man[0]).read().splitlines() if " - " in l)
        for p in ("kmod-aic8800-sdio", "aic8800-sdio-firmware", "kmod-nvme", "wpad-mbedtls",
                  "luci", "kernel"):
            check(p in pkgs, "manifest: %s %s" % (p, pkgs.get(p, "")))
        for p in ("mwan3", "luci-app-mwan3", "watchcat", "nlbwmon", "luci-app-nlbwmon",
                  "kmod-aic8800-btusb", "wpad-basic-mbedtls"):
            check(p not in pkgs, "manifest: no %s" % p)
    with tempfile.TemporaryDirectory() as tmp:
        for i in imgs:
            check_image(i, tmp)
    check_kconfig(a.build_dir)
    print()
    if FAILED:
        print("%d check(s) failed:" % len(FAILED))
        for f in FAILED:
            print("  - " + f)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
