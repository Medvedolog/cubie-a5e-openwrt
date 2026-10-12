# Porting notes: OpenWrt on the Radxa Cubie A5E

What the build takes from where, and why. Everything here is from reading
sources; **nothing in this file has been verified on hardware yet** unless a
section says so.

## 1. Starting point (2026-10-12)

| Tree | Kernel | A527 / Cubie A5E |
|---|---|---|
| OpenWrt main | sunxi on 6.18 | nothing for A527 yet |
| [openwrt/openwrt#23296](https://github.com/openwrt/openwrt/pull/23296) "sunxi: add support for A527/T527 boards" (Zoltan Herpai, sunxi maintainer; open since 2026-05-11, last rework 2026-09-27) | 6.18.52 | new subtarget `cortexa55`, profiles `radxa_cubie-a5e` and `yuzukihd_avaota-a1`, TF-A and U-Boot for A523, DTS backports, IOMMU, PCIe, combo PHY, Wi-Fi node on mmc1; **no Wi-Fi driver** |
| ImmortalWrt master (`da63f7d6ac42`) | 6.18.55 | the same A527 parts on the `cortexa53` subtarget, plus the `aic8800` package, MAXIO PHY, cpufreq |
| OpenWrt 25.12 | 6.12 | nothing for A527 |
| Linux 6.18 (mainline) | — | `sun55i-a527-cubie-a5e.dts` with gmac0, USB2, microSD; no Wi-Fi node, no second GMAC, no PCIe, no USB3 |

There is no official kernel with A527 support yet, so the official
ImageBuilder/SDK cannot be used: the image is built from source.

**Base: the branch of PR #23296**, pinned to `5035e7d51ae5`. The aim is to
differ as little as possible from what is expected to become official
OpenWrt: same subtarget (`cortexa55`, packages `aarch64_cortex-a55`),
same profile, same kernel patches. When the PR is merged, the build moves
to the official snapshot (and later the ImageBuilder) and keeps only the
Wi-Fi driver in this project's repository — as the Orange Pi Zero 3
project does. The first build of this project (run 1) used the
ImmortalWrt parts on OpenWrt main instead; it is kept as a reference in
the git history.

## 2. What we add to the PR branch

| Where | What | Why |
|---|---|---|
| `patches/openwrt/0001` | `cortexa55/target.mk`: `FEATURES += pci pcie` | the PR builds the PCIe driver but does not declare the feature, so `kmod-nvme` cannot be selected |
| `target/linux/sunxi/patches-6.18/950-*` | Wi-Fi power sequence on PM1, BLDO1 as vqmmc (below) | the PR's mmc1 node (patch 701) has neither |
| `package/boot/uboot-sunxi/patches/420-*` | DRAM fallback parameters (below) | the PR's open blocker: 1 GB boards do not boot |
| `package/kernel/aic8800` | ImmortalWrt's AIC8800 package | the PR has the Wi-Fi node but no driver |
| `config/diffconfig` | image contents | |

Not in the PR, available in ImmortalWrt, not taken for now: the MAXIO
MAE0621A PHY driver (both ports reportedly work with the generic PHY
driver), A523 cpufreq/OPP patches, AXP717 multi-phase DCDC. Candidates
once the board runs.

### Wi-Fi driver (`package/kernel/aic8800`)

ImmortalWrt's package, unchanged: source
`https://github.com/radxa-pkg/aic8800.git` at `89f865b80f5f` (2026-03-10),
`kmod-aic8800-sdio` = `aic8800_bsp.ko` + `aic8800_fdrv.ko`, firmware in
`/lib/firmware/aic8800/sdio`. Bluetooth (`AIC8800_SDIO_BT_SUPPORT`) is
switched off in `config/diffconfig` (the package's Kconfig reports a
recursive dependency around that option; harmless, to be cleaned up).

Notes for the driver audit (step after the first boot):

- radxa-pkg/aic8800 keeps its own fixes as `debian/patches` (firmware path
  per chip, build fixes up to Linux 7.3, `fix-sprintf-fw-path-overlap`).
  ImmortalWrt does not apply them and carries its own 010–080 instead;
  upstream has moved 37 commits since the pinned version.
- Reports from hardware testers of the AIC8800D80 on the A5E (mainline
  kernel, not OpenWrt):
  - `aicbt_patch_info_unpack()` can overflow a stack buffer while parsing
    `fw_patch_table_8800d80_u02.bin` (stack-protector panic in
    `aicbt_patch_trap_data_load`). To be checked whether the Wi-Fi-only
    path still parses that table.
  - the vendor driver writes SDIO IO-pad delay registers (F0 0xF0/0xF1/
    0xF8) for every bus timing; on the sunxi MMC host this gave data CRC
    errors outside DDR50. This may be what the "clock above 40 MHz makes
    data errors" comment (`max-frequency = <35000000>`) works around.
  - the chip may start in bus sleep; an explicit SDIO wakeup before the
    first firmware transfer avoided timeouts.

  None of this is in the build yet: first see what the board does.

## 3. Our own changes

### `950-arm64-dts-allwinner-a527-cubie-a5e-wifi-pwrseq.patch`

The PR's Wi-Fi node has no power sequence. The Radxa BSP device tree
(`radxa/allwinner-device`, branch `device-a527`,
`configs/cubie_a5e/linux-5.15/board.dts`) gives the module's control pins:

```
wlan_power    = "axp2202-bldo1";               /* 1.8 V I/O */
wlan_regon    = <&r_pio PM 1 GPIO_ACTIVE_HIGH>;
wlan_hostwake = <&r_pio PM 0 GPIO_ACTIVE_HIGH>;
bt_rst_n      = <&r_pio PM 2 GPIO_ACTIVE_HIGH>;
```

The patch adds `mmc-pwrseq-simple` on PM1 (WL_REG_ON) and BLDO1 as
`vqmmc-supply` of mmc1. Armbian's Cubie A5E Wi-Fi patch does the same
(`patch/kernel/archive/sunxi-6.18/patches.backports/22-*`, `34-*`), an
OpenWrt 25.12.5 community image with this wiring reports a working AP, and
testers report that without the PM1 sequence the module does not enumerate
on mainline kernels. Checked locally: the PR's DTS patches plus 950 apply
to the Linux 6.18 device tree and compile.

### U-Boot: DRAM fallback parameters (`420-sunxi-dram-a523-alternative-parameters.patch`)

From Armbian (`patch/u-boot/v2026.07-sunxi64/board_radxa-cubie-a5e/`,
author Guation), unchanged. Mainline U-Boot has one fixed set of DRAM PHY
timings for the Cubie A5E; boards with other DRAM chips fail the memory
check in SPL (`DRAM test failure at address …`) or hang. The patch retrains
the DRAM with an alternative set (`TPR6/10/11/12_ALT = 0x3a000000 /
0x882f3333 / 0xe6e6e2e3 / 0x38383031`) when the check fails. It applies to
U-Boot 2026.04, where `mctl_calc_size()` already returns 0 on a failed
check. Details and the values owners have read from their boards:
[COMMUNITY-FINDINGS §1](COMMUNITY-FINDINGS.md#1-boot-dram-parameters-depend-on-the-board-revision).

### U-Boot: one image per DRAM profile (`config/dram/*.conf`)

The fallback above only acts when the memory check fails. Boards that
pass it with the mainline timings and hang later need their own values,
so the build makes one image per profile: after the main build, U-Boot is
rebuilt with `421-dram-profile.patch` (generated from the profile by
`scripts/dram-profile-patch.py`, applied after 420 so the fallback set
stays) and the image is assembled again. Images:
`…radxa_cubie-a5e-dram-mainline-…` (mainline timings) and
`…radxa_cubie-a5e-dram-<profile>-…`. The CI checks that each U-Boot
`.config` carries the profile's TPR values.

Profiles: `micron-4g-m6` — Micron 4 GB on a V1.1 board (this project's
test board), read back from the vendor U-Boot with `sunxi_dram_para`.

### Kernel config: `CONFIG_RESET_GPIO` must stay off

With `RESET_GPIO` enabled, `pwrseq_simple` asks the reset framework for its
`reset-gpios`; the reset-gpio fallback handles 2-cell GPIO specifiers only
(`__reset_add_reset_gpio_device`, `args_count != 2` → `-ENOENT`), sunxi uses
3 cells, and mmc1 never probes. OpenWrt's generic config has it off;
`scripts/check-image.py` fails the build if it ever gets enabled.

### Not taken from other A523/T527 trees, and why

- POW_MOD_SEL polarity fix for A523 pinctrl: Linux 6.18 already has it
  (`BIAS_VOLTAGE_PIO_POW_MODE_CTL_INV` in `pinctrl-sun55i-a523*.c`).
- Watchdog restart priority above PSCI, AXP717 soft power-off: needed on
  boards booting the vendor (BSP) BL31, whose PSCI `SYSTEM_RESET`/`OFF`
  hang. This image uses mainline TF-A 2.14 with the PR's A523 port; reboot and
  power-off are in the test plan, and these patches are the fallback.

## 4. USB: what works and what does not

The A527 has **one** PCIe/USB3 combo PHY (`phy@4f00000`). On the Cubie A5E
it is wired to both the M.2 slot and the USB 3.0 Type-A port through a
GMA340 lane switch (PB6 selects PCIe or USB3, PB7 is the switch's output
enable). **M.2 NVMe and USB 3.0 SuperSpeed cannot be used at the same
time** (hardware limit, stated by Radxa).

| Mode | Who uses it | Device tree |
|---|---|---|
| PCIe (default here) | Radxa BSP default (`#define USE_PCIE 1`), ImmortalWrt, Armbian | `combophy phy_use_sel = <0>`, `pcie` okay, PB6 high |
| USB3 | Radxa overlay `cubie-a5e-enable-usb3.dtso` | `phy_use_sel = <1>`, `pcie` off, PB6 low, DWC3 `usb@4d00000` + USB2 PHY `phy@4e00000` |

This build uses the PCIe mode: M.2 NVMe works (as far as the drivers go),
the USB-A ports run at USB 2.0 through EHCI/OHCI (`usb@4200000/4200400`,
as in the BSP's PCIe mode).

A USB3 variant needs, beyond the device tree: the DWC3 node and the USB2
PHY of the USB3 controller (`phy@4e00000`, no mainline driver; a posted
series extends `phy-sun4i-usb` with it and adds a `phy-sun55i-usb3-pcie`
driver). It would be a second image (`radxa_cubie-a5e-usb3`) with the same
kernel. Planned after the PCIe image boots.

## 5. Other sources studied

- **Armbian** (`armbian/build`, family `sun55iw3`, board
  `radxa-cubie-a5e.csc`): kernels `current`/`edge` (6.18, 7.2) with the same
  A523 backports, TF-A from `jernejsk/arm-trusted-firmware` branch
  `a523-v4`, msdos partition table (the eGON boot image at 8 KiB overwrites
  a GPT — OpenWrt's sunxi image is msdos already). Wi-Fi from radxa-pkg
  aic8800 as DKMS with `aic8800_fdrv_sdio … ps_on=0` (power save off).
- **Radxa** BSP (`radxa/allwinner-bsp`, `radxa/allwinner-device`, Linux
  5.15/6.6): pin assignments above, USB3/PCIe switching, vendor
  `aic8800` driver tree.
- **DietPi**: no Cubie A5E image (only Orange Pi 4A on T527, Armbian kernel).
- Reports of board owners (4PDA, ImmortalWrt issues) and other A523/T527
  projects: [COMMUNITY-FINDINGS.md](COMMUNITY-FINDINGS.md).
