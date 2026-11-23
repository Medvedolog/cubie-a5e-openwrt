# SPDX-License-Identifier: GPL-2.0-only
include $(TOPDIR)/rules.mk

PKG_NAME:=aic8800-recovery
PKG_VERSION:=1.0
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/aic8800-recovery
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Manual AIC8800 SDIO recovery for Radxa Cubie A5E
  DEPENDS:=+kmod-aic8800-sdio +wifi-scripts
  PKGARCH:=all
endef

define Package/aic8800-recovery/description
 Manual preflight and bounded recovery for the built-in AIC8800 SDIO Wi-Fi.
 Does not install a daemon, a hotplug hook, or an automatic reset.
endef

define Build/Compile
endef

define Package/aic8800-recovery/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/lib
	$(INSTALL_BIN) ./files/aic8800-recover $(1)/usr/sbin/aic8800-recover
	$(INSTALL_DATA) ./files/aic8800.sh $(1)/lib/aic8800.sh
endef

$(eval $(call BuildPackage,aic8800-recovery))
