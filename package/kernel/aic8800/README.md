# AIC8800 on Cubie A5E: source and packaging provenance

**Source lineage (2026-10-13)**

| Layer | Repository / exact revision |
|---|---|
| Wi-Fi device | AIC8800D80 SDIO on Radxa Cubie A5E (Allwinner A527) |
| Vendor driver and firmware | [radxa-pkg/aic8800](https://github.com/radxa-pkg/aic8800), **2026-03-10**, commit [`89f865b80f5f2ba6c0711c560e1d0191e87a1bf0`](https://github.com/radxa-pkg/aic8800/commit/89f865b80f5f2ba6c0711c560e1d0191e87a1bf0) |
| OpenWrt packaging baseline | [ImmortalWrt `package/kernel/aic8800`](https://github.com/immortalwrt/immortalwrt/tree/master/package/kernel/aic8800), **`PKG_RELEASE=5` (`r5`)** |
| ImmortalWrt r5 change | [`1811015941f1`](https://github.com/immortalwrt/immortalwrt/commit/1811015941f109c24f89cf3a2ee3400479d5c565), **2026-09-04**, cfg80211/mac80211 7.3 build compatibility |
| Local package revision | **`r6`** (this repository; r5 baseline with additional patches) |
| Build target | OpenWrt A527 PR #23296, Linux 6.18.52, `sunxi/cortexa55` |

Why "ImmortalWrt" was not obvious: `PKG_SOURCE_URL` points to the **Radxa
vendor code**, because ImmortalWrt provides the **OpenWrt Makefile and quilt
patches**, not the source Git repository. The previous Makefile mentioned
ImmortalWrt only in the copyright header. The source revision has remained
pinned; the upstream `main` of Radxa is newer and must not be confused
with this binary's source version.

**Patch provenance**

- `010`–`080`: from ImmortalWrt, unchanged relative to its r5 packaging
  (all eight patch Git blob SHAs matched at comparison time).
- `090-sdio-respect-mmc-clock.patch`: local Cubie A5E modification —
  no driver-enforced 150 MHz, respect DTS/MMC clock limit.
- `100-sdio-rx-fortify-radiotap.patch`: imported verbatim from
  [akorshun/aic8800-openwrt `090`](https://github.com/akorshun/aic8800-openwrt/blob/master/package/aic8800/patches/090-sdio-rx-fortify-radiotap.patch);
  renumbered `100` because our local `090` is already in use.

The `100` patch addresses **FORTIFY_SOURCE compiler diagnostics** for
an HE radiotap copy in the SDIO RX path; it is **not** a cure for
firmware upload timeouts `-110`. It uses the kernel `unsafe_memcpy`
macro where available and retains a `memcpy` fallback otherwise.
The runtime safety of the radiotap bounds depends on the driver's
allocation logic, described in the original patch.

**What testers can check**

```sh
cat /etc/aic8800-origin
apk info kmod-aic8800-sdio
uname -r
```

The file `/etc/aic8800-origin` is created **by the image build workflow**
from `Makefile` rather than hard-coded, so the recorded vendor Git SHA and
local package revision track the actual build. The `build-info.txt` in
GitHub Actions artifacts also records those fields and the patch list.

Do **not** install prebuilt `sunxi/cortexa53` ImmortalWrt `.apk`
kernel modules into our `sunxi/cortexa55` firmware: the kernel ABI is
different. The OpenWrt builder must compile them against this image's
exact kernel.

See [hardware evidence and known SDIO errors](../../../docs/AIC8800-SDIO-WIFI.ru.md).
