#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the packaged executable using fixture sysfs and OpenWrt jshn.

Usage: test-rpc.py /path/to/jshn.sh /path/to/host/bin
The host bin directory must contain the matching executable jshn.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

root = Path(__file__).resolve().parents[1]
js = root / "root/usr/libexec/rpcd/luci.a5e-board"
inputs = Path(sys.argv[1]).resolve()
bindir = Path(sys.argv[2]).resolve()
assert inputs.is_file(), inputs
assert (bindir / "jshn").is_file(), bindir
env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"}
with TemporaryDirectory() as work:
    work = Path(work)
    fixture = work / "sys"
    lock = work / "lock"
    test = work / "rpc"
    raw = js.read_text()
    text = raw.replace(". /usr/share/libubox/jshn.sh", f'. "{inputs}"')
    text = text.replace("SYS=/sys\n", f'SYS="{fixture}"\n')
    text = text.replace("LOCK=/var/lock/luci-a5e-board\n", f'LOCK="{lock}"\n')
    assert text != raw
    test.write_text(text)

    def call(method, payload=None, raw_payload=None, executable=test):
        args = ["/bin/bash", str(executable), "list"] if method == "list" else [
            "/bin/bash", str(executable), "call", method]
        if raw_payload is None:
            raw_payload = json.dumps(payload or {})
        p = subprocess.run(args, input=raw_payload, check=False, text=True,
                           env=env, capture_output=True)
        assert not p.stderr, p.stderr
        assert p.returncode == 0, p.stdout
        return json.loads(p.stdout)

    def write(path, value):
        p = fixture / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(value) + "\n")
        return p

    assert set(call("list")) == {"status", "set_governor", "set_limits"}
    assert call("status") == {"temperatures": [], "policies": []}
    assert call("set_governor", {"policy": "policy0", "governor": "ondemand"}) == {
        "ok": False, "error": "unavailable"}
    assert call("set_limits", raw_payload="{")["error"] == "invalid"
    write("class/thermal/thermal_zone0/type", "cpu0-thermal")
    write("class/thermal/thermal_zone0/temp", 42750)
    write("class/thermal/thermal_zone1/type", 'gpu<"test">')
    write("class/thermal/thermal_zone1/temp", -1200)
    write("class/thermal/thermal_zone2/temp", "invalid")
    write("class/hwmon/hwmon0/name", "nvme")
    write("class/hwmon/hwmon0/temp1_label", "Composite")
    write("class/hwmon/hwmon0/temp1_input", 31500)
    write("class/hwmon/hwmon0/temp23_input_bad", 10000)
    write("class/thermal/thermal_zone0/hwmon99/temp1_input", 42750)
    (fixture / "class/hwmon/hwmon99").symlink_to(
        fixture / "class/thermal/thermal_zone0/hwmon99")

    control = "devices/system/cpu/cpufreq/"
    for n in ("policy0", "policy4"):
        for k, v in {
            "related_cpus": "0 1 2 3" if n == "policy0" else "4 5 6 7",
            "scaling_cur_freq": 600000, "scaling_governor": "performance",
            "scaling_available_governors": "performance ondemand",
            "scaling_min_freq": 600000, "scaling_max_freq": 1200000,
            "cpuinfo_min_freq": 200000, "cpuinfo_max_freq": 2000000,
        }.items():
            write(f"{control}{n}/{k}", v)
    opts = write(control + "policy0/scaling_available_frequencies",
                 "200000 400000 600000 1200000 1800000 2000000")
    status = call("status")
    assert [(r["label"], r["millidegrees"]) for r in status["temperatures"]] == [
        ("cpu0-thermal", 42750), ('gpu<"test">', -1200), ("Composite", 31500)], status
    assert [p["id"] for p in status["policies"]] == ["policy0", "policy4"], status
    assert status["policies"][1]["frequencies"] == [], status
    assert call("set_governor", {"policy": "policy4", "governor": "ondemand"}) == {"ok": True}
    assert call("set_governor", {"policy": "policy4", "governor": "performance;touch /tmp/no"})["error"] == "invalid"
    assert call("set_governor", {"policy": "policy4/../policy0", "governor": "ondemand"})["error"] == "invalid"
    assert call("set_governor", {"policy": "policy4", "governor": "powersave"})["error"] == "unavailable"
    assert call("set_limits", {"policy": "policy4", "min": 400000, "max": 600000})["error"] == "unavailable"
    assert call("set_limits", {"policy": "policy0", "min": "400000", "max": 600000})["error"] == "invalid"
    assert call("set_limits", {"policy": "policy0", "min": 400000, "max": 200000})["error"] == "invalid"
    assert call("set_limits", {"policy": "policy0", "min": 399999, "max": 600000})["error"] == "unavailable"
    lock.mkdir()
    assert call("set_limits", {"policy": "policy0", "min": 200000, "max": 400000})["error"] == "busy"
    lock.rmdir()
    assert call("set_limits", {"policy": "policy0", "min": 200000, "max": 400000}) == {"ok": True}
    assert call("set_limits", {"policy": "policy0", "min": 1800000, "max": 2000000}) == {"ok": True}
    s = call("status")["policies"]
    assert (s[0]["min"], s[0]["max"], s[1]["min"], s[1]["governor"]) == (
        1800000, 2000000, 600000, "ondemand"), s

    # Replace only sysfs writes with a fixture that enforces kernel ordering
    # and rejects the requested ceiling after the new floor was accepted.
    replacement = """write_value() {
        base=${1%/*}
        curmin=$(readval "$base/scaling_min_freq")
        curmax=$(readval "$base/scaling_max_freq")
        case "$1" in
            */scaling_min_freq) [ "$2" -le "$curmax" ] || return 1;;
            */scaling_max_freq)
                [ "$2" -ge "$curmin" ] && [ "$2" != 400000 ] || return 1;;
        esac
        printf '%s\\n' "$2" >"$1"
    }"""
    altered, n = re.subn(r"^write_value\(\) \{.*?^\}", lambda _: replacement,
                         text, flags=re.M | re.S)
    assert n == 1
    hooked = work / "rpc-with-failure"
    hooked.write_text(altered)
    assert call("set_limits", {"policy": "policy0", "min": 200000, "max": 400000},
                executable=hooked)["error"] == "rejected"
    s = call("status")["policies"][0]
    assert (s["min"], s["max"]) == (1800000, 2000000), s
    opts.unlink()
    assert call("status")["policies"][0]["frequencies"] == []
    assert not lock.exists()
    a = json.loads((root / "root/usr/share/rpcd/acl.d/luci-app-a5e-board.json").read_text())
    assert a["luci-app-a5e-board"]["read"] == {"ubus": {"luci.a5e-board": ["status"]}}
    assert a["luci-app-a5e-board"]["write"] == {"ubus": {"luci.a5e-board": ["set_governor", "set_limits"]}}
print("PASS: discovery, two CPU policies, no-fallback UI data, ACL, valid and rejected writes, rollback")
