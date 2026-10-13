#!/bin/sh
# AIC8800D80 helpers for Radxa Cubie A5E. Sourced by aic8800-recover.
# Do not assume stable mmcN, phyN or radioN numbers.
AIC_CONTROLLER=4021000.mmc

aic_host() {
    local h dev
    for h in /sys/class/mmc_host/mmc*; do
        [ -d "$h" ] || continue
        dev=$(readlink -f "$h/device") || continue
        [ "$dev" = "/sys/devices/platform/soc/$AIC_CONTROLLER" ] || continue
        printf '%s\n' "$dev"
        return 0
    done
    return 1
}
aic_host_name() {
    local h dev
    for h in /sys/class/mmc_host/mmc*; do
        [ -d "$h" ] || continue
        dev=$(readlink -f "$h/device") || continue
        [ "$dev" = "/sys/devices/platform/soc/$AIC_CONTROLLER" ] || continue
        basename "$h"
        return 0
    done
    return 1
}
aic_phy() {
    local p dev
    for p in /sys/class/ieee80211/*; do
        [ -r "$p/macaddress" ] || continue
        dev=$(readlink -f "$p/device") || continue
        case "$dev" in
            */4021000.mmc/*) basename "$p"; return 0 ;;
        esac
    done
    return 1
}
aic_phy_mac() {
    local phy
    phy=$(aic_phy) || return 1
    cat "/sys/class/ieee80211/$phy/macaddress"
}
aic_sdio_present() {
    local dev path
    for dev in /sys/bus/sdio/devices/*; do
        [ -e "$dev" ] || continue
        path=$(readlink -f "$dev") || continue
        case "$path" in
            */4021000.mmc/*) return 0 ;;
        esac
    done
    return 1
}
aic_no_storage_on_host() {
    local blk path
    for blk in /sys/class/block/mmcblk*; do
        [ -e "$blk" ] || continue
        path=$(readlink -f "$blk/device") || continue
        case "$path" in
            */4021000.mmc/*)
                echo "refusing: storage $blk belongs to Wi-Fi controller" >&2
                return 1 ;;
        esac
    done
    return 0
}
# Match UCI radio by stable MAC or by the physical controller segment.
aic_radios() {
    local mac radio path rm
    mac=$(aic_phy_mac | tr A-F a-f)
    for radio in $(uci -q show wireless |
        sed -n 's/^wireless\.\(radio[0-9][0-9]*\)=wifi-device$/\1/p'); do
        path=$(uci -q get "wireless.$radio.path")
        rm=$(uci -q get "wireless.$radio.macaddr" | tr A-F a-f)
        case "$path" in
            *4021000.mmc*)
                printf '%s\n' "$radio"
                continue ;;
        esac
        if [ -n "$mac" ] && [ "$mac" = "$rm" ]; then
            printf '%s\n' "$radio"
        fi
    done
}
aic_preflight() {
    local host
    host=$(aic_host) || {
        echo "Wi-Fi MMC host $AIC_CONTROLLER not found" >&2
        return 1
    }
    [ -e "$host/of_node/mmc-pwrseq" ] || {
        echo "Wi-Fi host lacks DT mmc-pwrseq; refusing reset" >&2
        return 1
    }
    aic_no_storage_on_host || return 1
    [ -L "$host/driver" ] || {
        echo "Wi-Fi MMC host not bound to a driver" >&2
        return 1
    }
    return 0
}
