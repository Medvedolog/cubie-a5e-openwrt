# Roadmap

Development plan in the order of work. Updated **2026-10-13** with the
first hardware evidence. "Done" still distinguishes source / CI from
hardware validation. The Micron 4 GB board boots ext4 from microSD;
AIC8800 firmware sometimes loads, sometimes fails with SDIO `-110`.
See [field report](AIC8800-SDIO-WIFI.ru.md) and [test plan](TEST-PLAN.md).

| Stage | What | Status |
|---|---|---|
| 0 | Repository, build base, research | done |
| 1 | First image that builds | **done** (multiple CI builds succeeded; hardware ext4 boot confirmed) |
| 2 | First boot on hardware | **partial:** microSD/ext4 confirmed; ports/reboot/sysupgrade pending |
| 3 | Wi-Fi works (AP and client, 2.4/5 GHz) | **in progress:** AIC8800 SDIO/firmware/PHY intermittent; AP/client tests pending |
| 4 | Own SDK, ImageBuilder and signed apk repository | planned |
| 5 | Image contents and first-boot setup | **partial:** laboratory UCI defaults and MAC/radioX fix; secure production AP pending |
| 6 | Test plan and releases | test plan added, test releases; gate still pending |
| 7 | AIC8800 driver audit and fixes | **started:** 150 MHz override disabled; -110 under investigation |
| 8 | One image for all memory types | planned |
| 9 | USB 3.0 image variant | planned |
| 10 | Upstream: OpenWrt PR, official snapshot | ongoing |

## 0. Repository, build base, research — done

- Structure as in the Orange Pi Zero 3 project: `package/`, `target/`,
  `patches/openwrt/`, `config/`, `scripts/`, `.github/workflows/`, `docs/`.
- Base: the branch of [openwrt/openwrt#23296](https://github.com/openwrt/openwrt/pull/23296)
  (sunxi A527/T527 by the sunxi maintainer) at a pinned commit, plus what
  it lacks for this board ([PORTING-NOTES](PORTING-NOTES.md)).
- Sources studied: ImmortalWrt, Armbian, Radxa BSP and overlays, DietPi,
  community builds and the 4PDA topic ([COMMUNITY-FINDINGS](COMMUNITY-FINDINGS.md)).

## 1. First image that builds — done for experimental images

- [x] CI from source: OpenWrt commit recorded, `dl/` and ccache caches,
  GitHub or self-hosted runner, a new push waits for the running build.
- [x] Wi-Fi power sequence (patch 950), AIC8800 package, PCI feature for
  NVMe, U-Boot DRAM fallback (420).
- [x] One image per DRAM profile (`config/dram/*.conf`): `universal`,
  `micron-4g-m6`.
- [x] Image checks (`scripts/check-image.py`): DTB in the FIT image, U-Boot,
  partitions, rootfs contents, kernel options.
- [x] Publishing: test builds as pre-release `cubie-a5e-test` with a table
  of images.
- [x] Later builds succeeded and test images were published; ext4 rootfs on a Micron 4 GB board verified from dmesg. New commits still require their own CI result.

Exit: pre-release `cubie-a5e-test` with both DRAM images, all checks pass.

## 2. First boot on hardware

On the project's board (V1.1, Micron 4 GB, image `dram-micron-4g-m6`),
then on testers' boards.

- [x] Kernel reached ext4 rootfs read-write with DRAM initialized on the Micron 4 GB test board. Full UART power-on log / cross-board tests remain pending.
- [ ] Both Ethernet ports: which jack is `eth0` (LAN) and `eth1` (WAN);
  link at 1 Gbit/s; reboot keeps both ports.
- [x] microSD ext4 rootfs observed; [ ] squashfs image and `sysupgrade` not tested.
- [ ] USB 2.0 ports; M.2 NVMe (`lspci`, `nvme list`, read/write).
- [ ] reboot and power-off (TF-A PSCI; fallbacks known from other T527
  work: watchdog restart priority, AXP717 soft power-off).
- [ ] Temperature sensors, CPU frequency (cpufreq is not in the PR; take
  it from ImmortalWrt if missing).
- [ ] Update the README status table from the reports.

Exit: the board boots, both ports work, the image survives reboot and
sysupgrade.

## 3. Wi-Fi works

- [ ] `aic8800_bsp` / `aic8800_fdrv` register reliably after every cold start: one success and one `-110` failure on the same microSD; PHY observed after successful firmware load. `wlan0`/AP readiness not independently confirmed.
- [ ] AP 2.4 and 5 GHz with WPA2 and WPA3 (WPA2 failures were reported on
  older builds); country code set vs unset.
- [ ] Client mode (LuCI "Join network"); AP and client together.
- [ ] Throughput with iperf3 (reports: ~110 Mbit/s mainline vs 290 Mbit/s
  vendor kernel).
- [ ] If it fails: firmware A/B (radxa-pkg set vs vendor-kernel set,
  [COMMUNITY-FINDINGS §7](COMMUNITY-FINDINGS.md)), SDIO clock, power
  sequence timing.

Exit: an AP and a client work after cold and warm boots on the test board.

## 4. Own SDK, ImageBuilder and signed apk repository

The kernel is ours, so kmods from downloads.openwrt.org do not fit it.

- [x] Repository secret `APK_SIGN_KEY` (EC P-256, created by the owner;
  never stored in the repository).
- [ ] Build with `CONFIG_SDK`, `CONFIG_IB`, `CONFIG_ALL_KMODS`: every kmod
  of this kernel is published.
- [ ] apk repository on GitHub Pages; kmods under a path with the kernel
  version and hash (`…/kmods/<kernel>-<hash>/`), so older images keep
  finding their modules after a kernel change.
- [ ] The image trusts only our key for kmods and target packages; check
  whether the official `packages`/`luci` feeds fit (same `aarch64_cortex-a55`
  ABI) or publish those too.
- [ ] Driver-only workflow: our SDK rebuilds `kmod-aic8800-sdio` and the
  firmware in minutes; fixes reach boards by `apk upgrade`.
- [ ] Kernel changes (DTS, config, OpenWrt version) mean a new image and
  sysupgrade; apk cannot replace the kernel.
- [ ] Image checks: our key and repository in the rootfs, no official kmod
  feed.

## 5. Image contents and first-boot setup

As in the Orange Pi Zero 3 project
([IMAGE-PACKAGES](https://github.com/Medvedolog/opiz3-wlan-backport/blob/main/docs/IMAGE-PACKAGES.md)),
without mwan3, luci-app-mwan3, watchcat, nlbwmon; Bluetooth stays off.

- [ ] Network through `board.d` (eth0 LAN 192.168.1.1, eth1 WAN DHCP), no
  `uci-defaults` with a network restart.
- [ ] First boot: Wi-Fi AP "A5E" with a placeholder password and a LuCI
  warning until it is changed.
- [ ] LuCI, AmneziaWG/WireGuard, sing-box, modems (ModemManager, QMI/MBIM/
  NCM), USB Ethernet and USB Wi-Fi drivers, NVMe tools.
- [ ] Footstrap theme in the project's colours.
- [ ] `docs/IMAGE-PACKAGES.md` with the reason for each package.

## 6. Test plan and releases

- [x] Test pre-release `cubie-a5e-test`, rolling `cubie-a5e-snapshot-latest`
  from `main`, fixed releases by tag with notes from `docs/releases/<tag>.md`
  (`release-tag.yml`).
- [x] [`docs/TEST-PLAN.md`](TEST-PLAN.md) created for boot, MMC identity, UCI radio renumbering, AP/STA, recovery and repeated cold boots. Hardware gate pending.
- [ ] `main` branch and the first beta release after stages 2–3.
- [ ] Test reports thread (as in the Orange Pi Zero 3 project).

## 7. AIC8800 driver audit and fixes

Initial investigation started while Wi-Fi is intermittent. After Wi-Fi works,
continue following the Orange Pi Zero 3 UWE5622 audit: KASAN-class
bugs, `dump_station`, honest station statistics. Patches numbered 010+ in
`package/kernel/aic8800/patches`, rebased onto ImmortalWrt's.

Candidates already known:

- radxa-pkg's own `debian/patches` (firmware path per chip,
  `fix-sprintf-fw-path-overlap`, build fixes) are not applied by
  ImmortalWrt; upstream moved 37 commits since the pinned version.
- Stack overflow in `aicbt_patch_info_unpack()` (BT patch table).
- SDIO IO-pad delay writes outside DDR50 (data CRC errors; may be why mmc1
  is limited to 35 MHz).
- SDIO wakeup before the first firmware transfer; cold-start failures.
- Kconfig recursive dependency around `AIC8800_SDIO_BT_SUPPORT`.
- `docs/AIC8800-DRIVER-AUDIT.md` with the findings.

## 8. One image for all memory types

Mainline U-Boot has no DRAM training; the timings come from the defconfig
([COMMUNITY-FINDINGS §1](COMMUNITY-FINDINGS.md)).

- [ ] Collect `sunxi_dram_para` readings from testers; one profile per
  memory type.
- [ ] U-Boot: try several parameter sets in turn (mainline, then the
  newer-board set) with a stricter SPL memory check, so that a set that
  passes the quick check but is unstable is rejected too.
- [ ] Test on the project's board by putting a wrong set first.
- [ ] Then one image for all, profiles only for exceptions; send the
  change to U-Boot upstream.

## 9. USB 3.0 image variant

The M.2 slot and the USB 3.0 port share one PHY
([PORTING-NOTES §4](PORTING-NOTES.md)).

- [ ] Second device tree: combo PHY in USB3 mode, PCIe off, GMA340 switch to
  USB3 (PB6 low), DWC3 `usb@4d00000` with its USB2 PHY.
- [ ] Driver side: the PR's combo PHY in USB3 mode, or the A523 USB3 series
  posted to LKML (used by an OpenWrt 25.12.5 community build).
- [ ] Image `…-usb3-…` next to the NVMe one.

## 10. Upstream

- [ ] Hardware reports on openwrt/openwrt#23296.
- [ ] Offer the DRAM fallback (the PR's 1 GB blocker) and the Wi-Fi power
  sequence to the PR, or to U-Boot and Linux upstream.
- [ ] When the PR is merged: build on the official snapshot, later the
  official ImageBuilder; keep only the Wi-Fi driver and its repository
  here, as the Orange Pi Zero 3 project does.
- [ ] AIC8800 in OpenWrt: only after the audit, and only if the driver
  quality allows it.

## 11. Current blocker: cold boot SDIO and persistent Wi-Fi identity

### Confirmed on the test board (2026-10-13)

- MMC `4020000.mmc` is microSD, `4021000.mmc` is onboard SDIO Wi-Fi.
  The logical `mmc0/mmc1` order can change between reboots.
- On a successful start AIC8800 requests 35 MHz but operates at 33.33 MHz,
  firmware registers a PHY, and its MAC stayed `fc:23:cd:03:8e:78`
  between checked reboots.
- On a failed start the driver retries firmware transfer twice and hits
  `-110` at `4021000.mmc`, even without its old 150 MHz override.
- An existing UCI `radio0.path` with a previous `mmcN` can be orphaned;
  `wifi config` then creates `radio1` for the same device.

### Changes implemented, still needing a hardware release gate

- [x] Disable forced 150 MHz SDIO; leave limit to MMC/DTS.
- [x] Retry `uci-defaults` when Wi-Fi PHY has not appeared; run `wifi config`
  after driver loading.
- [x] Record the onboard detected MAC as `wireless.radio0.macaddr` and
  clean up duplicate sections from previous MMC enumerations.
- [x] Remove `wireless.default_radio0.disabled` from first-boot lab AP.
- [x] Add manual-only [`aic8800-recover`](AIC8800-RECOVERY.ru.md)
  using an isolated `4021000.mmc` unbind/bind, with lock and attempt limits.
- [ ] Confirm these changes on a freshly flashed image across a series
  of cold starts and reboots (not just successful CI).
- [ ] Port OPIZ3-style **persistent** `ieee80211 add` handling to onboard
  AIC8800 (MAC + current path), preserving modified UCI sections.
- [ ] Test recovery manually after actual `-110` with Ethernet/UART.
- [ ] Run isolated SDIO 25 MHz vs 35 MHz, BLDO1 always-on, MMC pwrseq
  timing experiments; instrument the first failing firmware transaction.
- [ ] Only then consider automatic, rate-limited recovery.

References: [detailed investigation](AIC8800-SDIO-WIFI.ru.md),
[hardware test plan](TEST-PLAN.md),
[OPIZ3 recovery](https://github.com/Medvedolog/opiz3-wlan-backport/blob/main/package/kernel/uwe5622/files/uwe5622-recover),
[Armbian A5E power patch](https://github.com/armbian/build/blob/main/patch/kernel/archive/sunxi-6.18/patches.backports/34-fix-wifi-regulator-cubie-a5e.patch).
