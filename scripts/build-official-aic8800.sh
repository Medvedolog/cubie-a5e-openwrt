#!/usr/bin/env bash
# Build from official pinned source; no flash or publication.
set -Eeuo pipefail
trap 'rc=$?; printf "Build command failed (line %d, exit %d)\n" "$LINENO" "$rc" >&2; exit "$rc"' ERR

upstream=f8145e65458fba52e360bbdb358be42939eb557f
reference=r38527-f8145e6545
repo=$(cd "$(dirname "$0")/.." && pwd)
variant=${1:-pwrseq-950}
case "$variant" in
  pwrseq-950|stock-dtb) ;;
  *) echo "expected pwrseq-950 or stock-dtb" >&2; exit 2 ;;
esac
: "${APK_SIGN_KEY:?Existing APK_SIGN_KEY is required for this signed build}"
[[ "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ]]
[[ "${GITHUB_REPOSITORY:-}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]
[[ "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ && "${GITHUB_RUN_ATTEMPT:-}" =~ ^[1-9][0-9]*$ ]]
[[ "$(git -C "$repo" rev-parse HEAD)" == "$GITHUB_SHA" ]] || {
  echo "APK feed identity must match the checked-out project commit" >&2
  exit 2
}
[[ "$variant" == pwrseq-950 ]] || {
  echo "the signed GitHub build is only for the pwrseq-950 variant" >&2
  exit 2
}
feed_tag="cubie-a5e-pkgs-${GITHUB_SHA:0:12}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
feed_url="https://raw.githubusercontent.com/${GITHUB_REPOSITORY}/apk-feed/${feed_tag}/packages.adb"

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
if [[ -e "$src" || -e "$out" || -e "$artifacts/signed-feed" || -e "$artifacts/imagebuilder" ]]; then
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
(umask 077; printf '%s\n' "$APK_SIGN_KEY" >private-key.pem)
unset APK_SIGN_KEY
trap 'rm -f "$src/private-key.pem"' EXIT
# Build host never writes the private project key to logs or artifacts.
openssl ec -in private-key.pem -check -noout >/dev/null 2>&1
openssl ec -in private-key.pem -pubout >public-key.pem 2>/dev/null
openssl ec -pubin -in public-key.pem -text -noout | grep -Eq 'ASN1 OID: prime256v1$'
# Override the generator used by both base-files and the non-standalone
# ImageBuilder so neither can silently pull kmods from a rolling Snapshot.
python3 - "$feed_url" <<'OPENWRT_PATCH'
from pathlib import Path
import re
import sys

feeds = Path("include/feeds.mk")
source = feeds.read_text()
def new_repo(_):
    return ("define FeedSourcesAppendAPK\n"
            "( echo '" + sys.argv[1] + "' ) >> $(1)\nendef")
source, n = re.subn(r"^define FeedSourcesAppendAPK\n.*?^endef$", new_repo,
                    source, flags=re.M | re.S)
if n != 1:
    raise SystemExit("Upstream APK feed generator changed")
feeds.write_text(source)
profile = Path("target/linux/sunxi/image/cortexa53.mk")
source = profile.read_text()
def add_profile_packages(match):
    return (match[1]
            + "  DEVICE_PACKAGES += kmod-aic8800-sdio aic8800-sdio-firmware "
            + "wpad-mbedtls -wpad-basic-mbedtls aic8800-recovery "
            + "luci luci-theme-footstrap luci-theme-bootstrap luci-app-a5e-board\n"
            + match[2])
source, n = re.subn(r"(^define Device/radxa_cubie-a5e\n.*?)(^endef$)", add_profile_packages,
                    source, flags=re.M | re.S)
if n != 1:
    raise SystemExit("Upstream Cubie A5E profile changed")
profile.write_text(source)
OPENWRT_PATCH
test ! -e package/kernel/aic8800
cp -a "$repo/package/kernel/aic8800" package/kernel/
# Package the existing manual tool so same-build ImageBuilder includes it
# too. Do not carry over old test overlays or anything that runs on boot.
recovery=package/utils/aic8800-recovery
test ! -e "$recovery"
cp -a "$repo/$recovery" "$recovery"
mkdir "$recovery/files"
cp "$repo/files/lib/aic8800.sh" "$recovery/files/"
python3 - "$repo/files/usr/sbin/aic8800-recover" "$recovery/files/aic8800-recover" <<'RECOVERY_PATCH'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text()
# This build deliberately has no legacy first-boot test defaults. Remove
# the dormant branch too, so recovery never executes a stale copy.
begin = "# Only if first-boot defaults are still pending:"
end = '/sbin/wifi config || fail "wifi config failed"'
if source.count(begin) != 1 or source.count(end) != 1:
    raise SystemExit("Unexpected AIC8800 recovery source; re-review the legacy defaults block")
start, stop = source.index(begin), source.index(end)
if stop <= start or "99-cubie-a5e-test-config" not in source[start:stop]:
    raise SystemExit("Unexpected AIC8800 recovery defaults block")
Path(sys.argv[2]).write_text(source[:start] + source[stop:])
RECOVERY_PATCH
sh -n "$recovery/files/aic8800-recover"
sh -n "$recovery/files/aic8800.sh"
board_ui=package/luci/luci-app-a5e-board
test ! -e "$board_ui"
mkdir -p "$(dirname "$board_ui")"
cp -a "$repo/$board_ui" "$board_ui"
# Preserve executable rpcd discovery even if the repository write path
# materialized source files without executable bits.
board_rpc="$board_ui/root/usr/libexec/rpcd/luci.a5e-board"
chmod 0755 "$board_rpc"
sh -n "$board_rpc"
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

# The pinned official LuCI feed ships both themes. Its package scripts
# register them, but deliberately leave the existing mediaurlbase alone.
# Set the fresh-install conffile in luci-base so the firmware AND same-build
# ImageBuilder use Footstrap without overwriting an admin's UCI selection.
luci_revision=$(git -C feeds/luci rev-parse HEAD)
luci_theme=feeds/luci/themes/luci-theme-footstrap/Makefile
test -f "$luci_theme" || { echo "Footstrap not present in pinned LuCI $luci_revision" >&2; exit 2; }
python3 - <<'LUCI_PATCH' | tee "$logs/luci-default-theme.log"
from pathlib import Path

config = Path("feeds/luci/modules/luci-base/root/etc/config/luci")
original = config.read_text()
old = "\toption mediaurlbase '/luci-static/bootstrap'\n"
if original.count(old) != 1:
    raise SystemExit("unexpected LuCI stock default theme config at pinned feed")
config.write_text(original.replace(old, "\toption mediaurlbase '/luci-static/footstrap'\n", 1))
print("LuCI fresh-install theme: Footstrap (Bootstrap retained)")
LUCI_PATCH
printf 'luci_upstream_commit=%s\n' "$luci_revision" | tee -a "$logs/luci-default-theme.log"
git -C feeds/luci diff -- modules/luci-base/root/etc/config/luci | tee -a "$logs/luci-default-theme.log"

cp "$repo/config/diffconfig.official-aic8800" .config
make defconfig 2>&1 | tee "$logs/defconfig.log"
for setting in \
    CONFIG_TARGET_sunxi_cortexa53_DEVICE_radxa_cubie-a5e=y \
    CONFIG_TARGET_ROOTFS_EXT4FS=y CONFIG_TARGET_ROOTFS_SQUASHFS=y \
    CONFIG_IB=y CONFIG_USE_APK=y CONFIG_SIGNED_PACKAGES=y CONFIG_SIGNATURE_CHECK=y CONFIG_SIGN_EACH_PACKAGE=y \
    CONFIG_PACKAGE_luci=y CONFIG_PACKAGE_luci-base=y CONFIG_PACKAGE_uhttpd=y \
    CONFIG_PACKAGE_luci-theme-footstrap=y CONFIG_PACKAGE_luci-theme-bootstrap=y CONFIG_PACKAGE_luci-app-a5e-board=y \
    CONFIG_PACKAGE_kmod-usb-net-qmi-wwan=m \
    CONFIG_PACKAGE_kmod-usb-net-cdc-mbim=m CONFIG_PACKAGE_kmod-usb-serial-option=m CONFIG_PACKAGE_kmod-usb-acm=m \
    CONFIG_PACKAGE_kmod-aic8800-sdio=y CONFIG_PACKAGE_aic8800-sdio-firmware=y CONFIG_PACKAGE_aic8800-recovery=y \
    CONFIG_PACKAGE_wpad-mbedtls=y; do
  grep -Fx "$setting" .config
done
grep -Fx '# CONFIG_IB_STANDALONE is not set' .config
if grep -Fxq CONFIG_AIC8800_SDIO_BT_SUPPORT=y .config; then
  echo "refusing untested SDIO Bluetooth configuration" >&2
  exit 2
fi
# OpenWrt's source mirror has no vendor archive. Git/Zstd repacking is
# not byte-identical to the package pin. Seed only the original archive.
aic_tar='aic8800-2026.03.10~89f865b8.tar.zst'
aic_sha='fb54d2ac13109cf49c1b981424f26e3cc595826f033392284f6b3835a162e069'
grep -Fxq "PKG_MIRROR_HASH:=$aic_sha" package/kernel/aic8800/Makefile
mkdir -p dl
if ! printf '%s  %s\n' "$aic_sha" "dl/$aic_tar" | sha256sum --check --status -; then
  (
    aic_tmp=$(mktemp "dl/.aic8800.XXXXXX")
    trap 'rm -f -- "$aic_tmp"' EXIT
    curl --fail --location --silent --show-error --retry 3 --retry-all-errors \
      --connect-timeout 15 --max-time 120 -o "$aic_tmp" "https://sources.immortalwrt.org/$aic_tar"
    printf '%s  %s\n' "$aic_sha" "$aic_tmp" | sha256sum --check -
    mv -f -- "$aic_tmp" "dl/$aic_tar"
  )
fi
printf '%s  %s\n' "$aic_sha" "dl/$aic_tar" | sha256sum --check -
make -j"$jobs" download V=s 2>&1 | tee "$logs/download.log"
if ! make -j"$jobs" V=s >"$logs/build.log" 2>&1; then
  tail -n 100 "$logs/build.log" >&2
  exit 1
fi
# Use the same build's host JSON helper against a throwaway simulated sysfs.
python3 "$repo/$board_ui/tests/test-rpc.py" \
  "$src/staging_dir/host/share/libubox/jshn.sh" "$src/staging_dir/host/bin" \
  2>&1 | tee "$logs/test-luci-board-rpc.log"
release="$src/bin/targets/sunxi/cortexa53"
if [[ "$variant" == pwrseq-950 ]]; then
  # ImageBuilder includes a copy of the kernel .config within its staging
  # tree. Do not recursively count that copy as a second kernel build.
  shopt -s nullglob
  kernel_cfg=("$src"/build_dir/target-*/linux-sunxi_cortexa53/linux-6.18*/.config)
  shopt -u nullglob
  if [[ "${#kernel_cfg[@]}" != 1 ]]; then
    printf 'Expected one primary kernel config, found %d\n' "${#kernel_cfg[@]}" >&2
    printf 'Candidate: %s\n' "${kernel_cfg[@]}" >&2
    exit 2
  fi
  printf 'Checking primary kernel config %s\n' "${kernel_cfg[0]}"
  grep -E '^((# )?CONFIG_(PWRSEQ_SIMPLE|RESET_GPIO))([= ]|$)' "${kernel_cfg[0]}" || true
  grep -Fxq CONFIG_PWRSEQ_SIMPLE=y "${kernel_cfg[0]}" || {
    echo 'Primary kernel does not have built-in MMC simple power sequencing' >&2
    exit 2
  }
  if grep -Eq '^CONFIG_RESET_GPIO=[ym]$' "${kernel_cfg[0]}"; then
    echo "RESET_GPIO is incompatible with this three-cell PM1 GPIO sequence" >&2
    exit 2
  fi
fi
python3 "$repo/scripts/check-official-aic8800.py" "$release" "$variant" \
  --feed-url "$feed_url" --public-key "$src/public-key.pem" --require-luci-footstrap --require-aic-recovery --require-board-ui 2>&1 | tee "$logs/check-image.log"
bash "$repo/scripts/prepare-official-aic8800-bundles.sh" "$repo" "$artifacts" "$feed_url" "$logs"
mkdir -p "$out"
cp "$release"/*radxa_cubie-a5e-{ext4,squashfs}-sdcard.img.gz \
   "$release"/*.manifest "$out/"
cp "$logs/check-image.log" "$out/"
./scripts/feeds list -fs >"$out/feeds.buildinfo"
cp .config "$out/config.resolved"
{
  printf 'upstream_commit=%s\nreference_snapshot=%s\nprofile=radxa_cubie-a5e\nvariant=%s\n' \
    "$upstream" "$reference" "$variant"
  printf 'feed=%s\nluci_default_theme=footstrap\nluci_upstream_commit=%s\naic_recovery=manual\nluci_board_ui=a5e\n' "$feed_url" "$luci_revision"
  printf 'project_commit=%s\nhardware_status=NOT_TESTED\n' "$(git -C "$repo" rev-parse HEAD)"
} >"$out/BUILD-METADATA.txt"
(cd "$out" && sha256sum *.img.gz *.manifest check-image.log feeds.buildinfo config.resolved \
  BUILD-METADATA.txt >SHA256SUMS && sha256sum -c SHA256SUMS)
printf 'Artifact: %s\n' "$out"
