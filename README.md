# OpenWrt for the Radxa Cubie A5E (Allwinner A527) with onboard Wi-Fi

**[Русская версия / Russian version](README.ru.md)**

A clean OpenWrt build for the Radxa Cubie A5E: OpenWrt main with the A527
support that is under review, built from source on GitHub Actions, with
the onboard Wi-Fi (AIC8800D80, SDIO), both Gigabit Ethernet ports, USB and
M.2 NVMe.

> **Status: hardware testing underway (2026-10-13).** On a Cubie A5E V1.1 / 4 GB Micron board the microSD ext4 rootfs boots. The AIC8800D80 sometimes loads firmware and registers a PHY, but another cold boot fails with SDIO `-110`. **Reliable AP operation and recovery have not yet been demonstrated.**
> Evidence and unresolved issues: [AIC8800 / SDIO field report (Russian)](docs/AIC8800-SDIO-WIFI.ru.md).

## Why a source build

OpenWrt has no Allwinner A527 yet. The support is in review:
[openwrt/openwrt#23296](https://github.com/openwrt/openwrt/pull/23296)
"sunxi: add support for A527/T527 boards" by the sunxi maintainer (new
`cortexa55` subtarget, `radxa_cubie-a5e` profile). This project builds that
branch at a pinned commit and adds what it lacks for this board: the
AIC8800 Wi-Fi driver (from ImmortalWrt), the Wi-Fi power sequence, a DRAM
fallback for more board revisions, NVMe packages
([docs/PORTING-NOTES.md](docs/PORTING-NOTES.md)). Once the PR is merged the
build moves to the official snapshot and keeps only the Wi-Fi driver here,
as the Orange Pi Zero 3 project does.

Consequence: **kmods from downloads.openwrt.org do not fit this kernel.**
All kmods for it will be published, signed, in this project's own apk
repository (planned, see below).

## Status

| Function | Status |
|---|---|
| Image builds in CI | yes; image checks pass but do not verify hardware behaviour |
| Boots from microSD | **confirmed:** ext4 rootfs on the 4 GB Micron test board |
| eth0 (LAN, 192.168.1.1) / eth1 (WAN, DHCP) | configuration present; both Ethernet ports not fully tested |
| Wi-Fi AP / client, 2.4 GHz | not tested |
| Wi-Fi 5 GHz / AIC8800D80 | **partial:** SDIO and firmware/PHY work on some boots; `-110` on others; AP/client/DHCP not validated |
| USB 2.0 ports | not tested |
| USB 3.0 SuperSpeed | not available in this image (see below) |
| M.2 NVMe | not tested |
| reboot / power-off / sysupgrade | not tested |

**Board revisions and RAM.** Owners report that mainline U-Boot does not
boot every revision: the DRAM timings depend on the memory chips. This
build adds a fallback parameter set and one image per known memory
profile (`dram-universal`, `dram-micron-4g-m6`, …); boards that still do
not boot need a UART log (see [docs/COMMUNITY-FINDINGS.md](docs/COMMUNITY-FINDINGS.md#1-boot-dram-parameters-depend-on-the-board-revision)).

**USB 3.0 or NVMe.** The A527 has one combo PHY shared by the M.2 slot and
the USB 3.0 port (hardware limit). This image uses it for PCIe (M.2 NVMe),
like the Radxa BSP default; the USB-A ports work as USB 2.0. A USB3 variant
is planned ([PORTING-NOTES §4](docs/PORTING-NOTES.md#4-usb-what-works-and-what-does-not)).

## Download

- Test builds: pre-release
  [cubie-a5e-test](../../releases/tag/cubie-a5e-test), replaced by every
  build of a working branch. **Experimental images: ext4 booted, but Wi-Fi reliability is unproven.**
- Later: the rolling `cubie-a5e-snapshot-latest` from `main` and fixed
  releases with notes (`docs/releases/`).

**Flash `…-dram-universal-…` first**: one image for all board revisions,
like Armbian's (mainline DRAM timings at 936 MHz plus a fallback set). The
other images (`…-dram-micron-4g-m6-…`, …) are fallbacks tuned to one memory
type for boards that do not start with it; they differ only in U-Boot's
DRAM settings.

## Repository layout

| Path | What |
|---|---|
| `target/`, `package/` | files added to the OpenWrt tree: Wi-Fi power sequence (DTS), U-Boot DRAM fallback, the `aic8800` package |
| `patches/openwrt/` | changes to files of the OpenWrt tree (PCI feature of the subtarget) |
| `config/diffconfig` | build configuration |
| `scripts/check-image.py` | checks of the built image (DTB in the FIT image, rootfs, kernel config) |
| `.github/workflows/build.yml` | the build: PR #23296 at a pinned commit, our files, `make`, checks |
| `docs/` | [AIC8800/SDIO field report (RU)](docs/AIC8800-SDIO-WIFI.ru.md), [manual recovery (RU)](docs/AIC8800-RECOVERY.ru.md), [hardware test plan](docs/TEST-PLAN.md), [roadmap](docs/ROADMAP.md), [porting notes](docs/PORTING-NOTES.md), [GitHub build guide (RU)](docs/GITHUB-ACTIONS-GUIDE.ru.md) |

The build runs on GitHub's runners or on a self-hosted runner
(`workflow_dispatch` input `runner`). Packages are signed with the
`APK_SIGN_KEY` repository secret (EC P-256 private key); without it a
throw-away key is used and nothing is published.

## Wi-Fi field findings

- Physical microSD host: `4020000.mmc`; onboard Wi-Fi host: `4021000.mmc`. The enumerated `mmc0/mmc1` names can swap between boots.
- Successful AIC8800 SDIO I/O was measured at **33.33 MHz actual** (35 MHz requested). The vendor override to 150 MHz has been disabled.
- The onboard MAC `fc:23:cd:03:8e:78` was stable across the reboots examined. A test-branch UCI fix uses the MAC to prevent duplicate `radioX` sections caused by renumbered MMC paths.
- A **manual-only** `aic8800-recover --check/--run` has been added, inspired by OPIZ3. It targets only `4021000.mmc` but is **not yet tested on the board**. Run recovery only over UART or wired Ethernet.
- Firmware upload timeout `-110` is still under investigation. Planned isolated A/B tests: 25 MHz SDIO, BLDO1 supply, MMC power sequence and manual recovery.

See the [full field report](docs/AIC8800-SDIO-WIFI.ru.md), [recovery instructions](docs/AIC8800-RECOVERY.ru.md), and [test plan](docs/TEST-PLAN.md).

## Driver origin and exact version

The package is based on **ImmortalWrt `r5`** packaging, using the
**Radxa AIC8800 source/firmware at `89f865b8` (2026-03-10)**.
This branch adds its own `090` SDIO clock patch and the **`100`**
radiotap/FORTIFY patch imported from akorshun (originally named `090`);
the **local package release is now `r6`**. Source and patch provenance:
[`package/kernel/aic8800/README.md`](package/kernel/aic8800/README.md).
A tester can also inspect `cat /etc/aic8800-origin` on the new image.

## Plan

Full plan with tasks and status: [docs/ROADMAP.md](docs/ROADMAP.md).

1. First image that builds — done (test pre-release `cubie-a5e-test`).
2. First boot on hardware: both Ethernet ports, USB, NVMe, reboot,
   sysupgrade.
3. Wi-Fi: AP and client, 2.4 and 5 GHz, WPA2/WPA3, cold start.
4. Own SDK, ImageBuilder and signed apk repository with all kmods of this
   kernel; driver fixes delivered by `apk upgrade`.
5. Image contents as in the Orange Pi Zero 3 project; first boot with the
   "A5E" access point and a LuCI password warning.
6. Test plan, `main` branch, beta releases.
7. AIC8800 driver audit and fixes.
8. One image for all memory types (several DRAM sets in U-Boot).
9. USB 3.0 image variant.
10. Upstream: reports and fixes for openwrt/openwrt#23296; after the merge,
    the official snapshot plus only the Wi-Fi driver from here.

## Acknowledgements

- [OpenWrt](https://openwrt.org) and its sunxi maintainer Zoltan Herpai
  for the A527/T527 support this build is based on.
- [ImmortalWrt](https://github.com/immortalwrt/immortalwrt): the
  `aic8800` package and the first A527/Cubie A5E support.
- [Radxa](https://github.com/radxa): the board, the BSP and
  [radxa-pkg/aic8800](https://github.com/radxa-pkg/aic8800).
- The mainline Linux developers of the Allwinner sun55i (A523/A527/T527)
  support.

## License

GPL-2.0 ([LICENSE](LICENSE)). Files taken from other projects keep their
authors and licenses.
