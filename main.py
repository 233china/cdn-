@register(
    "simplecdn",
    "YourName", 
    "腾讯云CDN管理插件",
    "1.1.0"
)
class SimpleCdnPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._manager = None  # 使用私有变量
        self._load_config(context.config)

    def _load_config(self, config):
        """安全加载配置"""
        self.secret_id = config.get("secret_id") or ""
        self.secret_key = config.get("secret_key") or ""
        
        # 添加配置验证
        if not all([self.secret_id, self.secret_key]):
            logger.error("CDN插件配置不完整，请检查secret_id和secret_key")
            return False
        
        try:
            self._manager = SimpleCDNManager(self.secret_id, self.secret_key)
            return True
        except Exception as e:
            logger.error(f"CDN管理器初始化失败: {str(e)}")
            return False

    async def on_config_update(self, new_config):
        """配置更新时的热重载"""
        logger.info("检测到配置更新，重新加载CDN管理器...")
        success = self._load_config(new_config)
        if success:
            logger.info("CDN管理器重载成功")
        else:
            logger.error("CDN管理器重载失败，请检查新配置")

    @filter.command("cdn")
    async def handle_cdn_command(self, event: AstrMessageEvent):
        '''CDN缓存刷新/预热'''
        # 添加管理器状态检查
        if self._manager is None:
            yield event.plain_result("❌ 插件未正确初始化，请检查配置")
            return
            
        # 原有业务逻辑保持不变...

    async def terminate(self):
        """安全终止方法"""
        if self._manager is not None:
            logger.info("正在清理CDN管理器资源...")
            self._manager = None
        logger.info("CDN插件已安全卸载")
