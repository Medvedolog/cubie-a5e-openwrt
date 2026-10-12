# OpenWrt для Radxa Cubie A5E (Allwinner A527) со встроенным Wi-Fi

**[English version](README.md)**

Чистая сборка OpenWrt для Radxa Cubie A5E: OpenWrt main с поддержкой A527,
которая пока на рецензии, собранный из исходников на GitHub Actions, со
встроенным Wi-Fi (AIC8800D80, SDIO), обоими гигабитными портами, USB и
M.2 NVMe.

> **Статус: первые сборки. На железе ещё ничего не проверено.**
> Таблица ниже обновляется только по отчётам с логами с платы.

## Почему сборка из исходников

В OpenWrt пока нет Allwinner A527. Поддержка на рецензии:
[openwrt/openwrt#23296](https://github.com/openwrt/openwrt/pull/23296)
«sunxi: add support for A527/T527 boards» от мейнтейнера sunxi (новая
подцель `cortexa55`, профиль `radxa_cubie-a5e`). Проект собирает эту ветку
на зафиксированном коммите и добавляет то, чего в ней нет для этой платы:
драйвер Wi-Fi AIC8800 (из ImmortalWrt), последовательность включения Wi-Fi,
запасной набор параметров DRAM для разных ревизий, пакеты NVMe
([docs/PORTING-NOTES.md](docs/PORTING-NOTES.md), по-английски). Когда PR
примут, сборка перейдёт на официальный snapshot, а здесь останется только
драйвер Wi-Fi — как в проекте для Orange Pi Zero 3.

Следствие: **kmod с downloads.openwrt.org к этому ядру не подходят.**
Все kmod для него будут опубликованы, подписанными, в собственном
apk-репозитории проекта (в плане, см. ниже).

## Статус

| Функция | Статус |
|---|---|
| Образ собирается в CI | в работе |
| Загрузка с microSD | не проверено |
| eth0 (LAN, 192.168.1.1) / eth1 (WAN, DHCP) | не проверено |
| Wi-Fi точка доступа / клиент, 2,4 ГГц | не проверено |
| Wi-Fi точка доступа / клиент, 5 ГГц | не проверено |
| Порты USB 2.0 | не проверено |
| USB 3.0 SuperSpeed | в этом образе нет (см. ниже) |
| M.2 NVMe | не проверено |
| reboot / выключение / sysupgrade | не проверено |

**Ревизии платы и память.** Владельцы сообщают, что mainline U-Boot
грузит не все ревизии: параметры DRAM зависят от чипов памяти. В этой
сборке добавлен запасной набор параметров; если плата всё равно не
стартует, нужен лог с UART (см.
[docs/COMMUNITY-FINDINGS.md](docs/COMMUNITY-FINDINGS.md#1-boot-dram-parameters-depend-on-the-board-revision)).

**USB 3.0 или NVMe.** В A527 одна combo-PHY на слот M.2 и порт USB 3.0
(аппаратное ограничение). Этот образ отдаёт её PCIe (M.2 NVMe), как
BSP Radxa по умолчанию; порты USB-A работают как USB 2.0. Вариант с USB3
запланирован ([PORTING-NOTES §4](docs/PORTING-NOTES.md#4-usb-what-works-and-what-does-not)).

## Скачать

Пока нет: образы лежат в артефактах запусков
[Build image](../../actions/workflows/build.yml), пока первый не загрузится
на плате.

## Устройство репозитория

| Путь | Что |
|---|---|
| `target/`, `package/` | файлы, добавляемые в дерево OpenWrt: последовательность включения Wi-Fi (DTS), запасной набор DRAM в U-Boot, пакет `aic8800` |
| `patches/openwrt/` | изменения файлов дерева OpenWrt (возможность PCI у подцели) |
| `config/diffconfig` | конфигурация сборки |
| `scripts/check-image.py` | проверки собранного образа (DTB в FIT, rootfs, конфиг ядра) |
| `.github/workflows/build.yml` | сборка: PR #23296 на зафиксированном коммите, наши файлы, `make`, проверки |
| `docs/` | [заметки о портировании](docs/PORTING-NOTES.md), [находки сообщества](docs/COMMUNITY-FINDINGS.md); план тестов и аудит драйвера — позже |

Сборка идёт на раннерах GitHub или на своём (self-hosted) раннере —
параметр `runner` при ручном запуске. Пакеты подписываются секретом
репозитория `APK_SIGN_KEY` (закрытый EC-ключ P-256); без него используется
одноразовый ключ и ничего не публикуется.

## План

1. Образ, который грузится, с Wi-Fi — текущий шаг.
2. Подписанный apk-репозиторий на GitHub Pages со всеми kmod этого ядра.
3. Проверки образа в CI (начато: `scripts/check-image.py`).
4. Первая загрузка: точка доступа «A5E» с паролем-заглушкой и
   предупреждением в LuCI до его смены.
5. Состав образа как в проекте для Orange Pi Zero 3 (LuCI, WireGuard/
   AmneziaWG, sing-box, модемы, USB-Ethernet/Wi-Fi, NVMe).
6. «Скользящий» и фиксированные релизы с описанием.
7. После того как Wi-Fi заработает на железе — аудит драйвера aic8800.
8. Потом: Cubie A5E и aic8800 в OpenWrt upstream.

## Благодарности

- [OpenWrt](https://openwrt.org) и мейнтейнер sunxi Zoltan Herpai за
  поддержку A527/T527, на которой основана сборка.
- [ImmortalWrt](https://github.com/immortalwrt/immortalwrt): пакет
  `aic8800` и первая поддержка A527/Cubie A5E.
- [Radxa](https://github.com/radxa): плата, BSP и
  [radxa-pkg/aic8800](https://github.com/radxa-pkg/aic8800).
- Разработчики поддержки Allwinner sun55i (A523/A527/T527) в mainline Linux.

## Лицензия

GPL-2.0 ([LICENSE](LICENSE)). Файлы из других проектов сохраняют своих
авторов и лицензии.
