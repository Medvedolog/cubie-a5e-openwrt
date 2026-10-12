#!/usr/bin/env python3
"""Release notes for a Cubie A5E build: which image to flash, in English and
Russian.

usage: release-notes.py --images DIR --dram-dir config/dram --kind test|latest|tag
                        [--build-info FILE] [--base-url URL] [--tag TAG]

Prints Markdown. The variant table is made from the images present in DIR
(…-radxa_cubie-a5e-dram-<profile>-ext4-sdcard.img.gz) and the comment header
of config/dram/<profile>.conf ("# en:" and "# ru:" lines).
"""
import argparse
import glob
import os
import re

MAINLINE = (
    "**Main image** for all revisions: mainline timings at 936 MHz with the "
    "fallback set (as Armbian).",
    "**Основной образ** для всех ревизий: параметры mainline на 936 МГц с "
    "запасным набором (как в Armbian).",
)


def profile_info(dram_dir, name):
    if name == "universal":
        return MAINLINE, None
    path = os.path.join(dram_dir, name + ".conf")
    if not os.path.exists(path):
        return ("", ""), None
    en = ru = ""
    vals = {}
    for line in open(path):
        line = line.strip()
        if line.startswith("# en:"):
            en = line[5:].strip()
        elif line.startswith("# ru:"):
            ru = line[5:].strip()
        elif line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    return (en, ru or en), vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--dram-dir", required=True)
    ap.add_argument("--kind", required=True, choices=["test", "latest", "tag"])
    ap.add_argument("--build-info")
    ap.add_argument("--base-url", default="")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()

    imgs = sorted(glob.glob(os.path.join(a.images, "*-dram-*-sdcard.img.gz")))
    variants = {}
    for i in imgs:
        m = re.search(r"-dram-(.+?)-(ext4|squashfs)-sdcard\.img\.gz$", os.path.basename(i))
        if m:
            variants.setdefault(m.group(1), {})[m.group(2)] = os.path.basename(i)
    order = ["universal"] + sorted(v for v in variants if v != "universal")

    out = []
    w = out.append
    if a.kind == "test":
        w("**Test build — NOT a release.** Replaced by the next test build. "
          "Nothing in it is verified on hardware unless the status table in the "
          "README says so.\n")
        w("**Тестовая сборка — НЕ релиз.** Заменяется следующей тестовой сборкой. "
          "На железе ничего не проверено, если в таблице статуса README не сказано "
          "иное.\n")
    elif a.kind == "latest":
        w("Rolling build of `main`, replaced on every change. / "
          "«Скользящая» сборка `main`, заменяется при каждом изменении.\n")

    if a.build_info and os.path.exists(a.build_info):
        info = open(a.build_info).read().strip()
        w("<details><summary>Build / сборка</summary>\n\n```\n%s\n```\n</details>\n" % info)

    w("## Which image / какой образ\n")
    w("**Start with `universal`.** One image for all board revisions, like "
      "Armbian's: mainline U-Boot DRAM timings at 936 MHz with a fallback set "
      "that is tried when the memory check fails. The other images are "
      "**fallbacks** for boards that do not start with it: they differ only in "
      "U-Boot's DRAM settings (kernel, packages and settings are the same) and "
      "are tuned to one memory type. Please report which image started on "
      "your board, and send the UART log if `universal` did not.\n")
    w("**Начинайте с `universal`.** Один образ для всех ревизий платы, как у "
      "Armbian: параметры DRAM mainline U-Boot на 936 МГц и запасной набор, "
      "который пробуется, если проверка памяти не прошла. Остальные образы — "
      "**запасные** для плат, которые с ним не стартуют: отличаются только "
      "настройками DRAM в U-Boot (ядро, пакеты и настройки те же) и "
      "подобраны под конкретную память. Напишите, какой образ запустился на "
      "вашей плате, а если `universal` не стартовал — пришлите лог UART.\n")
    w("| Profile / профиль | For / для | TPR6 / TPR10 / TPR11 / TPR12, DRAM clock | ext4 | squashfs |")
    w("|---|---|---|---|---|")
    for name in order:
        if name not in variants:
            continue
        (en, ru), vals = profile_info(a.dram_dir, name)
        tpr = ("0x38000000 / 0x802f3333 / 0xc7c5c4c2 / 0x3533302f, 936 MHz" if name == "universal"
               else " / ".join(vals.get(k, "?") for k in ("TPR6", "TPR10", "TPR11", "TPR12"))
               + ", %s MHz" % vals.get("CLK", "936"))
        desc = en if en == ru else "%s<br>%s" % (en, ru)

        def link(kind):
            f = variants[name].get(kind)
            if not f:
                return "—"
            return "[%s](%s%s)" % (kind, a.base_url, f) if a.base_url else f

        w("| `%s` | %s | %s | %s | %s |" % (name, desc, tpr, link("ext4"), link("squashfs")))
    w("")
    w("How to find your memory: the vendor image's U-Boot prints it with "
      "`sunxi_dram_para` on the UART console (pins 6/8/10, 115200), or read "
      "the marking of the RAM chip. New profiles: open an issue with that "
      "output. / Как узнать свою память: `sunxi_dram_para` в консоли U-Boot "
      "вендорского образа (UART, пины 6/8/10, 115200) или маркировка чипа. "
      "Новый профиль — issue с этим выводом.\n")

    w("## Write to a microSD card / запись на карту\n")
    w("RAW image: `dd`, USBImager, balenaEtcher (takes `.gz` directly), Win32 "
      "Disk Imager. Not PhoenixCard. / RAW-образ: `dd`, USBImager, "
      "balenaEtcher (берёт `.gz` сразу), Win32 Disk Imager. Не PhoenixCard.\n")
    w("```\ngunzip -c openwrt-…-radxa_cubie-a5e-dram-<profile>-ext4-sdcard.img.gz | "
      "sudo dd of=/dev/sdX bs=4M conv=fsync\n```\n")
    w("First boot: LuCI at http://192.168.1.1 on `eth0` (LAN), `eth1` is WAN "
      "(DHCP). / Первая загрузка: LuCI на http://192.168.1.1 через `eth0` (LAN), "
      "`eth1` — WAN (DHCP).\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
