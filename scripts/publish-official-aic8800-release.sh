#!/usr/bin/env bash
# Publish one completed matching build. Never replace a release or a feed path.
set -Eeuo pipefail
repo=Medvedolog/cubie-a5e-openwrt
expected_ref=refs/heads/work/a5e-official-snapshot-aic8800
upstream=f8145e65458fba52e360bbdb358be42939eb557f
die() { printf 'release: %s\n' "$*" >&2; exit 1; }
[[ ${GITHUB_REPOSITORY,,} == "${repo,,}" && $GITHUB_REF == "$expected_ref" ]] || die 'unexpected source repository or ref'
[[ $GITHUB_SHA =~ ^[0-9a-f]{40}$ && $GITHUB_RUN_ID =~ ^[0-9]+$ && $GITHUB_RUN_ATTEMPT =~ ^[0-9]+$ ]] || die 'bad build identity'
[[ $# == 3 ]] || die 'usage: publish-official-aic8800-release.sh IMAGES IMAGEBUILDER SIGNED_FEED'
images=$(realpath "$1")
builder=$(realpath "$2")
feed=$(realpath "$3")
pkg_tag="cubie-a5e-pkgs-${GITHUB_SHA:0:12}-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
feed_base="https://raw.githubusercontent.com/$repo/apk-feed/$pkg_tag"
tag="cubie-a5e-r38527-aic8800-sd-${GITHUB_SHA:0:8}-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/up"
shopt -s nullglob
ext4=("$images/"*radxa_cubie-a5e-ext4-sdcard.img.gz)
squash=("$images/"*radxa_cubie-a5e-squashfs-sdcard.img.gz)
ibs=("$builder/"*imagebuilder*.tar.zst)
manifests=("$images/"*radxa_cubie-a5e.manifest)
[[ ${#ext4[@]} == 1 && ${#squash[@]} == 1 && ${#ibs[@]} == 1 && ${#manifests[@]} == 1 ]] || die 'expected exactly two A5E disk images, one manifest and one ImageBuilder'
for pkg in luci luci-theme-footstrap luci-theme-bootstrap uhttpd aic8800-recovery luci-app-a5e-board; do
    grep -Eq "^${pkg} - " "${manifests[0]}" || die "firmware manifest lacks $pkg"
done
grep -Fxq "project_commit=$GITHUB_SHA" "$images/BUILD-METADATA.txt"
grep -Fxq "upstream_commit=$upstream" "$images/BUILD-METADATA.txt"
grep -Fxq 'variant=pwrseq-950' "$images/BUILD-METADATA.txt"
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
    'aic8800-recovery', 'luci-app-a5e-board'} - {p['name'] for p in packages}:
    raise SystemExit('APK feed lacks LuCI, its themes, A5E board support or manual recovery')
allowed = files | {'index.json', 'packages.adb', 'public-key.pem', 'SHA256SUMS', 'build-info.txt'}
if {p.name for p in root.iterdir()} != allowed:
    raise SystemExit('unrecognized files in feed; refusing to publish')
print(required['kmod-aic8800-sdio'])
PY
)
cp "${ext4[0]}" "$tmp/up/cubie-a5e-r38527-aic8800-ext4-sdcard.img.gz"
cp "${squash[0]}" "$tmp/up/cubie-a5e-r38527-aic8800-squashfs-sdcard.img.gz"
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
Экспериментальная сборка Cubie A5E на базе OpenWrt r38527, с драйвером AIC8800 и патчем питания SDIO PM1/BLDO1. Это не официальный образ OpenWrt. Сборка проверена в CI, **на железе не проверена**.

Первый запуск: ext4-образ только на запасной microSD. Не использовать для sysupgrade или записи в SPI, eMMC или NVMe. Загрузчик OpenWrt не меняли. Bluetooth не включён.

LuCI уже в образе. После загрузки подключитесь к LAN и откройте http://192.168.1.1/. Тема по умолчанию — Footstrap из официального фида LuCI, Bootstrap тоже установлен. Для первого входа интернет не нужен.

В обзоре LuCI выводятся доступные датчики температуры. Раздел управления CPU показывает частоты и governor, которые сообщает ядро; если оно не предоставляет cpufreq для этой платы, настройки недоступны. Ядро и таблицы напряжений ради этого не менялись.

Ручной Wi-Fi recovery включён без автозапуска. Диагностика: \`aic8800-recover --check\`. Восстановление: \`aic8800-recover --run\` только по кабелю или UART; оно прерывает Wi-Fi. На плате пока не проверено.

В архиве ImageBuilder уже собранные ядро и DTB этой версии. Используйте только [подписанный APK-репозиторий этой сборки]($feed_base/packages.adb), не kmods из официального rolling snapshot. Публичный ключ и SHA-256 файлов приложены.

- OpenWrt: $upstream
- Исходники сборки: $GITHUB_SHA
- [Проверки CI](https://github.com/$repo/actions/runs/$GITHUB_RUN_ID)
NOTES

# Upload as a draft. Only make it public once all expected assets exist.
# A unique tag per run/attempt avoids touching any legacy or stable release.
if gh release view "$tag" -R "$repo" >/dev/null 2>&1; then die 'release exists; refusing overwrite'; fi
gh release create "$tag" -R "$repo" --draft --prerelease --latest=false \
    --target "$GITHUB_SHA" --title 'Cubie A5E OpenWrt r38527 + AIC8800 + LuCI Footstrap (не проверено на железе)' \
    --notes-file "$tmp/notes.md" "$tmp/up/"*
gh release view "$tag" -R "$repo" --json assets --jq '.assets[].name' | LC_ALL=C sort > "$tmp/remote-assets"
(cd "$tmp/up" && printf '%s\n' * | LC_ALL=C sort) > "$tmp/expected-assets"
cmp "$tmp/remote-assets" "$tmp/expected-assets"
gh release edit "$tag" -R "$repo" --draft=false --prerelease --latest=false
gh release view "$tag" -R "$repo" --json url,isDraft,isPrerelease,tagName,targetCommitish
