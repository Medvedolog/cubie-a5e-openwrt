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
