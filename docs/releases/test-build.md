## Hardware test status / Состояние испытаний — 2026-10-13

**Russian:** На Radxa Cubie A5E V1.1 с Micron 4 ГБ подтверждена загрузка
тестового ext4-образа с microSD. Встроенный AIC8800D80 виден на SDIO
контроллере `4021000.mmc`; при успешной загрузке появляются firmware/PHY,
SDIO фактически работает на 33,33 МГц. При другом запуске той же карты
прошивка Wi-Fi дважды завершалась по `data error` / `-110`.
Один PHY/MAC (`fc:23:cd:03:8e:78`) наблюдался с разными именами
`mmc0/mmc1`, что приводило к дублированию UCI `radioX`.
Полноценная точка доступа, связь клиента, 20 холодных стартов и
`aic8800-recover` **ещё не прошли аппаратную приёмку**.

**English:** The ext4 microSD image has booted on a 4 GB Micron Cubie A5E.
The onboard AIC8800D80 sometimes loads firmware/registers a PHY, but on
another boot of the same card, SDIO firmware upload failed twice with
`-110`. MMC host numbering can change; the same Wi-Fi gets multiple
`radioX` entries if matched by path only. Stable AP/client operation and
manual recovery **have not yet passed hardware validation**.

Test builds are **rolling**; the release tag is replaced by new successful
builds. Check the actual build SHA and image SHA256 before concluding which
fixes are included. The following fixes live on the experimental branch
`claude/fix-a5e-rootfs-sdio-uci`: UCI first-boot retry, radio binding by
detected MAC, and manual-only SDIO recovery. Their presence in a particular
image depends on that image's commit SHA.

- [Detailed investigation / Полный журнал](https://github.com/Medvedolog/cubie-a5e-openwrt/blob/claude/zen-babbage-ss68yn/docs/AIC8800-SDIO-WIFI.ru.md)
- [Manual SDIO recovery / Инструкция](https://github.com/Medvedolog/cubie-a5e-openwrt/blob/claude/zen-babbage-ss68yn/docs/AIC8800-RECOVERY.ru.md)
- [Hardware test protocol / План тестов](https://github.com/Medvedolog/cubie-a5e-openwrt/blob/claude/zen-babbage-ss68yn/docs/TEST-PLAN.md)

---

## Testing / тестирование

What to report (issue or the test thread): board revision, RAM size and
maker (photo of the chip or `sunxi_dram_para` from the vendor U-Boot), which
image (profile, ext4/squashfs), what worked and what did not, and the logs:

- does not boot: the UART log from power-on (pins 6 GND / 8 TX / 10 RX,
  115200 8N1);
- boots: `dmesg`, `logread`, `ip -br link`, `iw dev`, `lsusb`, `lspci`.

Что сообщить (issue или тема с тестами): ревизия платы, объём и
производитель памяти (фото чипа или `sunxi_dram_para` из вендорского
U-Boot), какой образ (профиль, ext4/squashfs), что работает и что нет, и
логи:

- не грузится: лог UART с момента включения (пины 6 GND / 8 TX / 10 RX,
  115200 8N1);
- грузится: `dmesg`, `logread`, `ip -br link`, `iw dev`, `lsusb`, `lspci`.

Packages in this pre-release (`kmod-aic8800-sdio`, `aic8800-sdio-firmware`)
fit only the kernel of the same build. / Пакеты в этом пререлизе подходят
только к ядру этой же сборки.
