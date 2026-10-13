# Как собирать OpenWrt прямо на GitHub Actions

**Практическое руководство на примере Radxa Cubie A5E (Allwinner A527)**  
**Дата:** 13 октября 2026 года  
**Репозиторий-пример:** [Medvedolog/cubie-a5e-openwrt](https://github.com/Medvedolog/cubie-a5e-openwrt)

> **Для кого:** для тех, кто хочет собирать OpenWrt из исходников в публичном GitHub-репозитории, не устанавливая компиляторы на собственном компьютере.
>
> **Важно:** Cubie A5E пока является экспериментальной аппаратной платформой для нашего проекта. Успешная сборка не означает, что все устройства платы стабильно работают. Ниже описан реальный сборочный процесс, а не гарантия готовности прошивки к эксплуатации.

## 1. Идея в двух словах

GitHub Actions выдаёт проекту временную машину Ubuntu. Она выполняет команды из файла `.github/workflows/build.yml`:

```text
Вы меняете код/конфигурацию в GitHub
                  |
                  v
          GitHub Actions
         (временная Ubuntu)
                  |
        скачивает исходники OpenWrt
                  |
        накладывает свои патчи
                  |
        устанавливает пакеты и собирает
                  |
        проверяет готовые образы
                  |
                  v
     Artifacts (.img.gz, APK, логи)
                  |
                  v
        GitHub Releases (по CI)
```

Свой компьютер во время сборки можно выключить. Публичные репозитории могут использовать стандартные GitHub-hosted runners без оплаты; действуют ограничения GitHub по ресурсам и времени выполнения.

## 2. Почему мы не храним весь OpenWrt в репозитории

В нашем проекте хранятся **только собственные настройки, драйверы, патчи и автоматизация**. Сами исходники OpenWrt скачиваются в процессе сборки. Это легче поддерживать и удобнее проверять в истории изменений Git.

Структура проекта (упрощённо):

```text
cubie-a5e-openwrt/
├── .github/workflows/
│   ├── build.yml             # сборка и проверки
│   ├── publish.yml           # публикация успешного CI в Releases
│   └── release-tag.yml       # фиксированный релиз из проверенной сборки
├── config/
│   ├── diffconfig            # целевая плата, пакеты, тип rootfs
│   └── dram/
│       └── micron-4g-m6.conf # отдельные параметры памяти для U-Boot
├── target/                   # наши файлы/патчи целевой платформы
├── package/                  # драйвер AIC8800 и патчи U-Boot
├── patches/openwrt/          # патчи к существующим файлам OpenWrt
├── files/etc/uci-defaults/   # настройки, попадающие внутрь rootfs
│   └── 99-cubie-a5e-test-config
├── scripts/
│   ├── check-image.py        # проверки результатов сборки
│   └── dram-profile-patch.py
└── docs/                     # документация и заметки о тестах
```

**Посмотреть оригиналы:** [build.yml](https://github.com/Medvedolog/cubie-a5e-openwrt/blob/claude/fix-a5e-rootfs-sdio-uci/.github/workflows/build.yml), [diffconfig](https://github.com/Medvedolog/cubie-a5e-openwrt/blob/claude/fix-a5e-rootfs-sdio-uci/config/diffconfig), [publish.yml](https://github.com/Medvedolog/cubie-a5e-openwrt/blob/claude/fix-a5e-rootfs-sdio-uci/.github/workflows/publish.yml).

## 3. Что именно мы собираем

Наш пример — **Radxa Cubie A5E** на **Allwinner A527** с 64-битными ядрами Cortex-A55. Поддержка A527 в OpenWrt берётся из [upstream PR #23296](https://github.com/openwrt/openwrt/pull/23296), поскольку в выбранной базе проекта она ещё не включена в основную ветку OpenWrt.

В `build.yml` исходная ревизия закреплена:

```yaml
env:
  OPENWRT_REPO: https://github.com/openwrt/openwrt.git
  OPENWRT_PR: 23296
  OPENWRT_COMMIT: 5035e7d51ae54590309cbcf36e638c783e7a0557
  TARGET: sunxi
  SUBTARGET: cortexa55
  PROFILE: radxa_cubie-a5e
```

**Зачем фиксировать commit?** Чтобы новая сборка не получала неожиданно изменившееся ядро или набор патчей. Это обеспечивает повторяемую **базу OpenWrt**, хотя для строгой воспроизводимости также нужно фиксировать ревизии feeds и остальные внешние зависимости.

## 4. Где выбирать пакеты и файловую систему

В нашем проекте это [`config/diffconfig`](https://github.com/Medvedolog/cubie-a5e-openwrt/blob/claude/fix-a5e-rootfs-sdio-uci/config/diffconfig). Ниже реальные строки из него:

```config
CONFIG_TARGET_sunxi=y
CONFIG_TARGET_sunxi_cortexa55=y
CONFIG_TARGET_sunxi_cortexa55_DEVICE_radxa_cubie-a5e=y

CONFIG_TARGET_ROOTFS_EXT4FS=y
CONFIG_TARGET_ROOTFS_SQUASHFS=y
# CONFIG_TARGET_ROOTFS_INITRAMFS is not set
CONFIG_TARGET_ROOTFS_PARTSIZE=512
CONFIG_TARGET_KERNEL_PARTSIZE=32

CONFIG_PACKAGE_kmod-aic8800-sdio=y
CONFIG_PACKAGE_aic8800-sdio-firmware=y
CONFIG_PACKAGE_wpad-mbedtls=y
CONFIG_PACKAGE_kmod-nvme=y
CONFIG_PACKAGE_luci=y
CONFIG_PACKAGE_iperf3=y
```

Что здесь означает каждая группа:

- `TARGET` / `DEVICE` — конкретная аппаратная платформа.
- `EXT4FS` и `SQUASHFS` — два типа штатного корневого раздела для тестирования.
- `INITRAMFS` выключен — штатная SD-прошивка должна загружаться с раздела карты, а не использовать встроенную в ядро временную файловую систему.
- `kmod-aic8800-sdio` — драйвер встроенного Wi-Fi AIC8800D80; отдельный пакет содержит firmware.
- `kmod-nvme` — поддержка накопителя NVMe на PCIe.
- `luci` — веб-интерфейс управления; `iperf3` — измерение скорости сети.

После копирования конфигурации OpenWrt разворачивает зависимости:

```bash
cp ../config/diffconfig .config
make defconfig
```

> **Важно:** это фрагмент именно нашего проекта, а не универсальная конфигурация для любой модели. Для другого роутера нужно выбрать его `TARGET`, `SUBTARGET`, `DEVICE` и необходимые драйверы.

## 5. Где происходит сама сборка

Workflow находится в `.github/workflows/build.yml`. Его логика — последовательность шагов.

### 5.1. Получить исходники OpenWrt

Упрощённый эквивалент команды из нашего workflow:

```bash
git init openwrt
git -C openwrt remote add origin https://github.com/openwrt/openwrt.git
git -C openwrt fetch --depth 1 origin 5035e7d51ae54590309cbcf36e638c783e7a0557
git -C openwrt checkout FETCH_HEAD
```

В действительном workflow предусмотрено также получение commit через ref pull request в случае проблем с прямой загрузкой.

### 5.2. Установить feeds

```bash
cd openwrt
./scripts/feeds update -a
./scripts/feeds install -a
```

### 5.3. Добавить свои файлы, драйверы и патчи

После получения исходников workflow переносит собственные каталоги `target/`, `package/`, `files/` в дерево OpenWrt и применяет `.patch` из `patches/openwrt/`.

Пример:

```bash
cp -a ../target ../package ../files .
for patch in ../patches/openwrt/*.patch; do
    git apply --whitespace=nowarn "$patch"
done
```

В реальном workflow перед копированием дополнительно проверяются конфликты имён с исходными файлами OpenWrt — это защита от незаметной подмены чужого кода.

### 5.4. Собрать

```bash
cp ../config/diffconfig .config
make defconfig
make download -j8
make -j"$(nproc)"
```

`$(nproc)` — число доступных процессоров сборочной машины. Наш CI также сохраняет кэш компилятора `ccache`, скачанные исходники и подробные логи. При ошибке параллельной сборки запускает диагностический повтор с `-j1 V=s`.

## 6. Настройки OpenWrt прямо внутри образа: UCI defaults

Проект содержит файл [`files/etc/uci-defaults/99-cubie-a5e-test-config`](https://github.com/Medvedolog/cubie-a5e-openwrt/blob/claude/fix-a5e-rootfs-sdio-uci/files/etc/uci-defaults/99-cubie-a5e-test-config).

`files/` — стандартный способ поместить дополнительные файлы в rootfs при сборке из исходников. Скрипты `/etc/uci-defaults/` обычно применяются при первом запуске и после успешного выполнения удаляются механизмом OpenWrt.

В нашем тестовом образе задаются:

```sh
#!/bin/sh
uci -q get wireless.radio0 >/dev/null 2>&1 || exit 1
uci -q get wireless.default_radio0 >/dev/null 2>&1 || exit 1

uci set network.lan.ipaddr='192.168.1.1'
uci set network.lan.netmask='255.255.255.0'
uci set network.lan.ip6assign='60'

uci set wireless.radio0.channel='36'
uci set wireless.radio0.htmode='HE80'
uci set wireless.radio0.country='PA'
uci set wireless.radio0.txpower='20'
uci set wireless.radio0.disabled='0'

uci set wireless.default_radio0.ssid='OpenWrt'
uci set wireless.default_radio0.encryption='none'
uci -q delete wireless.default_radio0.key

uci commit network
uci commit wireless
```

Полный файл также задаёт `cell_density=0` и проверяет наличие LAN. **Это лабораторная конфигурация:** сеть открытая, без пароля. Для обычного использования следует настроить шифрование и выбрать регуляторную страну, соответствующую реальному месту эксплуатации; `PA` не является универсальным выбором.

**Почему `192.168.1.1` + `255.255.255.0`, а не `192.168.1.1/24`?** Это явно задаёт адрес и маску стандартными отдельными параметрами UCI.

## 7. Особенность нашего A5E: разные DRAM-профили

На Cubie A5E разные ревизии плат могут использовать разную память. В нашем проекте есть:

| Профиль | Для чего |
|---|---|
| `dram-universal` | Основной U-Boot с DRAM 936 МГц и резервными параметрами |
| `dram-micron-4g-m6` | Профиль Micron LPDDR4 4 ГБ, DRAM 1200 МГц |

Профили задаются файлами `config/dram/*.conf`, например `micron-4g-m6.conf`. Скрипт `scripts/dram-profile-patch.py` создаёт патч для U-Boot.

**Важный урок из наших тестов:** при повторной полной упаковке образа после пересборки U-Boot во втором варианте загрузка попала в `recovery (initramfs)`, хотя Wi-Fi работал. Поэтому исправленный workflow должен заменять в готовом SD-образе **только область SPL/U-Boot**, оставляя boot-раздел с ядром и rootfs неизменными.

Это проверяется в CI: образы двух DRAM-профилей одного типа файловой системы должны иметь одинаковые контрольные суммы загрузочного и корневого разделов. Такая проверка подтверждает идентичность разделов, но **не заменяет проверку загрузки на настоящей плате**.

## 8. Как запустить сборку в браузере

1. Открыть [GitHub Actions нашего проекта](https://github.com/Medvedolog/cubie-a5e-openwrt/actions).
2. В списке слева выбрать **Build image (OpenWrt from source)**.
3. Нажать **Run workflow**.
4. Выбрать нужную ветку. Для нашего экспериментального исправления — `claude/fix-a5e-rootfs-sdio-uci`.
5. В параметре `runner` оставить `github` (или выбрать `self-hosted`, если есть свой настроенный runner).
6. Поле `openwrt_commit` оставить пустым, чтобы использовать закреплённый commit. `clean_ccache` обычно `false`.
7. Нажать зелёную кнопку **Run workflow**. После запуска открыть задание `build`: каждый шаг покажет свой лог.

Можно и **ничего не нажимать**: в нашем проекте сборка автоматически запускается при push в ветки `main` или `claude/**`, если изменены `target/`, `package/`, `patches/`, `config/`, `files/`, `scripts/` или сам `build.yml`.

> Если вы используете GitHub Actions в другом репозитории, убедитесь, что Actions разрешены в его настройках и workflow доступен в выбранной ветке.

## 9. Где искать результаты

### Артефакты одной конкретной сборки

Откройте успешно завершившийся запуск в **Actions** и найдите блок **Artifacts**:

| Артефакт | Содержимое |
|---|---|
| `cubie-a5e-image` | Образы `.img.gz`, `sha256sums`, сведения о сборке |
| `cubie-a5e-packages` | Собранные пакеты `.apk` |
| `build-logs` | Полная конфигурация, логи компиляции, результаты проверок |

В новых сборках OpenWrt этого проекта используются `.apk` (пакеты менеджера `apk`), а не старые `.ipk`.

### Автоматическая публикация на странице Releases

Наш [`publish.yml`](https://github.com/Medvedolog/cubie-a5e-openwrt/blob/claude/fix-a5e-rootfs-sdio-uci/.github/workflows/publish.yml) получает артефакты **успешной** сборки и публикует их **без повторной компиляции**:

- Из `main` → плавающий пререлиз `cubie-a5e-snapshot-latest`.
- Из других веток → плавающий пререлиз [`cubie-a5e-test`](https://github.com/Medvedolog/cubie-a5e-openwrt/releases/tag/cubie-a5e-test).

**Осторожно:** оба плавающих релиза могут обновляться последующими сборками. Поэтому для точной идентификации теста сохраняйте SHA коммита, номер Actions run и хэш конкретного файла. Не считайте ссылку `cubie-a5e-test` неизменяемой.

Workflow `release-tag.yml` предназначен для фиксированного выпуска из ранее проверенных образов, без новой компиляции.

## 10. Как проверить файл перед прошивкой

После скачивания сравните SHA-256 с опубликованным `sha256sums`:

Linux:

```bash
sha256sum openwrt-sunxi-cortexa55-radxa_cubie-a5e-dram-universal-ext4-sdcard.img.gz
```

Windows PowerShell:

```powershell
Get-FileHash .\openwrt-sunxi-cortexa55-radxa_cubie-a5e-dram-universal-ext4-sdcard.img.gz -Algorithm SHA256
```

Сверьте выведенный хэш со строкой для **того же файла** из `sha256sums` того же релиза.

**При записи на карту:** сначала убедитесь, что выбрано правильное устройство. Запись `.img.gz` стирает данные на целевом носителе. Для тестов держите резервную SD-карту с заведомо работающим образом.

## 11. Частые ошибки

| Симптом | Что смотреть |
|---|---|
| Workflow не появился | Есть ли `.github/workflows/build.yml` и разрешены ли Actions |
| Сборка упала при `make` | `build-logs`, последнее сообщение об ошибке, повтор `-j1 V=s` |
| Не хватает диска | Шаг `Free disk space`, размер `dl/`, `build_dir/`, кэши |
| Исходники обновились и всё сломалось | Закрепить OpenWrt commit и проверить версии feeds |
| Пакет `kmod` не подходит | Он должен соответствовать **точно тому же ядру и ABI** |
| CI успешен, но плата не грузится | Смотреть UART: сборочные проверки не симулируют железо |
| Загрузка в `initramfs` вместо rootfs | Проверить содержимое FIT/kernel и повторную упаковку SD-образов |
| Wi-Fi не стартует, SDIO `-110` | Сохранять UART/dmesg, проверять SDIO clock и холодные старты; причина может быть не в одной только частоте |

## 12. Что нужно, чтобы сделать такой проект с нуля

Минимальная практическая последовательность:

1. Создать **публичный** репозиторий на GitHub.
2. Добавить `.github/workflows/build.yml` с событием `workflow_dispatch` и разрешением запуска из нужных веток.
3. Указать конкретную версию OpenWrt и создать `config/diffconfig` под свою плату.
4. Добавить требуемые драйверы и патчи в `package/`, `target/`, `patches/openwrt/`.
5. Добавить файлы, которые должны попасть в прошивку, в `files/`.
6. В workflow последовательно сделать `checkout`, загрузку исходников, `feeds`, конфигурирование, `make download`, `make`, проверки и `upload-artifact`.
7. Запустить сборку из **Actions**; по результатам проверить не только компиляцию, но и загрузку реального устройства.
8. После стабилизации включить публикацию в **Releases** и написать тестовый план.

**Существенный момент:** просто скопировать `build.yml` A5E в пустой репозиторий **недостаточно**. Он зависит от наших каталогов, патчей, `diffconfig`, скриптов и конкретной ревизии OpenWrt. Как полный рабочий пример надо рассматривать репозиторий целиком.

---

### Ссылки на исходный проект

- [Репозиторий Cubie A5E](https://github.com/Medvedolog/cubie-a5e-openwrt)
- [Ветка экспериментальной пересборки](https://github.com/Medvedolog/cubie-a5e-openwrt/tree/claude/fix-a5e-rootfs-sdio-uci)
- [Pull Request с исправлениями rootfs/SDIO/UCI](https://github.com/Medvedolog/cubie-a5e-openwrt/pull/1)
- [Сборки GitHub Actions](https://github.com/Medvedolog/cubie-a5e-openwrt/actions)
- [Тестовые образы Releases](https://github.com/Medvedolog/cubie-a5e-openwrt/releases/tag/cubie-a5e-test)
- [Поддержка A527 в upstream OpenWrt, PR #23296](https://github.com/openwrt/openwrt/pull/23296)

*Материал основан на фактической структуре `Medvedolog/cubie-a5e-openwrt` и workflow ветки `claude/fix-a5e-rootfs-sdio-uci` по состоянию на 13.10.2026. При изменении workflow, CI и веток отдельные детали могут устареть.*