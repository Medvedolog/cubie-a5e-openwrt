# Porting notes: OpenWrt on the Radxa Cubie A5E

What the build takes from where, and why. Everything here is from reading
sources; **nothing in this file has been verified on hardware yet** unless a
section says so.

## 1. Starting point (2026-10-12)

| Tree | Kernel | A527 / Cubie A5E |
|---|---|---|
| OpenWrt main (`66ee7b6950a8`) | sunxi on 6.18.55 | no `sun55i-a527`, no profile, no AIC8800 driver; A523 clocks off in the kernel config |
| OpenWrt 25.12 | 6.12 | nothing for A527 |
| ImmortalWrt master (`da63f7d6ac42`) | sunxi on 6.18.55 | `Device/sun55i-a527`, `Device/radxa_cubie-a5e`, `package/kernel/aic8800`, A523 U-Boot and TF-A, PCIe/combo PHY drivers |
| Linux 6.18 (mainline) | — | `sun55i-a527-cubie-a5e.dts` with gmac0, USB2, microSD; no Wi-Fi node, no second GMAC, no PCIe, no USB3 |

There is no official kernel with A527 support, so the official
ImageBuilder/SDK cannot be used: the image is built from the OpenWrt
sources. OpenWrt main and ImmortalWrt master share the kernel (6.18.55),
U-Boot (2026.04), TF-A (2.14) and mac80211 backports (7.2), so ImmortalWrt's
A527 parts apply to OpenWrt main without rebasing. This was checked locally:
all generic and sunxi kernel patches plus ours apply to Linux 6.18.55, and
the Cubie A5E device tree compiles.

## 2. What is taken from ImmortalWrt

Files are copied unchanged, with their authorship headers. The OpenWrt tree
changes are in `patches/openwrt/0001-*.patch`.

### Kernel (`target/linux/sunxi/patches-6.18`, `files/`)

| Patches | What | Why we need it |
|---|---|---|
| 011, 012, 013, 030-01…07 | AXP717 type-C, A523 SPI/SPDIF, DTS backports from 6.19: GMAC200, DMA, I2S, SPDIF, SPI nodes | 031-01 (second Ethernet) builds on the GMAC200 node |
| 031-01 | Cubie A5E: second Ethernet port (GMAC200 + MAXIO MAE0621A PHY), mainline v6.19 | eth1 (WAN) |
| 702, 703 | MAXIO PHY driver and its LEDs | the PHY of both ports on this board |
| 120 | pinctrl: pins calculation on re-probe | generic fix |
| 121-01…03 | A523 clocks: cpufreq, regmap gate, USB3 ref clock/reset | CPU frequency scaling, PCIe/USB3 combo PHY clock |
| 122-01…03, 130-02 | AXP717 dual/tri-phase DCDC | CPU supply on the A527 |
| 123-*, 130-01 | thermal sensor (THS0/1) | temperature |
| 124 + `files/drivers/iommu` | sun55i IOMMU | PCIe DMA |
| 125 + `files/drivers/phy/allwinner/sunxi-inno-combophy.c` | INNO PCIe/USB3 combo PHY | M.2 NVMe |
| 126 + `files/drivers/pci/pcie-sunxi` | DesignWare PCIe RC for sun55i | M.2 NVMe |
| 130-03, 130-04 | CPU OPP table; IOMMU, combo PHY, PCIe nodes in the dtsi | |
| 131-01 | Cubie A5E: Wi-Fi on mmc1 (PL7 3.3 V switch, 35 MHz, drive strength 40), CPU supplies, Bluetooth UART1 | Wi-Fi |
| 131-02 | Cubie A5E: combo PHY in PCIe mode, PCIe slot power, GMA340 lane switch to PCIe | M.2 NVMe |
| 314 | LED aliases (status LED), PHY LEDs | OpenWrt LED triggers |

Not taken: 102/103/313 (Orange Pi Zero 2/3 Wi-Fi and LEDs), 910/911 (H5/H616
OPPs) — other boards.

### Kernel config (`patches/openwrt/0001`)

ImmortalWrt's `target/linux/sunxi/{config-6.18,cortexa53/config-6.18}`
differences: A523 CCU/pinctrl, `DWMAC_SUN55I`, `MAXIO_PHY`, IOMMU, PCIe
(`PCIE_SUN55I_RC`, `AW_INNO_COMBOPHY`), `USB_DWC3`/`USB_XHCI_*`, schedutil.
`cortexa53/target.mk` gets `FEATURES += pci pcie` (needed by `kmod-nvme`).

### Image, U-Boot, TF-A

- `Device/sun55i-a527` and `Device/radxa_cubie-a5e` in
  `image/cortexa53.mk`. Device packages: `kmod-aic8800-sdio`,
  `aic8800-sdio-firmware`, `kmod-nvme`, `wpad-mbedtls` (instead of
  ImmortalWrt's `wpad-openssl`; OpenWrt's default is mbedTLS).
- U-Boot 2026.04 `radxa-cubie-a5e_defconfig` (`U-Boot/radxa-cubie-a5e`,
  `uEnv-a523.txt`) with ImmortalWrt's U-Boot patches for the second GMAC
  and the MAXIO PHY.
- TF-A 2.14 `PLAT=sun55i_a523` with ImmortalWrt's A523 patch set (100–107).
- `board.d/02_network`: `radxa,cubie-a5e` → `eth0` LAN, `eth1` WAN.

### Wi-Fi driver (`package/kernel/aic8800`)

ImmortalWrt's package, unchanged: source
`https://github.com/radxa-pkg/aic8800.git` at `89f865b80f5f` (2026-03-10),
`kmod-aic8800-sdio` = `aic8800_bsp.ko` + `aic8800_fdrv.ko`, firmware in
`/lib/firmware/aic8800/sdio`. Bluetooth (`AIC8800_SDIO_BT_SUPPORT`) is
switched off in `config/diffconfig`.

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
    errors outside DDR50. This may be what ImmortalWrt's "clock above
    40 MHz makes data errors" (`max-frequency = <35000000>`) works around.
  - the chip may start in bus sleep; an explicit SDIO wakeup before the
    first firmware transfer avoided timeouts.

  None of this is in the build yet: first see what the board does.

## 3. Our own changes

### `900-arm64-dts-allwinner-a527-cubie-a5e-wifi-pwrseq.patch`

ImmortalWrt's Wi-Fi node has no power sequence. The Radxa BSP device tree
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
(`patch/kernel/archive/sunxi-6.18/patches.backports/22-*`, `34-*`), and
testers report that without the PM1 sequence the module does not enumerate
on mainline kernels.

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
  hang. This image uses mainline TF-A 2.14 with the A523 port; reboot and
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
