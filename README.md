# OpenWrt for the Radxa Cubie A5E (Allwinner A527) with onboard Wi-Fi

**[Русская версия / Russian version](README.ru.md)**

A clean OpenWrt build for the Radxa Cubie A5E: OpenWrt main built from
source on GitHub Actions, with the onboard Wi-Fi (AIC8800D80, SDIO), both
Gigabit Ethernet ports, USB and M.2 NVMe.

> **Status: first builds. Nothing has been tested on hardware yet.**
> The table below is updated only from reports with logs from a board.

## Why a source build

OpenWrt main has the sunxi target on Linux 6.18, but no Allwinner A527 and
no Cubie A5E profile; OpenWrt 25.12 (Linux 6.12) has no A527 at all. There
is no official kernel for this board, so no official ImageBuilder either:
the image is built from OpenWrt sources at a pinned commit, with the A527
support and the Wi-Fi driver from ImmortalWrt (details in
[docs/PORTING-NOTES.md](docs/PORTING-NOTES.md)).

Consequence: **kmods from downloads.openwrt.org do not fit this kernel.**
All kmods for it will be published, signed, in this project's own apk
repository (planned, see below).

## Status

| Function | Status |
|---|---|
| Image builds in CI | in progress |
| Boots from microSD | not tested |
| eth0 (LAN, 192.168.1.1) / eth1 (WAN, DHCP) | not tested |
| Wi-Fi AP / client, 2.4 GHz | not tested |
| Wi-Fi AP / client, 5 GHz | not tested |
| USB 2.0 ports | not tested |
| USB 3.0 SuperSpeed | not available in this image (see below) |
| M.2 NVMe | not tested |
| reboot / power-off / sysupgrade | not tested |

**Board revisions and RAM.** Owners report that mainline U-Boot does not
boot every revision: the DRAM timings depend on the memory chips. This
build adds a fallback parameter set; boards that still do not boot need a
UART log (see [docs/COMMUNITY-FINDINGS.md](docs/COMMUNITY-FINDINGS.md#1-boot-dram-parameters-depend-on-the-board-revision)).

**USB 3.0 or NVMe.** The A527 has one combo PHY shared by the M.2 slot and
the USB 3.0 port (hardware limit). This image uses it for PCIe (M.2 NVMe),
like the Radxa BSP default; the USB-A ports work as USB 2.0. A USB3 variant
is planned ([PORTING-NOTES §4](docs/PORTING-NOTES.md#4-usb-what-works-and-what-does-not)).

## Download

Not yet: images are CI artifacts of
[Build image](../../actions/workflows/build.yml) runs until the first one
boots on a board.

## Repository layout

| Path | What |
|---|---|
| `target/`, `package/` | files added to the OpenWrt tree: A527 kernel patches and drivers, U-Boot/TF-A patches, the `aic8800` package |
| `patches/openwrt/` | changes to OpenWrt files (kernel config, the `radxa_cubie-a5e` device, board.d) |
| `config/diffconfig` | build configuration |
| `scripts/check-image.py` | checks of the built image (DTB in the FIT image, rootfs, kernel config) |
| `.github/workflows/build.yml` | the build: OpenWrt at a pinned commit, our files, `make`, checks |
| `docs/` | [porting notes](docs/PORTING-NOTES.md), [community findings](docs/COMMUNITY-FINDINGS.md); test plan and driver audit to follow |

The build runs on GitHub's runners or on a self-hosted runner
(`workflow_dispatch` input `runner`). Packages are signed with the
`APK_SIGN_KEY` repository secret (EC P-256 private key); without it a
throw-away key is used and nothing is published.

## Plan

1. Image that boots, with Wi-Fi — current step.
2. Signed apk repository on GitHub Pages with all kmods of this kernel.
3. Image checks in CI (started: `scripts/check-image.py`).
4. First boot: Wi-Fi access point "A5E" with a placeholder password and a
   LuCI warning until it is changed.
5. Image contents as in the Orange Pi Zero 3 project (LuCI, WireGuard/
   AmneziaWG, sing-box, modems, USB Ethernet/Wi-Fi, NVMe).
6. Rolling and fixed releases with notes.
7. After Wi-Fi works on hardware: audit of the aic8800 driver.
8. Later: Cubie A5E and aic8800 upstream in OpenWrt.

## Acknowledgements

- [ImmortalWrt](https://github.com/immortalwrt/immortalwrt): the
  A523/A527 target support, the Cubie A5E profile and the `aic8800` package
  this build is based on.
- [Radxa](https://github.com/radxa): the board, the BSP and
  [radxa-pkg/aic8800](https://github.com/radxa-pkg/aic8800).
- The mainline Linux developers of the Allwinner sun55i (A523/A527/T527)
  support.
- [OpenWrt](https://openwrt.org).

## License

GPL-2.0 ([LICENSE](LICENSE)). Files taken from other projects keep their
authors and licenses.
