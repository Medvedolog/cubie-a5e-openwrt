# SPDX-License-Identifier: GPL-2.0-only
include $(TOPDIR)/rules.mk

PKG_NAME:=a5e-nvme-installer
PKG_VERSION:=1.0
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/a5e-nvme-installer
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Manual Cubie A5E offline NVMe staging installer
  DEPENDS:=+parted +e2fsprogs +resize2fs
  PKGARCH:=all
endef

define Package/a5e-nvme-installer/description
 Explicitly invoked NVMe installer for the experimental Cubie A5E
 microSD. It requires the offline payload and provides no auto-run hook.
endef

define Build/Compile
endef

define Package/a5e-nvme-installer/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) ./files/a5e-install-nvme $(1)/usr/sbin/a5e-install-nvme
endef

$(eval $(call BuildPackage,a5e-nvme-installer))
