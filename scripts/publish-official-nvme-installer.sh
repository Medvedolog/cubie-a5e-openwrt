#!/usr/bin/env bash
# Publish the separate NVMe installer bundle. Never replace a release or a feed path.
set -Eeuo pipefail
repo=Medvedolog/cubie-a5e-openwrt
expected_ref=refs/heads/work/a5e-official-nvme-installer
upstream=f8145e65458fba52e360bbdb358be42939eb557f
die() { printf 'release: %s\n' "$*" >&2; exit 1; }
[[ ${GITHUB_REPOSITORY,,} == "${repo,,}" && $GITHUB_REF == "$expected_ref" ]] || die 'unexpected source repository or ref'
[[ $GITHUB_SHA =~ ^[0-9a-f]{40}$ && $GITHUB_RUN_ID =~ ^[0-9]+$ && $GITHUB_RUN_ATTEMPT =~ ^[0-9]+$ ]] || die 'bad build identity'
[[ $# == 4 ]] || die 'usage: publish-official-nvme-installer.sh IMAGES IMAGEBUILDER SIGNED_FEED INSTALLER'
images=$(realpath "$1")
builder=$(realpath "$2")
feed=$(realpath "$3")
installer=$(realpath "$4")
pkg_tag="cubie-a5e-pkgs-${GITHUB_SHA:0:12}-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
feed_base="https://raw.githubusercontent.com/$repo/apk-feed/$pkg_tag"
tag="cubie-a5e-r38527-nvme-installer-${GITHUB_SHA:0:8}-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/up"
shopt -s nullglob
ext4=("$images/"*radxa_cubie-a5e-ext4-sdcard.img.gz)
squash=("$images/"*radxa_cubie-a5e-squashfs-sdcard.img.gz)
ibs=("$builder/"*imagebuilder*.tar.zst)
manifests=("$images/"*radxa_cubie-a5e.manifest)
[[ ${#ext4[@]} == 1 && ${#squash[@]} == 1 && ${#ibs[@]} == 1 && ${#manifests[@]} == 1 ]] || die 'expected exactly two A5E disk images, one manifest and one ImageBuilder'
for pkg in luci luci-theme-footstrap luci-theme-bootstrap uhttpd aic8800-recovery luci-app-a5e-board a5e-nvme-installer e2fsprogs resize2fs parted; do
    grep -Eq "^${pkg} - " "${manifests[0]}" || die "firmware manifest lacks $pkg"
done
grep -Fxq "project_commit=$GITHUB_SHA" "$images/BUILD-METADATA.txt"
grep -Fxq "upstream_commit=$upstream" "$images/BUILD-METADATA.txt"
grep -Fxq 'variant=pwrseq-950' "$images/BUILD-METADATA.txt"
grep -Fxq 'image_role=nvme-installer-base' "$images/BUILD-METADATA.txt"
grep -Fxq 'rootfs_partsize_mib=2048' "$images/BUILD-METADATA.txt"
grep -Fxq 'luci_default_theme=footstrap' "$images/BUILD-METADATA.txt"
grep -Fxq 'luci_upstream_commit=256f69627d97f63e9173e2ef213a339e70b4b7a3' "$images/BUILD-METADATA.txt"
grep -Fxq 'aic_recovery=manual' "$images/BUILD-METADATA.txt"
grep -Fxq 'luci_board_ui=a5e' "$images/BUILD-METADATA.txt"
grep -Fxq 'hardware_status=NOT_TESTED' "$images/BUILD-METADATA.txt"
grep -Fq 'hardware status: NOT_TESTED' "$images/check-image.log"
grep -Fxq "project_commit=$GITHUB_SHA" "$feed/build-info.txt"
grep -Fxq "upstream_commit=$upstream" "$feed/build-info.txt"
grep -Fxq "feed_base=$feed_base" "$feed/build-info.txt"
for dir in "$images" "$builder" "$feed"; do (cd "$dir" && sha256sum -c SHA256SUMS); done
gzip -t -- "${ext4[0]}" "${squash[0]}"
zstd -t -- "${ibs[0]}"
openssl pkey -pubin -in "$feed/public-key.pem" -noout
grep -Fxq "feed=$feed_base/packages.adb" "$images/BUILD-METADATA.txt"
tar --zstd -tf "${ibs[0]}" > "$tmp/ib-files"
mapfile -t ib_repositories < <(grep -E '(^|/)repositories$' "$tmp/ib-files")
mapfile -t ib_keys < <(grep -E '(^|/)keys/public-key.pem$' "$tmp/ib-files")
[[ ${#ib_repositories[@]} == 1 && ${#ib_keys[@]} == 1 ]] || die 'ImageBuilder repository/key missing or ambiguous'
if grep -qi 'private-key' "$tmp/ib-files"; then die 'private key filename found in ImageBuilder'; fi
tar --zstd -xOf "${ibs[0]}" "${ib_repositories[0]}" > "$tmp/ib-repositories"
test "$(grep -vE '^([[:space:]]*#|[[:space:]]*$)' "$tmp/ib-repositories")" = "$feed_base/packages.adb"
tar --zstd -xOf "${ibs[0]}" "${ib_keys[0]}" > "$tmp/ib-key"
cmp "$tmp/ib-key" "$feed/public-key.pem"

# GitHub Releases rewrites ~ in package names. Keep exact names on apk-feed.
# The build signs/checks the APKs; validate the signed index's file set here.
api_pkg=$(python3 - "$feed" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
if not (root / 'packages.adb').stat().st_size:
    raise SystemExit('empty APK index')
packages = json.loads((root / 'index.json').read_text())['packages']
files, required = set(), {}
for p in packages:
    n = f"{p['name']}-{p['version']}.apk"
    if pathlib.Path(n).name != n or n in files:
        raise SystemExit(f'unsafe or duplicate APK name: {n}')
    f = root / n
    if not f.is_file() or f.is_symlink() or f.stat().st_size != p['file-size']:
        raise SystemExit(f'APK size/path mismatch: {n}')
    if f.stat().st_size >= 100_000_000:
        raise SystemExit(f'APK too large for GitHub feed: {n}')
    files.add(n)
    if p['name'] in {'kmod-aic8800-sdio', 'aic8800-sdio-firmware'}:
        required[p['name']] = n
if files != {p.name for p in root.glob('*.apk')} or len(required) != 2:
    raise SystemExit('APK set differs from the index or lacks AIC8800')
if {'luci', 'luci-theme-footstrap', 'luci-theme-bootstrap', 'uhttpd',
    'aic8800-recovery', 'luci-app-a5e-board', 'a5e-nvme-installer',
    'parted', 'resize2fs', 'e2fsprogs'} - {p['name'] for p in packages}:
    raise SystemExit('APK feed lacks LuCI, its themes, A5E board support or manual recovery')
allowed = files | {'index.json', 'packages.adb', 'public-key.pem', 'SHA256SUMS', 'build-info.txt'}
if {p.name for p in root.iterdir()} != allowed:
    raise SystemExit('unrecognized files in feed; refusing to publish')
print(required['kmod-aic8800-sdio'])
PY
)
# Check exact filenames and compare every packed file against its generated inventory.
installer_files=(a5e-hybrid-microsd-installer.img.gz payload/a5e-nvme-openwrt.img.gz payload/armbian-u-boot-sunxi-with-spl.bin)
(cd "$installer" && sha256sum --strict -c SHA256SUMS)
for file in "${installer_files[@]}"; do
    [[ -f "$installer/$file" && ! -L "$installer/$file" ]] || die "missing or unsafe installer file: $file"
    awk -v file="$file" '$2 == file && length($1) == 64 && $1 !~ /[^0-9a-f]/ { n++ } END { exit(n != 1) }' "$installer/SHA256SUMS" || die "missing or duplicated installer digest: $file"
    cp "$installer/$file" "$tmp/up/${file##*/}"
done
gzip -t "$tmp/up/a5e-hybrid-microsd-installer.img.gz" "$tmp/up/a5e-nvme-openwrt.img.gz"
echo '99ad69e2ededdf66fb15accfa003c1ec5986807e50d11d544c17c074682c6e98  armbian-u-boot-sunxi-with-spl.bin' | (cd "$tmp/up" && sha256sum -c)

cp "${ibs[0]}" "$tmp/up/"
cp "$images/BUILD-METADATA.txt" "$tmp/up/"
cp "$feed/build-info.txt" "$tmp/up/APK-FEED-BUILD-INFO.txt"
cp "$feed/public-key.pem" "$tmp/up/cubie-a5e-apk-public-key.pem"
(cd "$tmp/up" && sha256sum -- * > SHA256SUMS && sha256sum -c SHA256SUMS)

# A dedicated, immutable subdirectory, not a rolling repository update.
git clone -q --depth 1 --filter=blob:none --no-checkout --single-branch --branch apk-feed \
    "https://github.com/$repo.git" "$tmp/feed"
git -C "$tmp/feed" sparse-checkout set --no-cone "/$pkg_tag/"
git -C "$tmp/feed" checkout -q
if [[ -e "$tmp/feed/$pkg_tag" ]]; then
    diff -qr "$feed" "$tmp/feed/$pkg_tag" || die 'immutable feed path differs'
else
    cp -a "$feed" "$tmp/feed/$pkg_tag"
    git -C "$tmp/feed" add -f -- "$pkg_tag"
    git -C "$tmp/feed" -c user.name='github-actions[bot]' \
        -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
        commit -qm "Publish immutable Cubie A5E test APK feed $pkg_tag"
    git -C "$tmp/feed" -c credential.helper= -c 'credential.helper=!gh auth git-credential' \
        push origin HEAD:refs/heads/apk-feed
fi
for f in packages.adb public-key.pem "$api_pkg"; do
    curl --retry 10 --retry-delay 3 --retry-all-errors -fsSL "$feed_base/$f" -o "$tmp/feed-check"
    cmp -- "$feed/$f" "$tmp/feed-check"
done

cat > "$tmp/notes.md" <<NOTES
## Русский

Тестовый установщик **Radxa Cubie A5E**, собранный на исходниках официального **OpenWrt snapshot r38527** (Linux 6.18.64, sunxi/cortexa53). Это сборка проекта, не релиз OpenWrt. U-Boot/SPL взят из отдельной A5E-сборки на базе Armbian. Ядро, DTB, LuCI/Footstrap, AIC8800 и остальная система собраны на базе OpenWrt; DVFS-эксперимента здесь нет. **На плате не проверено.** Этот тест предназначен только для версии Cubie A5E с 4 ГиБ ОЗУ.

| Файл | Для чего |
| --- | --- |
| \`a5e-hybrid-microsd-installer.img.gz\` | Стартовый образ для запасной microSD. Внутри уже лежат образ NVMe и U-Boot; интернет для установки не нужен. |
| \`a5e-nvme-openwrt.img.gz\` | Отдельный образ всего NVMe-диска. Не sysupgrade и не SD-образ. |
| \`armbian-u-boot-sunxi-with-spl.bin\` | Тот же U-Boot/SPL для проверки и восстановления; не прошивайте этот файл вручную как первый шаг. |

1. Сверьте SHA-256. Подготовьте запасную microSD, пустой NVMe от 4 ГиБ до менее 2 ТиБ с логическими секторами 512 байт, кабель Ethernet и возможность восстановления через UART/FEL.
2. Загрузитесь с microSD и проверьте LuCI на \`http://192.168.1.1/\` по LAN. Задайте пароль root, войдите в интерактивный сеанс SSH и запустите **только диагностику**: \`a5e-install-nvme --check\`.
3. После проверки выполните \`a5e-install-nvme --install /dev/nvme0n1\`, только если это точно нужный пустой SSD. **Все данные на выбранном SSD будут удалены.** Скрипт сверит запись и расширит ext4. По умолчанию SPI не меняется.
4. Для автономной загрузки без microSD нужен совместимый SPI-загрузчик. Если умеете восстановить SPI через FEL, можно вместо шага 3 выбрать \`a5e-install-nvme --install /dev/nvme0n1 --flash-spi\`: скрипт сначала проверит NVMe, сохранит резервную копию SPI на microSD и запросит отдельное подтверждение. Сохраните резервную копию вне платы. Загрузка из SPI на NVMe пока не подтверждена на железе.

## English

Experimental installer for **Radxa Cubie A5E**, built from the official **OpenWrt r38527 snapshot** sources (Linux 6.18.64, sunxi/cortexa53). This is a project build, not an official OpenWrt release. Its U-Boot/SPL comes from the separate Armbian-based A5E loader build. The kernel, DTB, LuCI/Footstrap, AIC8800 and userspace are OpenWrt-based; this is not the DVFS bench. **Not tested on hardware.** This test targets the 4 GiB RAM version of the Cubie A5E only.

| File | Purpose |
| --- | --- |
| \`a5e-hybrid-microsd-installer.img.gz\` | Boot from a spare microSD. The NVMe image and U-Boot are embedded for offline installation. |
| \`a5e-nvme-openwrt.img.gz\` | Standalone full-disk NVMe image. Not for sysupgrade or microSD. |
| \`armbian-u-boot-sunxi-with-spl.bin\` | Matching U-Boot/SPL for verification and recovery. Do not flash it manually as a first step. |

1. Check SHA-256. Have a spare microSD, an empty NVMe SSD (4 GiB to under 2 TiB, with 512-byte logical sectors), wired Ethernet and a UART/FEL recovery path.
2. Boot microSD, open LuCI at \`http://192.168.1.1/\` over LAN, set a root password, then run the **read-only** check in an interactive SSH session: \`a5e-install-nvme --check\`.
3. Once you have identified the correct blank SSD, run \`a5e-install-nvme --install /dev/nvme0n1\`. **This erases the selected SSD.** The script verifies the write and grows ext4. SPI is untouched by default.
4. Standalone NVMe boot needs a compatible SPI loader. If you can recover through FEL, use \`a5e-install-nvme --install /dev/nvme0n1 --flash-spi\` instead of step 3. The installer verifies NVMe, makes a SPI backup on microSD and asks for separate confirmation. Save the backup off-device. SPI-to-NVMe boot is not yet verified on hardware.

## Сборка и пакеты / Build and packages

- OpenWrt source: \`$upstream\`; project commit: \`$GITHUB_SHA\`.
- [CI build and checks](https://github.com/$repo/actions/runs/$GITHUB_RUN_ID).
- [Armbian-based U-Boot donor](https://github.com/$repo/actions/runs/42092944575), pinned by SHA-256. Armbian build: \`6a09306be3edf243108441e108bc0705080f7393\`; U-Boot v2026.10: \`5508406582f6f7120dce0c4b3059819a41788db2\`.
- [Подписанный APK-фид только для этой сборки / Signed APK feed for this exact build]($feed_base/packages.adb). Не смешивайте kmods с другими сборками / Do not mix kmods across builds.
- ImageBuilder содержит ядро и DTB этой сборки, но сам по себе не вставляет гибридный U-Boot или офлайн-пакет установщика / ImageBuilder contains this build's kernel and DTB but does not inject the hybrid loader or offline installer payload by itself.
NOTES

# Upload as a draft. Only make it public once all expected assets exist.
# A unique tag per run/attempt avoids touching any legacy or stable release.
if gh release view "$tag" -R "$repo" >/dev/null 2>&1; then die 'release exists; refusing overwrite'; fi
gh release create "$tag" -R "$repo" --draft --prerelease --latest=false \
    --target "$GITHUB_SHA" --title 'Cubie A5E OpenWrt r38527: offline NVMe installer / установщик NVMe (TEST)' \
    --notes-file "$tmp/notes.md" "$tmp/up/"*
gh release view "$tag" -R "$repo" --json assets --jq '.assets[].name' | LC_ALL=C sort > "$tmp/remote-assets"
(cd "$tmp/up" && printf '%s\n' * | LC_ALL=C sort) > "$tmp/expected-assets"
cmp "$tmp/remote-assets" "$tmp/expected-assets"
gh release edit "$tag" -R "$repo" --draft=false --prerelease --latest=false
gh release view "$tag" -R "$repo" --json url,isDraft,isPrerelease,tagName,targetCommitish | \
  jq -e --arg tag "$tag" --arg sha "$GITHUB_SHA" '. | select(.isPrerelease and (.isDraft | not) and .tagName == $tag and .targetCommitish == $sha) | .url'
