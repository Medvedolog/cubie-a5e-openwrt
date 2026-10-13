include $(TOPDIR)/rules.mk

PKG_NAME:=aic8800-recovery
PKG_VERSION:=1.0
PKG_RELEASE:=1
PKG_FLAGS:=nonshared

include $(INCLUDE_DIR)/package.mk

define Package/aic8800-recovery
  SECTION:=net
  CATEGORY:=Network
  TITLE:=Cubie A5E AIC8800 safe SDIO recovery
  DEPENDS:=+kmod-aic8800-sdio +uci +ubus
  PKGARCH:=all
endef

define Package/aic8800-recovery/description
  Recovery of the physical Cubie A5E AIC8800 SDIO controller, with a
  once-per-boot guarded recovery if firmware failed to expose a PHY.
endef

define Package/aic8800-recovery/conffiles
/etc/config/aic8800-recovery
endef

define Build/Compile
endef

define Package/aic8800-recovery/install
	$(INSTALL_DIR) $(1)/lib $(1)/usr/sbin $(1)/etc/init.d $(1)/etc/config
	$(INSTALL_DATA) $(TOPDIR)/../files/lib/aic8800.sh $(1)/lib/aic8800.sh
	$(INSTALL_BIN) $(TOPDIR)/../files/usr/sbin/aic8800-recover $(1)/usr/sbin/aic8800-recover
	$(INSTALL_BIN) ./files/aic8800-auto-recover $(1)/usr/sbin/aic8800-auto-recover
	$(INSTALL_BIN) ./files/aic8800-recovery.init $(1)/etc/init.d/aic8800-recovery
	$(INSTALL_CONF) ./files/aic8800-recovery.config $(1)/etc/config/aic8800-recovery
endef

$(eval $(call BuildPackage,aic8800-recovery))
