# main.py
import logging
import asyncio
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.cdn.v20180606 import cdn_client, models

from astrbot.api.star import register, Star, Context
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger  # 必须导入logger

@register(
    "simplecdn",
    "eebk", 
    "腾讯云CDN管理插件",
    "1.1.0"  # 必须与metadata.yaml的version字段去掉v后的版本一致
)
class SimpleCdnPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._manager = None
        self._load_config(context._config)  # 使用_context

    def _load_config(self, config):
        """安全加载配置"""
        self.secret_id = config.get("secret_id", "")
        self.secret_key = config.get("secret_key", "")
        
        if not all([self.secret_id, self.secret_key]):
            logger.error("CDN插件配置不完整，请检查secret_id和secret_key")
            return False
        
        try:
            self._manager = SimpleCDNManager(self.secret_id, self.secret_key)
            logger.info("CDN管理器初始化成功")
            return True
        except Exception as e:
            logger.error(f"CDN管理器初始化失败: {str(e)}")
            return False

    async def on_config_update(self, new_config):
        """配置热重载"""
        logger.info("检测到配置更新，重新加载管理器...")
        if self._load_config(new_config):
            logger.info("配置重载成功")
        else:
            logger.error("配置重载失败")

    @filter.command("cdn")
    async def handle_cdn_command(self, event: AstrMessageEvent):
        '''CDN缓存刷新/预热'''
        args = event.message_str.split()[1:]
        is_preheat = "--preheat" in args
        urls = [arg for arg in args if not arg.startswith("--")]
        
        if not urls:
            yield event.plain_result("❌ 请提供要刷新的URL")
            return
            
        try:
            if self._manager is None:
                yield event.plain_result("❌ 插件未初始化，请检查配置")
                return

            if is_preheat:
                count = await self._manager.simple_preheat(urls)
                yield event.plain_result(f"🔥 已提交{count}个预热请求")
            else:
                count = await self._manager.simple_purge(urls)
                yield event.plain_result(f"🔄 已提交{count}个刷新请求")
                
        except Exception as e:
            logger.error(f"操作失败: {str(e)}")
            yield event.plain_result(f"❌ 操作失败: {str(e)}")

    async def terminate(self):
        """安全终止方法"""
        try:
            if hasattr(self, '_manager') and self._manager is not None:
                logger.info("正在释放CDN管理器资源...")
                self._manager = None
            logger.info("插件已安全卸载")
        except Exception as e:
            logger.error(f"终止异常: {str(e)}")

class SimpleCDNManager:
    def __init__(self, secret_id, secret_key):
        cred = credential.Credential(secret_id, secret_key)
        http_profile = HttpProfile(endpoint="cdn.tencentcloudapi.com")
        client_profile = ClientProfile(httpProfile=http_profile)
        self.client = cdn_client.CdnClient(cred, "", client_profile)

    def _format_url(self, url):
        """统一格式化URL"""
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        return url.rstrip('/')

    async def simple_purge(self, urls):
        """执行刷新操作"""
        paths = []
        files = []
        
        for raw_url in urls:
            formatted = self._format_url(raw_url)
            if raw_url.endswith('/'):
                paths.append(formatted + '/')
            else:
                files.append(formatted)

        if files:
            req = models.PurgeUrlsCacheRequest()
            req.Urls = files
            self.client.PurgeUrlsCache(req)
        
        if paths:
            req = models.PurgePathCacheRequest()
            req.Paths = paths
            req.FlushType = "delete"
            self.client.PurgePathCache(req)

        return len(files) + len(paths)

    async def simple_preheat(self, urls):
        """执行预热操作"""
        req = models.PushUrlsCacheRequest()
        req.Urls = [self._format_url(url) for url in urls]
        self.client.PushUrlsCache(req)
        return len(urls)
