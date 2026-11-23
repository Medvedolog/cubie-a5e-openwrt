# Cubie A5E board status and CPU frequency

Install `luci-app-a5e-board`. **Status → Overview → Board** shows readable
kernel temperatures from thermal zones and independent hwmon inputs, plus
every reported CPU frequency policy. A hwmon alias under the same Linux
thermal zone is not shown a second time.

**System → CPU frequency** edits one policy at a time, using only its current
kernel-advertised governor and frequency lists. Missing sysfs facilities
disable the corresponding controls. The tested official A5E image's DTB
describes four thermal zones (`cpu0-thermal`, `cpu4-thermal`, `gpu-thermal`,
`ddr-thermal`) but has no CPU OPP table; do not assume that image exposes DVFS.
The application adds no Device Tree changes and does not load a scaling
driver, set boot defaults, or modify thermal policy. Manual settings last
until reboot. The kernel can still throttle the actual CPU frequency.

The packaged rpcd ACL grants only `status` to read access. Only a session
granted write access for this application may call its two narrowly scoped
settings methods. Limits are written in an order that avoids invalid
intermediate ranges; rejected or mismatched changes are read back and the
previous limits restored when possible. No generic file, UCI, or command
access is granted.

Adapted in design and LuCI structure from Medvedolog's GPL-2.0-only
[Orange Pi board panel and CPU frequency page](https://github.com/Medvedolog/opiz3-wlan-backport/tree/29b6faf6b08a2b62097e509eb0fa62720ab48996/package/luci/luci-app-opiz3-status).
All A5E readings and allowed settings are discovered live; no H616/H618
operating points, governors, thresholds, Wi-Fi fields, or boot policy
are imported.

Host test with OpenWrt's native host `jshn` (no real sysfs writes):

```sh
python3 tests/test-rpc.py /path/to/host/share/libubox/jshn.sh /path/to/host/bin
```
