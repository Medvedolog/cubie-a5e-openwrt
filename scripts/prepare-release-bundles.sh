#!/bin/bash
# Prepare immutable GitHub Release APK feed and a matching ImageBuilder.
# Run from the OpenWrt build root after make and make package/index.
set -euo pipefail

: "${GITHUB_SHA:?GITHUB_SHA must be the full commit of the firmware source}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be owner/repository}"
: "${TARGET:?TARGET must be the OpenWrt target}"
: "${SUBTARGET:?SUBTARGET must be the OpenWrt subtarget}"
: "${GITHUB_RUN_ID:?GITHUB_RUN_ID must identify this particular build}"
: "${GITHUB_RUN_ATTEMPT:?GITHUB_RUN_ATTEMPT must identify retries}"

# Include run and attempt: re-running one Git commit can use newer feeds
# or a different workflow_dispatch OpenWrt commit/kernel ABI.
feed_tag="cubie-a5e-pkgs-${GITHUB_SHA:0:12}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
upstream_sha=$(git rev-parse HEAD)
feed_url="https://github.com/${GITHUB_REPOSITORY}/releases/download/${feed_tag}"
package_dir="staging_dir/packages/${TARGET}"
out_feed="../feed"
out_ib="../imagebuilder"

test -s "${package_dir}/packages.adb" || {
    echo "::error::Missing signed, merged APK index at ${package_dir}/packages.adb"
    exit 1
}
test -s public-key.pem || {
    echo "::error::Missing OpenWrt APK public-key.pem; cannot publish trusted feed"
    exit 1
}
test -x staging_dir/host/bin/apk
rm -rf "${out_feed}" "${out_ib}"
mkdir -p "${out_feed}" "${out_ib}"

# The merged build-time index already contains the complete package set
# and is signed with the exact key installed into this firmware. Never
# regenerate it with an unrelated key in the publisher.
cp "${package_dir}/packages.adb" "${out_feed}/packages.adb"
cp public-key.pem "${out_feed}/public-key.pem"
count=0
for apk in "${package_dir}"/*.apk; do
    [ -f "${apk}" ] || continue
    cp -L "${apk}" "${out_feed}/"
    count=$((count + 1))
done
[ "${count}" -gt 10 ] || {
    echo "::error::Only ${count} APK packages found; refusing an incomplete feed"
    exit 1
}
ls "${out_feed}"/kmod-aic8800-sdio-*.apk >/dev/null || {
    echo "::error::AIC8800 SDIO module missing from APK feed"
    exit 1
}

# Confirm that the signed index can actually be decoded by the build's apk.
staging_dir/host/bin/apk adbdump --format json "${out_feed}/packages.adb" \
    > "${out_feed}/index.json"
test -s "${out_feed}/index.json"
sha256sum "${out_feed}"/*.apk "${out_feed}/packages.adb" \
    "${out_feed}/public-key.pem" | sed "s@  ${out_feed}/@  @" > "${out_feed}/SHA256SUMS"
printf 'commit=%s\nupstream=%s\nfeed=%s/packages.adb\npackages=%s\n' \
    "${GITHUB_SHA}" "${upstream_sha}" "${feed_url}" "${count}" \
    > "${out_feed}/build-info.txt"
echo "Prepared ${count} APKs, exact build key and signed packages.adb"

# The IB MUST originate from this same private A527 build, never from the
# official sunxi/cortexa53 ImageBuilder (different subtarget and kernel ABI).
src_ib=$(find "bin/targets/${TARGET}/${SUBTARGET}" -maxdepth 1 -type f \
    -name '*imagebuilder*.tar.zst' -print -quit)
[ -n "${src_ib}" ] && [ -s "${src_ib}" ] || {
    echo "::error::No ImageBuilder generated from this PR kernel"
    exit 1
}
scratch=$(mktemp -d)
trap 'rm -rf "${scratch}"' EXIT
tar --zstd -xf "${src_ib}" -C "${scratch}"
ib_root=$(find "${scratch}" -mindepth 1 -maxdepth 1 -type d \
    -name '*imagebuilder*' -print -quit)
[ -n "${ib_root}" ] && [ -d "${ib_root}" ] || {
    echo "::error::Could not locate extracted ImageBuilder"
    exit 1
}
[ -f "${ib_root}/repositories" ] || {
    echo "::error::ImageBuilder has no APK repositories file; check CONFIG_IB_STANDALONE"
    exit 1
}
printf '%s/packages.adb\n' "${feed_url}" > "${ib_root}/repositories"
mkdir -p "${ib_root}/keys"
cp public-key.pem "${ib_root}/keys/public-key.pem"
# Preserve first-boot UCI, AIC8800 diagnostics/recovery and firmware
# provenance in images generated later with ImageBuilder.
cp -a files "${ib_root}/a5e-overlay"
test -s "${ib_root}/a5e-overlay/etc/uci-defaults/99-cubie-a5e-test-config"
printf '%s/packages.adb\n' "${feed_url}" > "${ib_root}/a5e-distfeeds.list"

# The IB's remote repositories file controls package downloads, but does
# NOT by itself replace /etc/apk/repositories.d/distfeeds.list in images
# created by ImageBuilder. Install the same pinned feed and public key in
# EVERY generated image, even if users pass their own FILES= overlay.
python3 - "${ib_root}/Makefile" <<'PY'
import pathlib
import sys
p = pathlib.Path(sys.argv[1])
source = p.read_text()
needle = "\t$(call prepare_rootfs,$(TARGET_DIR),$(USER_FILES),$(DISABLED_SERVICES))"
if source.count(needle) != 1:
    raise SystemExit("ImageBuilder prepare_rootfs recipe changed upstream")
# A527 upstream profile does not select our AIC8800 package itself.
# Include it in the ImageBuilder profile without forcing it on Avaota A1.
profile_needle = "BUILD_PACKAGES:=$(sort $(DEFAULT_PACKAGES) $($(USER_PROFILE)_PACKAGES) kernel)"
if source.count(profile_needle) != 1:
    raise SystemExit("ImageBuilder default package list changed upstream")
profile_extra = (
    "\nifneq ($(filter DEVICE_radxa_cubie-a5e,$(USER_PROFILE)),)"
    "\nBUILD_PACKAGES += kmod-aic8800-sdio aic8800-sdio-firmware wpad-mbedtls"
    "\nendif"
)
source = source.replace(profile_needle, profile_needle + profile_extra)
extra = (
    "\n\t$(INSTALL_DIR) $(TARGET_DIR)/etc/apk/repositories.d"
    "\n\t$(CP) $(TOPDIR)/a5e-distfeeds.list $(TARGET_DIR)/etc/apk/repositories.d/distfeeds.list"
    "\n\t$(INSTALL_DIR) $(TARGET_DIR)/etc/apk/keys"
    "\n\t$(CP) $(TOPDIR)/keys/public-key.pem $(TARGET_DIR)/etc/apk/keys/public-key.pem"
)
# Board overlay first, user FILES may then override normal settings,
# but the signed APK feed URL and key are enforced for kernel ABI safety.
overlay = "\t$(CP) $(TOPDIR)/a5e-overlay/. $(TARGET_DIR)/\n"
p.write_text(source.replace(needle, overlay + needle + extra))
PY
grep -q 'a5e-distfeeds.list' "${ib_root}/Makefile"
cat > "${ib_root}/README-A5E-REPOSITORY.txt" <<EOF
Radxa Cubie A5E OpenWrt ImageBuilder
Firmware commit: ${GITHUB_SHA}
OpenWrt source: ${upstream_sha}
Target: ${TARGET}/${SUBTARGET}
Build-specific APK repository:
${feed_url}/packages.adb

This ImageBuilder uses ONLY APKs from the matching immutable release,
signed by public-key.pem in keys/. Do not mix with official OpenWrt
snapshot kmods: the kernel ABI differs from the upstream build.

The base ImageBuilder uses the universal U-Boot DRAM configuration.
For boards requiring Micron-specific boot timings, use the tested
DRAM-profile sdcard image from the matching firmware release; an
unmodified ImageBuilder image may not boot on such hardware.

Example: make image PROFILE=radxa_cubie-a5e PACKAGES="luci kmod-nvme"
EOF

base=$(basename "${src_ib}" .tar.zst)
tar -C "${scratch}" -I 'zstd -T0 -9' -cf \
    "${out_ib}/${base}-a5e-${GITHUB_SHA:0:12}.tar.zst" \
    "$(basename "${ib_root}")"
sha256sum "${out_ib}"/*.tar.zst | sed "s@  ${out_ib}/@  @" \
    > "${out_ib}/SHA256SUMS"
echo "Prepared immutable ImageBuilder for ${feed_tag}"
ls -lh "${out_ib}"
