# Эксперимент: Armbian U-Boot на Radxa Cubie A5E V1.1 / 4 ГБ

**Ветка:** `test/a5e-v1.1-armbian-uboot`

## Цель

Сравнить холодную загрузку платы V1.1 / 4 ГБ на U-Boot из Armbian
и на уже собранном U-Boot OpenWrt с профилем Micron M6. Это
**диагностический эксперимент**, а не новая рекомендуемая прошивка.

## Источники

- Готовые SD-образы OpenWrt из успешного Actions #42056025519,
  в которых тестировался `micron-4g-m6`.
- **Реально собранный Armbian U-Boot**, а не переименованный загрузчик
  OpenWrt: официальный `./compile.sh uboot BOARD=radxa-cubie-a5e
  BRANCH=current RELEASE=trixie` из armbian/build. Исходный коммит
  Armbian записывается в `armbian-framework-sha.txt`.
- В Armbian 2026.11 используется общий `v2026.10-sunxi64` U-Boot
  и `radxa-cubie-a5e_defconfig`. Его параметры DRAM не обязаны
  совпадать с нашим профилем Micron M6 (1200 МГц, TPR6/10/11/12).

## Метод

GitHub Actions собирает Armbian U-Boot, извлекает
`u-boot-sunxi-with-spl.bin` из собственного .deb, проверяет
Allwinner eGON SPL signature и размер, после чего заменяет **только
диапазон загрузчика на смещении 8 КиБ** внутри копий SD-образов.
MBR/разделы, OpenWrt FIT/DTB, rootfs и APK не пересобираются.

Публикуется отдельный артефакт
`a5e-v1.1-armbian-uboot-hybrid-EXPERIMENTAL` с двумя файлами
`*armbian-v1.1-4g-test-ext4-sdcard.img.gz` и
`*armbian-v1.1-4g-test-squashfs-sdcard.img.gz`.

**Ограничение:** даже успешно собранный SPL/U-Boot может не
загружать FIT OpenWrt (другая конфигурация bootcmd, поиск boot.scr/
extlinux, окружение). Также различие DRAM training может не позволить
загрузить плату вовсе. Пока это именно гибридный образ для опытного
тестера с UART, а не обещание работоспособности.

## Испытания

1. Проверить чипы ОЗУ: Micron ли установлен на плате V1.1.
2. Записать образ **только на отдельную microSD**. Не менять eMMC/SPI.
3. Снять UART с самого включения питания, записать версии SPL,
   TF-A/BL31 и U-Boot, тип/частоту/объём DRAM и ошибки.
4. Для контроля аналогично загрузить оригинальный
   `dram-micron-4g-m6` OpenWrt из сборки #42056025519.
5. Сделать несколько холодных стартов. Сравнить стадию отказа:
   SPL/DRAM, BL31/FIP, U-Boot, поиск OpenWrt FIT, запуск Linux.
6. При проблемах приложить полный UART boot.log, фото маркировки
   DRAM и описание, какой образ реально загружается.

Поскольку выбран отдельный репозиторий тестов, сборка не затрагивает
основные релизы `cubie-a5e-test` или `cubie-a5e-snapshot-latest`.
