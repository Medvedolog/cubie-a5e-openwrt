# OpenWrt DevBuild — Radxa Cubie A5E

This is **OpenWrt**, built from a pinned upstream development commit carrying
the in-review A527/T527 support (openwrt/openwrt#23296). It is **not** an
official OpenWrt stable release, nor a fork distribution.

## Versioning

- User-visible image label: `OpenWrt DevBuild NNN`, starting at `001`.
- `CONFIG_VERSION_DIST="OpenWrt"` and
  `CONFIG_VERSION_NUMBER="DevBuild NNN"`.
- `CONFIG_VERSION_CODE="A5E"` is only a build label, not a firmware ABI.
- Preserve the real `DISTRIB_REVISION`, OpenWrt source SHA, Linux version,
  kernel ABI, package feed revisions and image SHA256 in build metadata.
- Increment NNN **only** for a newly published image, not for each commit.
- Never overwrite an existing numbered DevBuild image with different bytes.
- Package-only AIC8800 updates keep the image DevBuild number unchanged;
  report package revision independently.

## Storage

- The ext4 SD-card image is configured with
  `CONFIG_TARGET_ROOTFS_PARTSIZE=2048` (MiB). This is **disk** space, not RAM.
- A card must have enough free capacity for the image and its partitions.
- Check squashfs behavior separately: squashfs is read-only; writable
  overlay capacity is not established by the ext4 rootfs setting.
- No automatic, tested rootfs expansion or sysupgrade retention is claimed yet.

## Packages and signatures

- Current workflow supports `APK_SIGN_KEY`; absence causes an ephemeral key.
  The presence and continuity of the real secret must be verified in CI.
- Current workflow uploads package artifacts, but no persistent signed
  public APK feed, SDK, ImageBuilder, or complete kmod feed is guaranteed yet.
- Build kmods only against the **exact** running OpenWrt kernel ABI; never
  mix official 25.12.x Linux 6.12 kmods with this Linux 6.18 image.
- To deliver a complete package-updatable DevBuild, publish a stable
  kernel-ABI-scoped signed feed, its public key and repository configuration,
  SDK and ImageBuilder. Test both `apk add` and upgrade paths on hardware.
- Kernel/DTB/U-Boot changes require image-level update and validation.

## Compatibility build for akorshun

The separate OpenWrt 25.12.5 Cubie A5E image at
`akorshun/openwrt` uses Linux 6.12.94 and a different ABI/target.
Build our AIC8800 patches against **its exact SDK and kernel ABI** and publish
the resulting packages as separate artifacts. Recovery and UCI helper scripts
must be packaged separately rather than assumed to ship inside the kmod.
Do not copy these packages into the Linux 6.18 DevBuild feed.

## Release checklist

1. Pin OpenWrt SHA and feed revisions; check the source build is reproducible.
2. Record kernel ABI and image SHA256; verify signed APK packages and keys.
3. Verify `/etc/openwrt_release`, `/etc/os-release`, image name, rootfs size.
4. Test boot, Ethernet, Wi-Fi/AP/client, recovery and installation of at
   least one out-of-image kmod from the matching feed.
5. Publish a new immutable `devbuild-NNN` tag only after checks pass.
