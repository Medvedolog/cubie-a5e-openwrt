#!/usr/bin/env bash
# Build from official pinned source; no flash or publication.
set -euo pipefail

upstream=f8145e65458fba52e360bbdb358be42939eb557f
reference=r38527-f8145e6545
repo=$(cd "$(dirname "$0")/.." && pwd)
variant=${1:-pwrseq-950}
case "$variant" in
  pwrseq-950|stock-dtb) ;;
  *) echo "expected pwrseq-950 or stock-dtb" >&2; exit 2 ;;
esac
root=${OPENWRT_BUILD_ROOT:-"$repo/build-official-openwrt"}
artifacts=${OPENWRT_ARTIFACT_ROOT:-"$repo/build-official-a5e"}
jobs=${JOBS:-$(nproc)}
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || { echo "invalid JOBS" >&2; exit 2; }
mkdir -p "$root" "$artifacts"
root=$(cd "$root" && pwd)
artifacts=$(cd "$artifacts" && pwd)
src="$root/src"
logs="$root/logs"
out="$artifacts/$variant"
if [[ -e "$src" || -e "$out" ]]; then
  echo "refusing overwrite; choose empty build/artifact directories" >&2
  exit 2
fi
mkdir -p "$logs"
test -f "$repo/package/kernel/aic8800/patches/090-sdio-respect-mmc-clock.patch"
test -n "$(find "$repo/package/kernel/aic8800/patches" -name '100-*' -print -quit)"

git init -q "$src"
git -C "$src" remote add origin https://github.com/openwrt/openwrt.git
git -C "$src" fetch --no-tags --depth 1 origin "$upstream"
git -C "$src" checkout -q --detach FETCH_HEAD
test "$(git -C "$src" rev-parse HEAD)" = "$upstream"
cd "$src"
test ! -e package/kernel/aic8800
cp -a "$repo/package/kernel/aic8800" package/kernel/
if [[ "$variant" == pwrseq-950 ]]; then
  patch_dir=target/linux/sunxi/patches-6.18
  patch_name=950-arm64-dts-allwinner-a527-cubie-a5e-wifi-pwrseq.patch
  test -f "$patch_dir/701-Add-wifi-mmc1-to-Radxa-Cubie-A5E.patch"
  test ! -e "$patch_dir/$patch_name"
  cp "$repo/$patch_dir/$patch_name" "$patch_dir/"
fi
# Exact official feeds.buildinfo (downloaded and verified on 2026-11-23).
cp "$repo/config/feeds.official-r38527.conf" feeds.conf
{
  ./scripts/feeds update -a
  ./scripts/feeds install -a
  ./scripts/feeds list -fs
} 2>&1 | tee "$logs/feeds.log"
while read -r kind feed location; do
  [[ "$kind" == src-git && "$location" == *^* ]] || exit 2
  test "$(git -C "feeds/$feed" rev-parse HEAD)" = "${location##*^}"
done < feeds.conf

cp "$repo/config/diffconfig.official-aic8800" .config
make defconfig 2>&1 | tee "$logs/defconfig.log"
for setting in \
    CONFIG_TARGET_sunxi_cortexa53_DEVICE_radxa_cubie-a5e=y \
    CONFIG_TARGET_ROOTFS_EXT4FS=y CONFIG_TARGET_ROOTFS_SQUASHFS=y \
    CONFIG_PACKAGE_kmod-aic8800-sdio=y CONFIG_PACKAGE_aic8800-sdio-firmware=y \
    CONFIG_PACKAGE_wpad-mbedtls=y; do
  grep -Fx "$setting" .config
done
if grep -Fxq CONFIG_AIC8800_SDIO_BT_SUPPORT=y .config; then
  echo "refusing untested SDIO Bluetooth configuration" >&2
  exit 2
fi
make -j"$jobs" download V=s 2>&1 | tee "$logs/download.log"
if ! make -j"$jobs" V=s >"$logs/build.log" 2>&1; then
  tail -n 100 "$logs/build.log" >&2
  exit 1
fi
release="$src/bin/targets/sunxi/cortexa53"
if [[ "$variant" == pwrseq-950 ]]; then
  mapfile -t kernel_cfg < <(find "$src/build_dir" -path '*/linux-sunxi_cortexa53/linux-6.18*/.config')
  [[ "${#kernel_cfg[@]}" == 1 ]]
  grep -Fxq CONFIG_PWRSEQ_SIMPLE=y "${kernel_cfg[0]}"
  if grep -Eq '^CONFIG_RESET_GPIO=[ym]$' "${kernel_cfg[0]}"; then
    echo "RESET_GPIO is incompatible with this three-cell PM1 GPIO sequence" >&2
    exit 2
  fi
fi
python3 "$repo/scripts/check-official-aic8800.py" "$release" "$variant" \
  2>&1 | tee "$logs/check-image.log"
mkdir -p "$out"
cp "$release"/*radxa_cubie-a5e-{ext4,squashfs}-sdcard.img.gz \
   "$release"/*.manifest "$out/"
cp "$logs/check-image.log" "$out/"
./scripts/feeds list -fs >"$out/feeds.buildinfo"
cp .config "$out/config.resolved"
{
  printf 'upstream_commit=%s\nreference_snapshot=%s\nprofile=radxa_cubie-a5e\nvariant=%s\n' \
    "$upstream" "$reference" "$variant"
  printf 'project_commit=%s\nhardware_status=NOT_TESTED\n' "$(git -C "$repo" rev-parse HEAD)"
} >"$out/BUILD-METADATA.txt"
(cd "$out" && sha256sum *.img.gz *.manifest check-image.log feeds.buildinfo config.resolved \
  BUILD-METADATA.txt >SHA256SUMS && sha256sum -c SHA256SUMS)
printf 'Artifact: %s\n' "$out"
