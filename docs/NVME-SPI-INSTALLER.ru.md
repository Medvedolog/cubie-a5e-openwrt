# Cubie A5E V1.1 / 4 GiB — экспериментальный автономный NVMe OpenWrt

## Назначение

Это **отдельный тестовый установщик** с microSD, который работает
офлайн и по явной команде готовит два устройства:

- **NVMe (например /dev/nvme0n1):** полная система OpenWrt, MBR,
  раздел FAT (20 MiB) с FIT `uImage` и `boot.scr`, корень ext4 (сначала 2 ГиБ, затем автоматически на всю ёмкость SSD ещё при установке).
  `boot.scr` ищет PARTUUID раздела **NVMe**, а не microSD.
- **SPI NOR (16 MiB):** SPL + TF-A + U-Boot Armbian 2026.10, штатный
  `u-boot-sunxi-with-spl.bin` из собранного Armbian .deb.
  Запись только по подтверждению и после полного дампа оригинальной SPI.

Результат: **BootROM → SPI NOR U-Boot → NVMe FAT/boot.scr →
OpenWrt FIT (Linux 6.18.55) → NVMe ext4 rootfs**. После первого
проверенного запуска microSD можно убрать.

Это **не Armbian в rootfs**: Armbian используется только как загрузчик,
OpenWrt собирается из нашего пропатченного дерева PR #23296.

### Важные отличия от обычного образа

- `CONFIG_BLK_DEV_NVME=y`, `CONFIG_NVME_CORE=y`: NVMe доступен ядру
  ещё *до* монтирования корневого раздела.
- `CONFIG_SPI_SUN6I=y`, `CONFIG_MTD_SPI_NOR=y`: SPI0 с устройством
  `jedec,spi-nor` включён в DTS Cubie A5E; ожидается `/dev/mtd0`.
- `block-mount`, `parted`, `resize2fs`, `nvme-cli`, BusyBox `flashcp`
  включены в тестовую сборку.
- На **установочную SD** встроены `a5e-nvme-openwrt.img.gz` и
  `armbian-u-boot-sunxi-with-spl.bin` с SHA256 и командой
  `/usr/sbin/a5e-install-nvme`. Никаких скачиваний на роутере.
- SD использует SPL Armbian со смещением **8 KiB**. SPI NOR требует
  записывать этот же файл с **нулевого** смещения. Нельзя переносить
  сырой SD-образ целиком в SPI NOR.

## Как тестировать

1. В GitHub Actions найти успешный запуск ветки
   `claude/a5e-ssd-installer`, артефакт
   `a5e-SPI-NVMe-offline-installer-EXPERIMENTAL`. Сборка должна
   пройти все проверки: NVMe встроен в ядро, SPI NOR и скрипт
   установщика обнаружены в образе. Если CI упал, **не прошивать**.
2. Распаковать `a5e-hybrid-microsd-installer.img.gz` из ZIP и записать
   на **отдельную microSD** целиком, например balenaEtcher или
   `gzip -dc ... | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress`.
   Все данные на microSD будут уничтожены.
3. Подключить Ethernet, включить питание и загрузить OpenWrt с microSD.
   Установка проходит по SSH: `ssh root@192.168.1.1`. UART не требуется. Нужна плата **Cubie A5E V1.1 / 4 GiB**. В ходе первого
   старта root-ext4 на SD может расшириться, с одной перезагрузкой.
4. Предварительно осмотреть **без записи**:

   ```sh
   a5e-install-nvme --check
   cat /proc/mtd
   ls /dev/nvme*
   nvme list
   ```

5. **Не делайте этого, если на SSD есть нужные данные.** Для установки
   системы и загрузчика:

   ```sh
   a5e-install-nvme --install /dev/nvme0n1 --flash-spi
   ```

   После проверки контрольных сумм и размеров программа потребует два
   разных ручных подтверждения:
   `ERASE-nvme0n1` и `FLASH-SPI-16M`.
   Сначала полностью записывается и сверяется NVMe, корневой раздел и ext4 расширяются
   сразу на всю доступную ёмкость SSD. Затем читается
   и сохраняется **вся SPI NOR 16 MiB** в
   `/root/cubie-a5e-spi-before-nvme-*.bin` и
   `.bin.sha256` на microSD. Только после отдельного подтверждения
   записывается загрузчик Armbian и сверяется его содержимое.
   Путь к резервной копии выводится в консоль. Скопируйте её на ПК.
6. Выполнить `poweroff` по SSH, **вынуть microSD**, включить устройство
   и проверить доступность OpenWrt по SSH.
   Ожидаем на UART `Trying to boot from sunxi SPI`, затем
   инициализацию PCIe/NVMe, чтение `boot.scr`, запуск OpenWrt FIT
   и `root=PARTUUID=...`. После загрузки:

   ```sh
   cat /proc/cmdline
   mount | grep ' on / '
   ls -l /dev/nvme*
   df -h /
   logread | grep -E 'a5e-root-grow|nvme'
   ```

   NVMe ext4 уже расширен до ёмкости накопителя при установке по SSH.
   Проверить три последовательных холодных старта без SD.

## Разделение на этапы

Можно выполнить только

```sh
a5e-install-nvme --install /dev/nvme0n1
```

Это подготовит NVMe, **не трогая SPI**. Затем на UART/U-Boot
можно испытать чтение NVMe. Полная автономность требует совместимого
SPI загрузчика, установщик не перепрошивает его без `--flash-spi`.

## Предупреждения и восстановление

- Пока это лабораторный эксперимент, **аппаратного теста автономного
  старта OpenWrt из SPI/NVMe нет**. Успешная сборка — только
  проверка содержимого, не гарантия загрузки.
- Для SPI обязателен стабильный источник питания, UART и возможность
  загрузки через **FEL**. Отключение питания во время записи SPI может
  оставить плату без обычной загрузки.
- Установщик рассчитан на **16-МиБ NOR, доступную как /dev/mtd0**.
  Иную разметку/размер он не принимает. Нельзя подменять `mtd0` по
  номеру без проверки реального имени устройства.
- Если после установки NVMe не загружается, верните microSD и снимите
  полный UART-лог. Если SPI повреждена, восстановление выполняется
  отдельно через FEL и сохранённый дамп, после анализа содержимого.
- В SPI пишется только область загрузчика в начале; остальная часть
  микросхемы **не должна использоваться как хранилище данных**.
- Без SD ядро должно иметь *встроенный* NVMe; обычный гибрид
  #42092944575 со сменным `nvme.ko` не годится для NVMe-root.

## Источники и контрольные факты

- Radxa: [установка на NVMe](https://docs.radxa.com/en/cubie/a5e/getting-started/install-system/nvme-system),
  [управление SPI загрузчиком](https://docs.radxa.com/en/cubie/a5e/getting-started/install-system/nvme-system/burn-spi).
- U-Boot: [Allwinner SPI NOR требует запись с нулевого смещения](https://docs.u-boot-project.org/en/latest/board/allwinner/sunxi.html).
- Альтернативная SPI/NVMe реализация: [NixOS Cubie A5E](https://github.com/patryk4815/nixos-cubie-a5e), подтверждает
  `CONFIG_SPL_SPI_SUNXI`, `boot_targets` с `nvme0` и
  необходимость включить `spi0` в DTS.

## Только SSH, без UART

```sh
ssh root@192.168.1.1
a5e-install-nvme --check
a5e-install-nvme --install /dev/nvme0n1 --flash-spi
# Два подтверждения: уничтожение SSD, затем изменение SPI NOR.
# rootfs на NVMe расширяется до полного размера SSD до записи SPI.
poweroff
```

После выключения извлечь microSD и включить питание. Убедиться,
что роутер доступен по SSH, проверить `df -h /` и
`cat /proc/cmdline`. UART для штатной установки не нужен.
Если запись SPI оказалась неудачной, доступ по SSH может пропасть —
тогда потребуется восстановление через FEL; UART полезен для диагностики.
