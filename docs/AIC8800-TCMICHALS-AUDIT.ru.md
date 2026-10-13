# AIC8800D80 on Cubie A5E: audit of tcmichals SDIO wakeup and OOB claims

Date: 2026-10-13. Status: **source audit, not a tested hardware fix**.

Reference: [tcmichals/cubie-a5e Wi-Fi architecture guide](https://github.com/tcmichals/cubie-a5e/blob/main/docs/common/WIFI_AIC8800_GUIDE.md).
Our packaged vendor source: [radxa-pkg/aic8800 at 89f865b8](https://github.com/radxa-pkg/aic8800/tree/89f865b80f5f2ba6c0711c560e1d0191e87a1bf0).
Local branch: `claude/fix-a5e-rootfs-sdio-uci`, ImmortalWrt package baseline r5, local r6.

## 1. Wakeup register

In the pinned Radxa source, `src/SDIO/driver_fw/driver/aic8800/aic8800_fdrv/aicwf_sdio.c`, the `aicwf_sdio_wakeup()` function writes `sdiodev->sdio_reg.wakeup_reg` but polls
`sdiodev->sdio_reg.sleep_reg`, checking bit 4 (`val & 0x10`).

In tcmichals' alternate `aic8800-upstream/aic8800_fdrv/aicwf_sdio.c`, that function instead polls `wakeup_reg` and tests that bit 0 clears (`(val & 0x1) == 0`).

The tcmichals explanation describes an SDIO wakeup timeout, but it is
not direct evidence that this is responsible for our errors during the
initial `fw_patch_8800d80_u02.bin` SDIO write.

**Critical gating:** In Radxa's pinned
`src/SDIO/driver_fw/driver/aic8800/aic8800_fdrv/Makefile`,
`CONFIG_SDIO_PWRCTRL ?= n`. In the BSP Makefile it is
`CONFIG_SDIO_PWRCTRL := n`.
The offending function is under `#if defined(CONFIG_SDIO_PWRCTRL)`.
Until build flags prove otherwise, this code is **not compiled into our
default SDIO WLAN module**.

**Decision:** Do not introduce a behavioral change into the next image
solely to fix this dormant routine. If preparing a future low-power
variant, patch with an isolated commit and verify the compile flags
and the before/after behavior.

## 2. OOB interrupts

The tcmichals guide says a write of `0x00000006` to
`0x40504084` redirects interrupt handling to an unconnected OOB GPIO,
and that the write must be disabled when `CONFIG_OOB=n`.

Our Radxa top-level SDIO driver Makefile exports `CONFIG_OOB = n`;
the BSP and FDRV Makefiles also default to `n`. The A5E is configured
for the standard SDIO interrupt route, not an externally connected
out-of-band IRQ in this integration.

We inspected the pinned Radxa `aicwf_sdio.c` and its
tcmichals counterpart: OOB-specific functionality is under
`#ifdef CONFIG_OOB`. The concrete register write from the guide
has **not** been located in the same function in those source files.
It may be in chip-specific initialization or another tree; the guide
alone is not enough to conclude this write occurs in our image.

**Decision:** Do not add an unverified blanket register-write
suppression. First locate each exact `0x40504084` write in
`aic8800_bsp` / `aic8800_fdrv`, follow its build and chip ID guards,
and determine whether it is reachable for `AIC8800D80` at cold
firmware initialization. If reachable, create a **separate** OOB-only
fix and A/B test it.

## 3. Relation to the actual A5E failure

Observed on the physical 4 GB Micron Cubie A5E: the SDIO device is
enumerated on `4021000.mmc`; one cold boot loads firmware and produces
PHY, another fails during the firmware transfer with
`sunxi-mmc: data error`, `aicwf_sdio_send_pkt fail-110`,
`bin upload fail: 1e2000, err:-110`.
On the successful boot, 35 MHz was requested, 33.33 MHz actual.

Neither OOB routing nor low-power wakeup has yet been shown to be
executing at the relevant instant, so root cause remains unknown.

## 4. Controlled next steps

1. Inspect the **actual preprocessed build flags**, not only defaults,
   for `CONFIG_OOB` and `CONFIG_SDIO_PWRCTRL`.
2. Trace the exact SDIO firmware transfer failure and the first
   `sdio_writesb` / MMC error, capturing log timestamps and host.
3. Locate writes to `0x40504084` in the BSP/chip-specific source;
   inspect the active chip ID and `CONFIG_OOB` conditions.
4. If the OOB write is truly reachable without OOB support, test a
   minimal guarded patch on an isolated build.
5. If power-control code is enabled, test the wakeup register change
   independently. Do not combine the two patches in one A/B image.
6. On each image, record 20 cold boots, firmware success ratio,
   PHY/AP availability, `dmesg`, and image SHA.

**No changes to the running or successful A5E driver are justified by
this audit alone.** Keep the known-good `40b6f77` build available as
a comparator and the later FORTIFY packaging fix isolated.

Other context:
- [SDIO evidence and investigation](AIC8800-SDIO-WIFI.ru.md).
- [Hardware test plan](TEST-PLAN.md).
