#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Apply to a copy of the pinned Linux 6.18.64 files and exercise C gates."""
import re
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

stage = Path(__file__).resolve().parents[1]
patch = next((stage / "target/linux/sunxi/patches-6.18").glob("954-*.patch"))
source = Path(sys.argv[1]).resolve()


def function(src, signature):
    """Extract one unmodified C function, retaining its signature."""
    start = src.index(signature)
    end = src.index("\n}", start) + 2
    return src[start:end]


with TemporaryDirectory() as temp:
    temp = Path(temp)
    d = temp / "drivers/cpufreq"
    d.mkdir(parents=True)
    for name in ("cpufreq-dt-platdev.c", "cpufreq-dt.c", "cpufreq-dt.h"):
        shutil.copy2(source / "drivers/cpufreq" / name, d / name)
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=temp, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=temp, check=True)
    plat = (d / "cpufreq-dt-platdev.c").read_text()
    driver = (d / "cpufreq-dt.c").read_text()
    assert 'early_param("a5e_dvfs", a5e_dvfs_setup);' in plat
    probe = function(driver, "static int dt_cpufreq_probe")
    assert probe.index("!data || !data->a5e_dvfs_bench") < probe.index("for_each_present_cpu")
    assert 'if (!of_property_present(np, "operating-points-v2"))\n\t\t\t\tcontinue;' in probe
    assert "CONFIG_CPU_FREQ_DEFAULT_GOV_POWERSAVE" in probe
    early = function(driver, "static int dt_cpufreq_early_init")
    assert early.index("a5e_dvfs_prepare_boot_opp(") < early.index("list_add(")
    assert "if (ret != -ENOENT || a5e_bench)" in early
    assert "CPUFREQ_NEED_INITIAL_FREQ_CHECK" in driver
    assert "a5e_dvfs_validate_topology()" in probe
    assert "clk_set_rate(" in driver
    assert ".config_clks = a5e_dvfs_config_opp_clock" in early
    assert "dev_pm_opp_set_config(cpu_dev, &a5e_opp_config)" in early
    assert "regulator_set_voltage(" not in driver
    assert re.search(r"\ba5e_dvfs_check_boot_opp\(priv, cpu_clk\)", function(driver, "static int cpufreq_init"))
    main = r'''
#include <assert.h>
#include <stdbool.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <stddef.h>
#define __init
#define __free(x)
#define A5E_DVFS_COMPATIBLE "radxa,cubie-a5e"
#define PTR_ERR_OR_ZERO(p) (p ? 0 : -ENODEV)
#define CPUFREQ_TABLE_END UINT32_MAX
#define CPUFREQ_ENTRY_INVALID (UINT32_MAX - 1)
#define cpufreq_for_each_valid_entry(pos, table) \
    for (pos = table; pos->frequency != CPUFREQ_TABLE_END; pos++) \
        if (pos->frequency == CPUFREQ_ENTRY_INVALID) continue; else
struct device { unsigned unused; };
struct device_node { const char *compatible; };
struct of_device_id { const void *data; };
struct cpufreq_dt_platform_data { bool a5e_dvfs_bench; };
struct clk {
    unsigned long hz;
    unsigned long round_to;
    int fail_first_set;
    int voltage_after, ignore_set;
    unsigned int sets;
};
struct regulator { int voltage; unsigned int gets, puts; };
struct opp_table { unsigned unused; };
struct dev_pm_opp { unsigned long frequency, voltage; };
static struct clk *fixture_clock;
static struct clk *clk_get(struct device *dev, const char *connection) {
    (void)dev;
    assert(connection == NULL);
    return fixture_clock;
}
static void clk_put(struct clk *clk) { assert(clk == fixture_clock); }
static unsigned long dev_pm_opp_get_freq(struct dev_pm_opp *opp) { return opp->frequency; }
static unsigned long dev_pm_opp_get_voltage(struct dev_pm_opp *opp) { return opp->voltage; }

static struct regulator fixture_rail;
#define IS_ERR(p) (!(p))
#define PTR_ERR(p) ((p) ? 0 : -ENODEV)

struct cpufreq_frequency_table { unsigned int frequency; };
struct private_data {
    struct cpufreq_frequency_table *freq_table;
    struct device *cpu_dev;
};
static bool is_allowlisted, is_blocklisted, cpu0_opp, a5e_dvfs_enabled, called, special;
static struct device_node root = { A5E_DVFS_COMPATIBLE };
static struct of_device_id match = { NULL };
static const struct of_device_id *allowlist = &match;
static const struct of_device_id *blocklist;
static const struct cpufreq_dt_platform_data a5e_dvfs_data = { true };
static struct device_node *of_find_node_by_path(const char *p) {
    assert(!strcmp(p, "/")); return &root;
}
static int of_device_is_compatible(struct device_node *p, const char *compatible) {
    return !strcmp(p->compatible, compatible);
}
static const struct of_device_id *of_match_node(const struct of_device_id *tbl,
                                                struct device_node *p) {
    assert(p == &root);
    return (tbl == allowlist ? is_allowlisted : is_blocklisted) ? &match : NULL;
}
static bool cpu0_node_has_opp_v2_prop(void) { return cpu0_opp; }
static void *platform_device_register_data(void *parent, const char *name, int id,
                                           const void *data, size_t len) {
    const struct cpufreq_dt_platform_data *cfg = data;
    assert(!parent && !strcmp(name, "cpufreq-dt") && id == -1);
    assert(len == sizeof(*cfg));
    called = true;
    special = cfg && cfg->a5e_dvfs_bench;
    return &root;
}
static unsigned long clk_get_rate(struct clk *clk) { return clk->hz; }
static unsigned int warned, admitted;
static long clk_round_rate(struct clk *clk, unsigned long hz) {
    return clk->round_to ? (long)clk->round_to : (long)hz;
}
static int clk_set_rate(struct clk *clk, unsigned long hz) {
    clk->sets++;
    if (!clk->ignore_set) clk->hz = hz;
    if (clk->sets == 1 && clk->voltage_after)
        fixture_rail.voltage = clk->voltage_after;
    return clk->sets == 1 ? clk->fail_first_set : 0;
}
static struct regulator *regulator_get_optional(struct device *dev, const char *name) {
    (void)dev;
    assert(!strcmp(name, "cpu"));
    fixture_rail.gets++;
    return &fixture_rail;
}
static void regulator_put(struct regulator *rail) { rail->puts++; }
static int regulator_get_voltage(struct regulator *rail) { return rail->voltage; }
static int dev_err_probe(struct device *dev, int err, const char *reason) {
    (void)dev;
    (void)reason;
    return err;
}
#define dev_info(device, format, rate) do { (void)(device); (void)(format); (void)(rate); admitted++; } while (0)
#define dev_err(device, format, ...) do { (void)(device); (void)(format); } while (0)
#define dev_warn(device, format, ...) do { (void)(device); (void)(format); warned++; } while (0)
'''
    main += "\n" + function(plat, "static int __init a5e_dvfs_setup")
    main += "\n" + function(plat, "static int __init cpufreq_dt_platdev_init")
    main += "\n" + function(driver, "static bool a5e_dvfs_has_opp")
    main += "\n" + function(driver, "static int a5e_dvfs_check_boot_opp")
    main += "\n" + "\n".join(re.findall(r"^#define A5E_.*$", driver, re.M)) + "\n"
    main += function(driver, "static bool a5e_dvfs_rail_ok")
    main += "\n" + function(driver, "static int a5e_dvfs_config_opp_clock")
    main += "\n" + function(driver, "static int a5e_dvfs_prepare_boot_opp")
    main += r'''
int main(void) {
    struct cpufreq_frequency_table table[] = {
        { 408000 }, { CPUFREQ_ENTRY_INVALID }, { 1488000 },
        { 1584000 }, { CPUFREQ_TABLE_END },
    };
    struct private_data cpu = { table, NULL };
    struct clk running = { .hz = 792000000 };
    const char *invalid[] = { NULL, "", "0", "01", "true", "1!", " 1" };

    assert(cpufreq_dt_platdev_init() == -ENODEV && !called);
    cpu0_opp = true;
    for (size_t i = 0; i < sizeof(invalid)/sizeof(invalid[0]); i++) {
        assert(a5e_dvfs_setup((char *)invalid[i]) == 0);
        assert(cpufreq_dt_platdev_init() == -ENODEV && !called);
    }
    cpu0_opp = false;
    assert(a5e_dvfs_setup("1") == 0);
    assert(cpufreq_dt_platdev_init() == 0 && called && special);

    called = false;
    root.compatible = "allwinner,sun55i-a527";
    assert(cpufreq_dt_platdev_init() == -ENODEV && !called);
    cpu0_opp = true;
    is_blocklisted = true;
    assert(cpufreq_dt_platdev_init() == -ENODEV && !called);
    is_blocklisted = false;
    assert(cpufreq_dt_platdev_init() == 0 && called && !special);
    called = false;
    cpu0_opp = false;
    is_allowlisted = true;
    assert(cpufreq_dt_platdev_init() == 0 && called && !special);

    assert(a5e_dvfs_check_boot_opp(&cpu, &running) == -ENODEV);
    assert(warned == 1 && running.hz == 792000000);
    running.hz = 0;
    assert(a5e_dvfs_check_boot_opp(&cpu, &running) == -ENODEV);
    assert(warned == 2);
    running.hz = 408000000;
    assert(a5e_dvfs_check_boot_opp(&cpu, &running) == 0);
    running.hz = 1488000000;
    assert(a5e_dvfs_check_boot_opp(&cpu, &running) == 0);
    running.hz = 1584000000;
    assert(a5e_dvfs_check_boot_opp(&cpu, &running) == 0);
    assert(warned == 2);

    running = (struct clk){ .hz = 792000000 };
    fixture_rail.voltage = 1000000;
    assert(a5e_dvfs_prepare_boot_opp(&cpu, &running) == -ENODEV);
    assert(running.sets == 0 && fixture_rail.gets == 0);
    running.hz = 768000000;
    running.round_to = 600000000;
    assert(a5e_dvfs_prepare_boot_opp(&cpu, &running) == -ENODEV);
    assert(running.sets == 0 && fixture_rail.gets == 0);
    running.round_to = 0;
    fixture_rail.voltage = 899999;
    assert(a5e_dvfs_prepare_boot_opp(&cpu, &running) == -ENODEV);
    assert(running.sets == 0 && fixture_rail.gets == 1 && fixture_rail.puts == 1);
    fixture_rail.voltage = 1050001;
    assert(a5e_dvfs_prepare_boot_opp(&cpu, &running) == -ENODEV);
    fixture_rail.voltage = 950000;
    assert(a5e_dvfs_prepare_boot_opp(&cpu, &running) == 0);
    assert(running.sets == 1 && running.hz == 408000000 && admitted == 1);
    running = (struct clk){ .hz = 768000000, .fail_first_set = -EIO };
    assert(a5e_dvfs_prepare_boot_opp(&cpu, &running) == -ENODEV);
    assert(running.sets == 2 && running.hz == 768000000 && admitted == 1);
    running = (struct clk){ .hz = 768000000, .voltage_after = 900000 };
    assert(a5e_dvfs_prepare_boot_opp(&cpu, &running) == -ENODEV);
    assert(running.sets == 1 && running.hz == 408000000 && admitted == 1);
    fixture_clock = &running;
    struct dev_pm_opp low = { 408000000, 900000 };
    struct dev_pm_opp high = { 1488000000, 1000000 };
    unsigned long rounded = 840000000;
    running = (struct clk){ .hz = 408000000 };
    fixture_rail.voltage = 900000;
    assert(a5e_dvfs_config_opp_clock(NULL, NULL, NULL, &high, NULL, true) == -EIO);
    assert(running.sets == 0); /* stale high OPP must not upclock on a low rail */
    assert(a5e_dvfs_config_opp_clock(NULL, NULL, NULL, &high, &rounded, true) == -EINVAL);
    fixture_rail.voltage = 1000000;
    assert(a5e_dvfs_config_opp_clock(NULL, NULL, NULL, &high, NULL, false) == 0);
    assert(running.hz == 1488000000 && running.sets == 1);
    running.ignore_set = true;
    assert(a5e_dvfs_config_opp_clock(NULL, NULL, NULL, &low, NULL, true) == -EIO);
    assert(running.hz == 1488000000 && fixture_rail.voltage == 1000000);
    running.ignore_set = false;
    assert(a5e_dvfs_config_opp_clock(NULL, NULL, NULL, &low, NULL, true) == 0);
    assert(running.hz == 408000000 && fixture_rail.voltage == 1000000);
    assert(fixture_rail.gets == fixture_rail.puts);
    return 0;
}
'''
    (temp / "test.c").write_text(main)
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter", str(temp / "test.c"),
                    "-o", str(temp / "test")], check=True)
    subprocess.run([str(temp / "test")], check=True)
print("PASS: exact patch application, default-off and board/argument gates, ordinary machine behavior, rail/rounding/clock guarded opt-in and fail-closed rollback")
