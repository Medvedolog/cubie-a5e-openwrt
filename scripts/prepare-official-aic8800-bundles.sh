#!/usr/bin/env bash
# Run in the exact OpenWrt source checkout after producing images and ImageBuilder.
set -euo pipefail
apk="$PWD/staging_dir/host/bin/apk"
packages="$PWD/staging_dir/packages/sunxi"
release="$PWD/bin/targets/sunxi/cortexa53"
public_key="$PWD/public-key.pem"
repo="$1"
artifacts="$2"
feed_url="$3"
logs="$4"
shift 4
installer_flags=("$@")
feed="$artifacts/signed-feed"
builder="$artifacts/imagebuilder"

[[ -s "$packages/packages.adb" && -s "$public_key" && -x "$apk" ]]
mkdir "$feed" "$builder"
cp "$packages/packages.adb" "$public_key" "$feed/"
cp -L "$packages"/*.apk "$feed/"
keys=$(mktemp -d)
scratch=$(mktemp -d)
trap 'rm -rf "$keys" "$scratch"' EXIT
cp "$public_key" "$keys/"
# apk verify returns a failure count; cap each invocation to prevent wrapping at 256.
files=("$feed"/packages.adb "$feed"/*.apk)
: >"$logs/apk-verify.log"
for ((i = 0; i < ${#files[@]}; i += 32)); do
  "$apk" verify --root "$scratch" --keys-dir "$keys" "${files[@]:i:32}" >>"$logs/apk-verify.log" 2>&1 || {
    tail -n 32 "$logs/apk-verify.log" >&2
    exit 1
  }
done
"$apk" adbdump --format json "$feed/packages.adb" >"$feed/index.json"
kernel_abi=$(python3 - "$feed" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
entries = json.loads((root / "index.json").read_text())["packages"]
actual = {path.name for path in root.glob("*.apk")}
indexed = set()
packages = {}
for entry in entries:
    name, version = entry["name"], entry["version"]
    filename = f"{name}-{version}.apk"
    if filename not in actual or filename in indexed:
        raise SystemExit(f"Missing or duplicated indexed file: {filename}")
    if (root / filename).stat().st_size != entry["file-size"]:
        raise SystemExit(f"Indexed file size mismatch: {filename}")
    indexed.add(filename)
    packages.setdefault(name, []).append(entry)
if actual != indexed:
    raise SystemExit(f"Unindexed APKs: {sorted(actual - indexed)}")
required = {"kernel", "libc", "base-files", "apk-mbedtls", "wpad-mbedtls",
            "kmod-aic8800-sdio", "aic8800-sdio-firmware", "luci", "luci-base",
            "luci-theme-footstrap", "luci-theme-bootstrap", "uhttpd",
            "aic8800-recovery", "luci-app-a5e-board"}
if not required <= packages.keys():
    raise SystemExit(f"Missing expected APKs: {sorted(required - packages.keys())}")
kernel, = packages["kernel"]
driver, = packages["kmod-aic8800-sdio"]
if f"kernel={kernel['version']}" not in driver.get("depends", []):
    raise SystemExit("AIC8800 does not depend on the exact indexed kernel ABI")
print(kernel["version"])
PY
)
{
  printf 'project_commit=%s\nupstream_commit=%s\nfeed_base=%s\nfeed=%s\nkernel_apk=%s\n' \
    "$GITHUB_SHA" "$(git rev-parse HEAD)" "${feed_url%/packages.adb}" "$feed_url" "$kernel_abi"
  printf 'target=sunxi/cortexa53\nprofile=radxa_cubie-a5e\npackage_count=%s\n' \
    "$(find "$feed" -maxdepth 1 -name '*.apk' | wc -l)"
} >"$feed/build-info.txt"
(cd "$feed" && LC_ALL=C sha256sum *.apk packages.adb index.json public-key.pem build-info.txt >SHA256SUMS && sha256sum -c SHA256SUMS)

shopt -s nullglob
archives=("$release"/*imagebuilder*.tar.zst)
[[ "${#archives[@]}" == 1 && -s "${archives[0]}" ]]
# Keep the upstream-generated archive byte-for-byte. Its only remote entry
# already comes from our lockfile-like FeedSourcesAppendAPK override.
tar --zstd -xf "${archives[0]}" -C "$scratch"
builders=("$scratch"/*imagebuilder*)
[[ "${#builders[@]}" == 1 && -d "${builders[0]}" ]]
ib="${builders[0]}"
cmp "$public_key" "$ib/keys/public-key.pem"
if find "$ib" -iname '*private-key*' -print -quit | grep -q .; then
  echo "unexpected private key in ImageBuilder archive" >&2
  exit 2
fi
test "$(grep -vE '^([[:space:]]*#|[[:space:]]*$)' "$ib/repositories")" = "$feed_url"
# Exercise the exact built ImageBuilder, locally, without requiring an
# unverified feed to be published first. Only its solver URL changes in
# this scratch copy; base-files inside the images still pins the live URL.
printf 'file://%s/packages.adb\n' "$feed" >"$ib/repositories"
make -C "$ib" image PROFILE=radxa_cubie-a5e ROOTFS_FILESYSTEM=ext4 \
  >"$logs/imagebuilder-smoke.log" 2>&1 || {
  tail -n 80 "$logs/imagebuilder-smoke.log" >&2
  exit 1
}
python3 "$repo/scripts/check-official-aic8800.py" "$ib/bin/targets/sunxi/cortexa53" pwrseq-950 \
  --filesystem ext4 --feed-url "$feed_url" --public-key "$public_key" --require-luci-footstrap --require-aic-recovery --require-board-ui \
  "${installer_flags[@]}" 2>&1 | tee "$logs/check-imagebuilder.log"
cp "${archives[0]}" "$builder/${archives[0]##*/}"
(cd "$builder" && sha256sum *.tar.zst >SHA256SUMS && sha256sum -c SHA256SUMS)
echo "Verified exact signed AIC8800 feed and same-run ImageBuilder (local feed smoke image): $kernel_abi"
