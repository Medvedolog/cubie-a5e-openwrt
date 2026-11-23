# Cubie A5E big-cluster CPUFreq: bench-only board evidence

This is an opt-in, fail-closed **plumbing bench**, not hardware-proven DVFS.
Do not install it over an existing system or publish it as the normal build.
Do not add boot arguments to the normal release. No regulator/PLL writes
are expected with the bench opt-in omitted. With the opt-in requested, the
stock nominal 768 MHz handoff is not an admitted big-cluster OPP and must leave
CPUFreq disabled. Do not invent a 792 MHz voltage or use a different board's table.

## Source evidence

- Radxa's [documented BSP](https://docs.radxa.com/en/cubie/a5e/other-system/tina-os/build-system#radxa-cubie-a5e-source-code) uses
  [A5E board DTS a23224f1c176](https://github.com/radxa/allwinner-device/blob/a23224f1c1764049508bf13ea0dba50d6d9c4424/configs/cubie_a5e/linux-5.15/board.dts#L1472-L1482)
  (CPU0/DSU main DCDC1, CPU4 external DCDC1). On mainline A5E the
  external PMIC is x-powers,axp323, CPU rail reg_dcdc1_323 at
  PMIC address 0x36; the existing DTS bounds are 0.900 to 1.160 V.
- [Radxa BSP 2045a3ca2a01, cluster1 OPP table](https://github.com/radxa/allwinner-bsp/blob/2045a3ca2a01f088c0314dc924bda59d154e363e/configs/linux-5.15/sun55iw3p1.dtsi#L560-L771)
  specifies the same nonzero voltage in all eleven listed VF bins at three points:

  | Big cluster CPUs 4–7 | All eleven VF bins |
  |---|---:|
  | 408 MHz | 900 mV |
  | 1488 MHz | 1000 mV |
  | 1584 MHz | 1050 mV |

  The bins are 0000, 0100, 0102, 0200, 0201, 0300, 0301, 0302, 0400, 0500, 0502.
  The BSP [decodes SID/eFuse and leakage data](https://github.com/radxa/allwinner-bsp/blob/2045a3ca2a01f088c0314dc924bda59d154e363e/drivers/cpufreq/sun50i-cpufreq-nvmem.c#L530-L616);
  this bench does **not** implement that decoder or extend frequencies by
  marketing SKU. 1680/1800 MHz are unavailable for bins 0500/0502; 1992
  MHz is only in 0400 at 1220 mV and exceeds the mainline board DTS
  regulator ceiling. All are intentionally omitted. Table commonality
  does not establish hardware validation for every board revision or SKU.
- U-Boot v2026.04 [requests 792 MHz](https://github.com/u-boot/u-boot/blob/v2026.04/arch/arm/mach-sunxi/Kconfig#L851-L857)
  and [programs both clusters and DSU](https://github.com/u-boot/u-boot/blob/v2026.04/arch/arm/mach-sunxi/clock_sun50i_h6.c#L103-L171).
  The generic programming subtracts one from N; the A523 hardware
  multiplier uses the encoded value, so expected handoff is 768 MHz,
  consistent with the A523 CPU CCU patch description and Armbian's
  matching-board note. Read back hardware rather than trusting a nominal
  Kconfig frequency. Neither 768 nor 792 MHz is an OPP in the BSP big
  table. Leave the little cluster
  and DSU untouched: the DSU shares the little regulator, and its
  [BSP table](https://github.com/radxa/allwinner-bsp/blob/2045a3ca2a01f088c0314dc924bda59d154e363e/configs/linux-5.15/sun55iw3p1.dtsi#L780-L902)
  does not permit undervolting that rail merely because the little
  CPU clock has been lowered.

## Bench safeguards from the A5E Armbian donor

- At pinned [Armbian 61485f704dd6](https://github.com/armbian/build/blob/61485f704dd661d8c9e1393ff2ceeda56b6c6725/patch/kernel/archive/sunxi-6.18/series.conf#L649-L659),
  the [AXP313A/AXP323 ramp patch](https://github.com/armbian/build/blob/61485f704dd661d8c9e1393ff2ceeda56b6c6725/patch/kernel/archive/sunxi-6.18/patches.armbian/axp313a-dcdc-ramp-delay.patch) adds 400 µV/µs
  (25 µs per 10 mV) regulator transition timing. Patch 956 is that
  exact donor; upward clock transitions must wait for the rail.
- [Armbian's A5E thermal backstop](https://github.com/armbian/build/blob/61485f704dd661d8c9e1393ff2ceeda56b6c6725/patch/kernel/archive/sunxi-6.18/patches.armbian/arm64-dts-sun55i-a527-cubie-a5e-cpu-thermal-backstop.patch)
  reports a real fanless shutdown under sustained all-core load.
  Its state 4/7 floors are not valid for this three-OPP big-only policy.
  Bench patch 957 instead binds both stock sensors to just the big
  policy: minimum cooling state 1 at 85°C (at most 1488 MHz) and
  state 2 at 90°C (408 MHz), with 2°C hysteresis. Existing 110°C
  critical trips remain. These new bench thresholds are not field tested.
- Kernel config must enable SUN8I_THERMAL, CPU_FREQ_THERMAL, and
  THERMAL_GOV_STEP_WISE. Keep this off the normal image.

Before any activation path that changes a stock handoff, collect measured
stock clock/parent, rail readback, board revision, and silicon bin, confirm
the exact ordered first transition and thermal monitoring, then repeat on
spare microSD with UART. These static checks do not complete that step.
