#!/usr/bin/env python3
"""Verify the exact BSP-common big-cluster OPPs in an extracted A5E FIT DTB."""
import argparse
from pathlib import Path
import struct


class FdtError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise FdtError(message)


def parse(blob):
    require(len(blob) >= 40, "truncated header")
    magic, total, off, strings, _, version, _, _, ssize, nsize = struct.unpack_from(">10I", blob)
    require(magic == 0xD00DFEED and version >= 17 and total <= len(blob), "invalid FDT header")
    require(40 <= off < off + nsize <= total and 40 <= strings <= strings + ssize <= total,
            "invalid FDT structure/string bounds")
    tree = blob[off:off + nsize]
    string_table = blob[strings:strings + ssize]
    nodes, path = {}, []

    def padded(index):
        return (index + 3) & ~3

    i = 0
    while i + 4 <= nsize:
        token, = struct.unpack_from(">I", tree, i)
        i += 4
        if token == 1:  # FDT_BEGIN_NODE
            end = tree.find(b"\x00", i)
            require(end >= i, "unterminated node name")
            name = tree[i:end].decode("ascii")
            path.append(name)
            full = "/".join(path) or "/"
            require(full not in nodes, f"duplicate node {full}")
            nodes[full] = {}
            i = padded(end + 1)
        elif token == 2:  # FDT_END_NODE
            require(bool(path), "unbalanced FDT node")
            path.pop()
        elif token == 3:  # FDT_PROP
            require(bool(path) and i + 8 <= nsize, "invalid property header")
            size, nameoff = struct.unpack_from(">2I", tree, i)
            i += 8
            end = string_table.find(b"\x00", nameoff)
            require(end >= nameoff and i + size <= nsize, "invalid property data bounds")
            prop = string_table[nameoff:end].decode("ascii")
            node = nodes["/".join(path) or "/"]
            require(prop not in node, f"duplicate property {prop}")
            node[prop] = tree[i:i + size]
            i = padded(i + size)
        elif token == 4:  # FDT_NOP
            continue
        elif token == 9:  # FDT_END
            require(not path and "/" in nodes, "malformed FDT end")
            return nodes
        else:
            raise FdtError(f"unknown FDT token {token}")
    raise FdtError("missing FDT end token")


def cells(value, count=1):
    require(value is not None and len(value) == 4 * count, f"expected {count} DT cells")
    return struct.unpack(f">{count}I", value)


def verify(nodes):
    require(b"radxa,cubie-a5e" in nodes["/"]["compatible"].split(b"\x00"), "Cubie A5E DTB only")
    table_path = "/opp-table-big"
    table = nodes[table_path]
    require(table.get("compatible") == b"operating-points-v2\x00", "wrong OPP binding")
    require(table.get("opp-shared") == b"", "big OPP table must be shared by all four CPUs")
    table_handle, = cells(table.get("phandle"))
    pmic_path = "/soc/i2c@7081400/pmic@36"
    pmic = nodes[pmic_path]
    require(b"x-powers,axp323" in pmic["compatible"].split(b"\x00"), "big-cluster PMIC is not AXP323")
    rail = nodes[pmic_path + "/regulators/dcdc1"]
    require(rail.get("regulator-name") == b"vdd-cpub\x00", "incorrect big-cluster PMIC rail")
    require(cells(rail.get("regulator-min-microvolt")) == (900000,), "unexpected minimum rail voltage")
    require(cells(rail.get("regulator-max-microvolt")) == (1160000,), "unexpected maximum rail voltage")
    require(rail.get("regulator-always-on") == b"", "big rail must remain always-on")
    supply, = cells(rail.get("phandle"))

    for i in range(8):
        cpu = nodes[f"/cpus/cpu@{i << 8:x}"]
        if i < 4:
            require(not ({"clocks", "operating-points", "operating-points-v2", "cpu-supply"} & cpu.keys()),
                    f"little CPU{i} must stay unmanaged")
        else:
            require(cells(cpu.get("operating-points-v2")) == (table_handle,),
                    f"big CPU{i} must share the candidate table")
            require(cells(cpu.get("cpu-supply")) == (supply,),
                    f"big CPU{i} must use the isolated AXP323 DCDC1 rail")

    points = {}
    for name, opp in nodes.items():
        if not name.startswith(table_path + "/"):
            continue
        hz_hi, hz_lo = cells(opp.get("opp-hz"), 2)
        frequency = (hz_hi << 32) | hz_lo
        voltage, = cells(opp.get("opp-microvolt"))
        require(frequency not in points, f"duplicate OPP {frequency}")
        require("opp-suspend" not in opp and "opp-supported-hw" not in opp,
                f"unexpected OPP exception at {frequency}")
        require(cells(opp.get("clock-latency-ns")) == (244144,), f"unexpected latency at {frequency}")
        points[frequency] = voltage
    require(points == {408000000: 900000, 1488000000: 1000000, 1584000000: 1050000},
            f"unexpected big-cluster OPP set: {points}")

    cpu4 = nodes["/cpus/cpu@400"]
    cpu4_handle, = cells(cpu4.get("phandle"))
    require(cells(cpu4.get("#cooling-cells")) == (2,), "big CPU must expose cooling cells")
    for cpu_num in (0, 4):
        zone = f"/thermal-zones/cpu{cpu_num}-thermal"
        cells(nodes[zone].get("thermal-sensors"), 2)
        critical = nodes[zone + "/trips/cpu-trip-2"]
        require(critical.get("type") == b"critical\x00" and
                cells(critical.get("temperature")) == (110000,), "stock critical trip must be retained")
        for threshold, state in ((85000, 1), (90000, 2)):
            suffix = str(threshold // 1000)
            trip = nodes[zone + "/trips/cpu-trip-bench" + suffix]
            mapping = nodes[zone + "/cooling-maps/map-bench" + suffix]
            require(trip.get("type") == b"passive\x00" and
                    cells(trip.get("temperature")) == (threshold,) and
                    cells(trip.get("hysteresis")) == (2000,),
                    f"unexpected passive trip {cpu_num}/{threshold}")
            require(cells(mapping.get("trip")) == cells(trip.get("phandle")) and
                    cells(mapping.get("cooling-device"), 3) == (cpu4_handle, state, 0xffffffff),
                    f"wrong big cooling floor {cpu_num}/{threshold}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dtb", type=Path, help="A5E board DTB extracted from its FIT")
    args = parser.parse_args()
    try:
        verify(parse(args.dtb.read_bytes()))
    except (OSError, KeyError, ValueError, struct.error) as error:
        parser.exit(1, f"A5E DVFS board check failed: {error}\n")
    print("PASS A5E DTB: three BSP-common big OPPs, AXP323 DCDC1, two-sensor big cooling floors, no little CPU policy")


if __name__ == "__main__":
    main()
