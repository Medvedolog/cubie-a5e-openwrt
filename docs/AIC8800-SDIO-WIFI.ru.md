# Cubie A5E — полевой журнал AIC8800D80: SDIO, прыгающие radioX и первая загрузка

**Обновлено: 2026-10-13.** Основано на двух присланных логах тестового
образа `ext4 / micron-4g-m6` и последующих консольных выводах с реальной
Radxa Cubie A5E V1.1 (Micron 4 ГБ). Это **не** универсальная оценка
стабильности всех A5E и не отчёт о пройденном release gate.

## 1. Главное: что подтверждено

| Объект | Факт с платы | Статус |
|---|---|---|
| MicroSD | Та же карта между удачным и неудачным запусками | подтверждено тестером |
| Загрузка Linux | `mmcblk0p2` с ext4, rootfs remount read-write | подтверждено dmesg |
| MMC SD-карты | `4020000.mmc`; имя `mmc0` либо `mmc1` | подтверждено sysfs/логами |
| MMC встроенного Wi-Fi | `4021000.mmc`; имя `mmc0` либо `mmc1` | подтверждено sysfs/логами |
| SDIO AIC8800 | VID `0xc8a1`, DID `0x0182`, адрес `390b` | подтверждено dmesg |
| Успешная загрузка firmware | `fmacfw_8800d80_u02.bin`, появляется `phy0` | подтверждено одним из стартов |
| Неудачный старт | `sunxi-mmc 4021000.mmc: data error`, `fail-110`, без PHY | подтверждено другим стартом |
| Фактическая частота Wi-Fi | 35 МГц requested / **33 333 333 Hz actual** | подтверждено `debugfs/mmc*/ios` на удачном старте |
| Стабильный PHY MAC | `fc:23:cd:03:8e:78` после перезагрузки не меняется | подтверждено тестером для проверенных перезагрузок |
| Wi-Fi AP и DHCP с клиентом | Работа hostapd, подключение, трафик не подтверждены отдельным протоколом | **требует теста** |
| Recovery после `-110` | Скрипт добавлен в репозиторий; на плате ещё не испытан | **эксперимент** |

Важное различие: **SDIO enumeration** (`390b`) — это не успешная загрузка
прошивки. Даже появление PHY не доказывает успешное подключение Wi-Fi-клиента.

## 2. Неудачный и успешный старты одного образа

**Неудачный:** Linux увидел SDIO-карту около 2,48 с, но первая передача
firmware около 12,43 с завершилась ошибкой. Драйвер пробовал ещё раз около
19,32 с — снова `-110`; соответствующие транзакции заканчивались
`cmd timed-out`, `bin upload fail: 1e2000, err:-110` и
`aicbt_patch_trap_data_load fail`. Интерфейс PHY не появился.

**Успешный:** тот же SD-носитель, SDIO обнаружено около 2,48 с,
загрузка AIC firmware начата около 12,1 с, затем
`fmacfw_8800d80_u02.bin`, `rd_version_val=06090101` и
`ieee80211 phy0: HT supp 1, VHT supp 1, HE supp 1` (~13,8 с).

В более позднем успешном выводе с платы было:

```text
sunxi-mmc 4020000.mmc: Got CD GPIO
sunxi-mmc 4021000.mmc: allocated mmc-pwrseq
mmc0: new high speed SDHC card at address 0001
mmcblk0: p1 p2
mmc1: new high speed SDIO card at address 390b
aicbsp: aicbsp_get_feature, set FEATURE_SDIO_CLOCK 0 MHz
rwnx_load_firmware :firmware path = /lib/firmware/aic8800/sdio/fmacfw_8800d80_u02.bin
```

`FEATURE_SDIO_CLOCK 0 MHz` в драйвере означает **не переопределять
частоту MMC**, а не передачу на 0 Гц. Патч
[`090-sdio-respect-mmc-clock.patch`](https://github.com/Medvedolog/cubie-a5e-openwrt/blob/claude/fix-a5e-rootfs-sdio-uci/package/kernel/aic8800/patches/090-sdio-respect-mmc-clock.patch)
убирает принудительное `FEATURE_SDIO_CLOCK_V3 = 150000000`.
DTS ограничивает скорость `max-frequency = <35000000>`.

## 3. Реальный MMC I/O и почему нельзя пользоваться mmcN как ID

Один успешный замер `/sys/kernel/debug/mmc*/ios`:

| Параметр | Wi-Fi MMC | microSD MMC |
|---|---|---|
| Контроллер | `4021000.mmc` | `4020000.mmc` |
| Запрошенный clock | 35 000 000 Гц | 50 000 000 Гц |
| Actual clock | **33 333 333 Гц** | **50 000 000 Гц** |
| Шина | SD high-speed, 4-bit | SD high-speed, 4-bit |
| Signal voltage | 1,8 В | 3,3 В |
| vdd | код 21 (диапазон 3,3–3,4 В) | код 21 (диапазон 3,3–3,4 В) |

Контроллеры в приведённом ниже тесте через `readlink` были
`mmc0 → 4020000.mmc`, `mmc1 → 4021000.mmc`. В других логах имена
`mmc0` и `mmc1` **менялись местами**. Не обращаться к системной
SD-карте, ориентируясь на имя `mmc0` или `mmc1`!

```sh
for h in /sys/class/mmc_host/mmc*; do
    echo "$h -> $(readlink -f "$h/device")"
done
for f in /sys/kernel/debug/mmc*/ios; do
    echo "=== $f ==="
    cat "$f"
done
```

Снижение частоты до 33,33 МГц и отказ от 150 МГц **не устранили**
наблюдаемые ошибки передачи firmware. По снимку после успешного старта
нельзя восстановить частоту непосредственно в момент сбоя.

## 4. Почему меняются radio0/radio1

При старте на разных MMC-хостах OpenWrt формировал:

```uci
wireless.radio0.path='platform/soc/4021000.mmc/mmc_host/mmc0/mmc0:390b/mmc0:390b:1'
wireless.radio1.path='platform/soc/4021000.mmc/mmc_host/mmc1/mmc1:390b/mmc1:390b:1'
```

Оба пути — **один физический AIC8800D80**, но разных загрузок. Запись
`radio0` была активирована, а `radio1` создана автоматически
(`wireless.default_radio1.disabled='1'`). При следующей загрузке
активность может приходиться уже на другой номер.

Генератор OpenWrt
[`mac80211.uc`](https://github.com/openwrt/openwrt/blob/5035e7d51ae54590309cbcf36e638c783e7a0557/package/network/config/wifi-scripts/files/lib/wifi/mac80211.uc)
сопоставляет PHY с UCI по `macaddr`, `phy` или *суффиксу пути*.
Изменение `mmcN` ломает совпадение последнего и создаёт новый
`radioX`. В
[ImmortalWrt master](https://github.com/immortalwrt/immortalwrt/blob/master/package/network/config/wifi-scripts/files/lib/wifi/mac80211.uc)
применён тот же общий подход, отдельного исправления для A5E не найдено.

### Что уже закоммичено в A5E

[`files/etc/uci-defaults/99-cubie-a5e-test-config`](https://github.com/Medvedolog/cubie-a5e-openwrt/blob/claude/fix-a5e-rootfs-sdio-uci/files/etc/uci-defaults/99-cubie-a5e-test-config):

- после `kmodloader` вызывает `/sbin/wifi config`, поскольку при
  раннем `uci-defaults` радио могло ещё не появиться;
- ищет PHY по реальному пути `4021000.mmc`;
- закрепляет `wireless.radio0.macaddr` по MAC встроенного AIC8800;
- удаляет нестабильный `wireless.radio0.path` и `phy`;
- удаляет только авто-дубликаты радио того же физического контроллера;
- задаёт 5 ГГц / канал 36 / HE80 / `PA` / SSID `OpenWrt` /
  `encryption='none'`;
- удаляет `wireless.default_radio0.disabled` и `key`;
- при отсутствии PHY выходит с ошибкой, чтобы `uci-defaults` повторился
  при следующей загрузке.

**Это исправление для первого применения, а не постоянный Wi-Fi hotplug.**
Наблюдаемая неизменность MAC `fc:23:cd:03:8e:78` подтверждает
жизнеспособность привязки по MAC на данной плате, но тесты нескольких
холодных стартов исправленного образа ещё нужны. Не переносить
фиксированный MAC этой платы в образ других пользователей.

### Почему подход OPIZ3 лучше для постоянной эксплуатации

В нашем проекте
[`opiz3-wlan-backport`](https://github.com/Medvedolog/opiz3-wlan-backport/blob/main/package/luci/luci-app-opiz3-status/root/etc/hotplug.d/ieee80211/11-opiz3-usb-macaddr)
на событии `ieee80211 add` USB-радио идентифицируется по MAC.
Если меняется номер USB-шины, текущий `path` обновляется для
существующего `radioX` без его удаления. Это сохраняет UCI-параметры
пользователя и не плодит секции.

**Следующая итерация A5E:** применить эквивалент к *встроенному SDIO*,
идентифицируя его по `4021000.mmc` и постоянному MAC; сохранить
имеющийся раздел `radioX` и AP/STA, обновлять `path`, а чистку старых
дубликатов сделать миграцией один раз. Отделить это от первого
`uci-defaults`, не менять пользовательский SSID после настройки.

## 5. UCI defaults и порядок загрузки

В OpenWrt `/etc/init.d/boot` может запускать
`/sbin/wifi config` **до** `kmodloader`, а затем выполняет
`uci_apply_defaults`. Если на момент `wifi config` устройство ещё не
появилось, проверка `wireless.radio0` не проходит. Сценарий
`uci-defaults` с кодом завершения 0 удаляется; при ошибке остаётся для
повторного запуска. Подробнее в исходном
[`boot`](https://github.com/openwrt/openwrt/blob/5035e7d51ae54590309cbcf36e638c783e7a0557/package/base-files/files/etc/init.d/boot).

Из наблюдения `uci show wireless`:
`radio0` содержал канал 36, HE80, страну PA, 20 dBm и активный AP, а
`radio1` содержал неактивный дубликат. Это значит, что настройки **были
записаны в UCI**, но не гарантирует, что AP действительно запустился на
актуальном PHY. Ошибку отсутствующего Wi-Fi нельзя объяснять только UCI:
в неудачном логе была независимая аппаратная ошибка SDIO `-110`.

**Внимание:** `encryption='none'` и `country='PA'` — параметры
лабораторного образа; страна должна соответствовать фактическому месту
эксплуатации, открытая сеть не подходит для повседневного роутера.

## 6. SDIO -110: гипотезы и следующие тесты

Путь ошибки: SDIO-устройство найдено → загрузка firmware началась →
`sdio_writesb` / `data error` в контроллере → тайм-аут сообщения /
`bin upload fail -110`. Это указывает на реальную проблему обмена с
устройством, а не на отсутствующий файл прошивки.

*Что проверено:* ограничение 35 МГц, `mmc-pwrseq` выделен, SD-карта
та же, удачная и неудачная загрузка на одном стенде.

*Что ещё не доказано:* причина `-110` — питание, `WL_REG_ON`, фазировка,
состояние чипа после reset, драйвер AIC8800 или комбинация этих факторов.
Два последовательных firmware retry в плохом старте не равны физическому
reset чипа. По коду Radxa AIC8800 без `CONFIG_PLATFORM_ALLWINNER`
`aicbsp_platform_power_off/on()` не обязаны переключать GPIO питания.
Поэтому даже `rmmod/modprobe` может не восстановить аппаратное состояние.

**Кандидаты независимых A/B-испытаний, по одному изменению:**

1. Ограничение `max-frequency` до 25 МГц, отдельный тестовый образ.
2. Эксперимент со временем/последовательностью `mmc-pwrseq`
   (`PM1 = WL_REG_ON`, post-power-on-delay 200 мс).
3. Отдельно сравнить regulator BLDO1 в Armbian:
   [патч `regulator-always-on`](https://github.com/armbian/build/blob/main/patch/kernel/archive/sunxi-6.18/patches.backports/34-fix-wifi-regulator-cubie-a5e.patch).
4. Инструментирование первой ошибки SDIO / firmware перед повтором.
5. Ручной **MMC-host reset + reinit** через
   [`aic8800-recover`](AIC8800-RECOVERY.ru.md) — не включать авто-reset,
   пока не проверена выгрузка модулей и сохранность Ethernet / microSD.

Для платы в Armbian патч
[`22-Enable-wifi-on-Radxa-Cubie-A5E`](https://github.com/armbian/build/blob/main/patch/kernel/archive/sunxi-6.18/patches.backports/22-Enable-wifi-on-Radxa-Cubie-A5E.patch)
применяет `mmc-pwrseq-simple`, `vmmc` 3,3 В, `vqmmc` BLDO1 1,8 В,
`max-frequency = <40000000>`. У нас 35 МГц; это осмысленное отличие.

Armbian также содержит
[`aic8800-Derive-the-fallback-MAC-from-the-SoC-efuse`](https://github.com/armbian/build/blob/main/patch/misc/aic8800/aic8800-Derive-the-fallback-MAC-from-the-SoC-efuse.patch).
**Этот патч рассчитан на SoC Sophgo / Milk-V Duo S, не на A527**:
его нельзя переносить целиком. На нашем тестовом AIC8800 MAC между
проверенными перезагрузками и так стабилен.

## 7. Восстановление по образцу OPIZ3

У OPIZ3 скрипт
[`uwe5622-recover`](https://github.com/Medvedolog/opiz3-wlan-backport/blob/main/package/kernel/uwe5622/files/uwe5622-recover)
после CP assert выгружает `sprdwl_ng` + `uwe5622_bsp_sdio`,
делает `unbind/bind` MMC-хоста и поднимает соответствующее PHY.
Есть защита от циклов: 3 попытки / 1800 секунд, lock, тайм-аут
`rmmod`, и [патч 250](https://github.com/Medvedolog/opiz3-wlan-backport/blob/main/package/kernel/uwe5622/patches/250-unisocwcn-sdiohal-unregister-driver-on-allwinner.patch),
который правильно освобождает SDIO-драйвер UNISOC.

У AIC8800 другие модульные интерфейсы:
`aic8800_fdrv` (потребитель) и `aic8800_bsp` (BSP).
В upstream `aicbsp_sdio_exit()` вызывает `sdio_unregister_driver`,
а `rwnx_mod_exit()` вызывает `aicbsp_set_subsys(AIC_WIFI, OFF)`.
Следовательно, патч 250 к AIC8800 **не применять механически**.
Это обещание кода, а не доказанная стабильность unload/reload на A5E.

В текущем репозитории уже добавлены:

- [`files/lib/aic8800.sh`](https://github.com/Medvedolog/cubie-a5e-openwrt/blob/claude/fix-a5e-rootfs-sdio-uci/files/lib/aic8800.sh) — физический
  контроллер, PHY, MAC, SDIO и UCI без привязки к `mmcN`;
- [`files/usr/sbin/aic8800-recover`](https://github.com/Medvedolog/cubie-a5e-openwrt/blob/claude/fix-a5e-rootfs-sdio-uci/files/usr/sbin/aic8800-recover) —
  ручные режимы `--check` / `--run`;
- [`docs/AIC8800-RECOVERY.ru.md`](AIC8800-RECOVERY.ru.md) —
  техника безопасности и первая аппаратная проверка;
- [`docs/TEST-PLAN.md`](TEST-PLAN.md) — протокол регрессионных испытаний.

**Recovery не должен автоматически вызываться при любом пропадании
`phy0`.** У AIC8800 пока нет подтверждённого события, подобного
`unisoc_wifi change` в OPIZ3. Автоматика только после ручной проверки
и добавления ограничений повторных попыток.

## 8. GitHub CI, статусы изменений и доказательность

Рабочая ветка испытаний:
[`claude/fix-a5e-rootfs-sdio-uci`](https://github.com/Medvedolog/cubie-a5e-openwrt/tree/claude/fix-a5e-rootfs-sdio-uci).

| Коммит | Что сделано | Доказано на железе? |
|---|---|---|
| `cfe52e8` | ext4/rootfs image, SDIO без принудительных 150 МГц, UCI defaults | ext4 и оба исхода Wi-Fi подтверждены логами |
| `57d686b` | `wifi config` после загрузки модулей, retry defaults | требует повторного первого старта |
| `9d69e12` | `radio0.macaddr`, очистка дубликатов, идентичность по `4021000.mmc` | MAC постоянен; логика требует теста на свежем образе |
| `ca4d44e` | удаление `wireless.default_radio0.disabled` | не испытано на новом образе |
| `40b6f77` | ручной SDIO recovery + проверка синтаксиса в CI | **не испытывался на плате** |

Готовность CI означает, что образ собран и прошёл проверки структуры,
**не** что холодный старт Wi-Fi стал надёжен. Публикация тега
`cubie-a5e-test` — скользящая; перед тестом фиксировать commit SHA,
имя и sha256sum конкретного `.img.gz`.

## 9. Минимальная диагностика и критерий готовности

```sh
cat /sys/class/ieee80211/phy*/macaddress
for h in /sys/class/mmc_host/mmc*; do
    echo "$h -> $(readlink -f "$h/device")"
done
for f in /sys/kernel/debug/mmc*/ios; do
    echo "=== $f ==="; cat "$f"
done
uci -q show wireless
iw dev
wifi status
dmesg | grep -Ei 'aic|sdio|mmc|firmware|timeout' | tail -100
logread | grep -Ei 'aic|hostapd|netifd|wireless' | tail -100
```

Протокол: минимум 20 холодных стартов, 10 `reboot`, отсутствие
неисправимых `-110` и лишних `radioX`; затем AP с клиентом,
DHCP и передача трафика. Это **цель для приёмки**, не уже полученные
результаты. Подробности: [TEST-PLAN](TEST-PLAN.md).
