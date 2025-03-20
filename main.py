# main.py
import logging
import asyncio
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.cdn.v20180606 import cdn_client, models

from astrbot.api.star import register, Star, Context
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger

@register(
    "simplecdn",
    "eebk", 
    "腾讯云CDN管理插件",
    "1.1.0"
)
class SimpleCdnPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._manager = None
        self._load_config(context._config)

    def _load_config(self, config):
        """安全加载配置"""
        required_config = {
            'secret_id': config.get("secret_id", ""),
            'secret_key': config.get("secret_key", ""),
            'region': config.get("region", "ap-singapore"),
            'zone_id': config.get("zone_id", "")
        }

        # 配置完整性校验
        if not all(required_config.values()):
            missing = [k for k, v in required_config.items() if not v]
            logger.error(f"配置缺失关键参数: {', '.join(missing)}")
            return False

        try:
            self._manager = SimpleCDNManager(**required_config)
            logger.info("CDN管理器初始化成功")
            return True
        except Exception as e:
            logger.error(f"初始化失败: {str(e)}")
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
            if not self._manager:
                yield event.plain_result("❌ 插件未初始化，请检查配置")
                return

            if is_preheat:
                result = await self._manager.simple_preheat(urls)
                yield event.plain_result(f"🔥 已预热{result['count']}个URL (请求ID: {result['request_id']})")
            else:
                result = await self._manager.simple_purge(urls)
                yield event.plain_result(f"🔄 已刷新{result['count']}个URL (请求ID: {result['request_id']})")

        except Exception as e:
            logger.error(f"操作失败: {str(e)}")
            yield event.plain_result(f"❌ 操作失败: {str(e)}")

    async def terminate(self):
        """安全终止方法"""
        try:
            if hasattr(self, '_manager') and self._manager:
                logger.info("释放CDN管理器资源...")
                self._manager = None
            logger.info("插件已安全卸载")
        except Exception as e:
            logger.error(f"终止异常: {str(e)}")

class SimpleCDNManager:
    def __init__(self, secret_id, secret_key, region, zone_id):
        """初始化腾讯云客户端
        
        Args:
            secret_id (str): API密钥ID
            secret_key (str): API密钥KEY
            region (str): 区域代码 (如ap-singapore)
            zone_id (str): 站点ID (需包含zone-前缀)
        """
        self.cred = credential.Credential(secret_id, secret_key)
        self.region = region
        self.zone_id = zone_id

        # 配置HTTP客户端
        http_profile = HttpProfile(
            endpoint="cdn.tencentcloudapi.com",
            reqTimeout=30
        )
        client_profile = ClientProfile(httpProfile=http_profile)
        
        # 创建区域化客户端
        self.client = cdn_client.CdnClient(
            self.cred, 
            self.region, 
            client_profile
        )

    def _format_url(self, url):
        """统一格式化URL"""
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        return url.rstrip('/')

    async def simple_purge(self, urls):
        """执行URL刷新"""
        req = models.PurgeUrlsCacheRequest()
        req.Urls = [self._format_url(url) for url in urls]
        req.ZoneId = self.zone_id  # 绑定站点ID

        try:
            resp = self.client.PurgeUrlsCache(req)
            return {
                "count": len(urls),
                "request_id": resp.RequestId
            }
        except Exception as e:
            raise RuntimeError(f"刷新失败: {str(e)}")

    async def simple_preheat(self, urls):
        """执行URL预热"""
        req = models.PushUrlsCacheRequest()
        req.Urls = [self._format_url(url) for url in urls]
        req.ZoneId = self.zone_id  # 绑定站点ID

        try:
            resp = self.client.PushUrlsCache(req)
            return {
                "count": len(urls),
                "request_id": resp.RequestId
            }
        except Exception as e:
            raise RuntimeError(f"预热失败: {str(e)}")
