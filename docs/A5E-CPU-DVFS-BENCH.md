# Cubie A5E CPU DVFS bring-up (separate bench only)

This is a candidate for the official-base OpenWrt Linux 6.18.64 image.
It is not the regular LuCI/Footstrap release, is not for deployment, and
does not change SPI, SPL, U-Boot, eMMC or TF-A. This work never publishes
its kernel modules to the regular APK repository.

The stock DTB has the CPU0, CPU4, GPU and DDR thermal zones but no CPU
operating points. Start with the CPU4–7 cluster only. Its power comes from
AXP323 DCDC1 (vdd-cpub). The little CPUs and DSU share another rail and
are deliberately left alone. Do not use Orange Pi 4A values or market
maximum clock figures as operating points. The initial table is the exact
common big-cluster subset of all vendor A5E silicon bins: 408 MHz / 900 mV,
1488 MHz / 1000 mV, and 1584 MHz / 1050 mV. No 1680 MHz, 1800 MHz or turbo
points are proposed here.

Without explicit opt-in via the kernel command line, no DVFS is enabled.
The isolated build selects powersave, not performance, when testing
the exposed policy. Mainline U-Boot asks for 792 MHz but writes the raw
multiplier 32, read as 768 MHz by the A523 CPU PLL hardware and Linux
clock model. This is not an admitted operating point. The bench code must verify the
actual starting clock and regulator before cpufreq registration; do not
force the generic CPUFreq core to jump to 1488 MHz while probing. If any
precondition fails, the policy must stay absent. Opt-in at a verified
stock handoff can prepare the supported 408 MHz point without changing voltage,
only inside the conservative startup rail window and with immediate
clock/rail readback. The test guard is not a substitute for real rail
measurements and thermal/load checks on the hardware.

At runtime the A5E-only OPP clock callback checks the rail and verifies the
live PLL rate before the generic OPP framework can lower voltage. This
matters on 6.18 because the Common Clock Framework can ignore a provider
rate callback error. Keep the stricter checks even when a donor's clock
driver compiles unchanged.

The AXP323 DCDC settling time follows the upstream vendor BSP rate
(400 µV/µs, via the Armbian patch). Both CPU sensors impose big-cluster
cooling floors at 85°C (1488 MHz or lower) and 90°C (408 MHz), sized to
this three-point table. No stock critical trip is removed. The full
[Armbian A5E DVFS port](https://github.com/armbian/build/blob/61485f704dd661d8c9e1393ff2ceeda56b6c6725/patch/kernel/archive/sunxi-6.18/series.conf#L649-L659)
is an evidence source, not a drop-in replacement: its shared little/DSU
domain and thermal floors depend on a different table.

## First hardware pass

1. Use a known-good alternate SD card and 3.3 V UART; save the full boot
   console from SPL. Leave persistent storage and the stock image alone.
   Boot the bench image without opt-in first. Confirm all eight CPUs,
   wired network, disk, thermal sensors, and no CPU frequency policy.
2. Opt in only on the bench under UART, once stock parent/rates and rails
   have been checked. Confirm the exact command line, expected single
   policy with CPU4–7, regulators and clocks (not dummy providers),
   temperatures, and CPU cooling mapped to the appropriate thermal zone.
   If DVFS refuses to activate, collect logs and stop rather than bypassing
   the gate. Keep Wi-Fi and storage checks independent.
3. Use active cooling for the first stress run and stop before the first
   temperature floor while validating basic operation. Validate every
   admitted step and governor with measured regulator and
   clock transitions under single- and both-cluster load, checksummed SD
   and network I/O, and several cold and warm boots. Do not deliberately
   raise temperatures to kernel trip points. Verify that rollback uses a
   known-good microSD only; a bad candidate must never become a release.

Inputs: [exact board power assignments](https://github.com/radxa/allwinner-device/blob/a23224f1c1764049508bf13ea0dba50d6d9c4424/configs/cubie_a5e/linux-5.15/board.dts#L1472-L1478),
[vendor VF tables](https://github.com/radxa/allwinner-bsp/blob/cubie-aiot-v1.4.6/configs/linux-5.15/sun55iw3p1.dtsi#L347),
[upstream clock series](https://lore-kernel.gnuweeb.org/linux-devicetree/20261005005036.7fd5e60e@ryzen.lan/T/).
