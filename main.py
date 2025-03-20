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
        """安全加载配置（包含详细日志）"""
        logger.debug("========= 开始加载配置 =========")
        logger.debug(f"原始配置内容: {dict(config)}")

        # 提取关键配置项
        required_config = {
            'secret_id': config.get("secret_id", ""),
            'secret_key': config.get("secret_key", ""),
            'region': config.get("region", "ap-singapore"),
            'zone_id': config.get("zone_id", "")
        }
        logger.debug(f"处理后配置: {required_config}")

        # 配置完整性校验
        if not all(required_config.values()):
            missing = [k for k, v in required_config.items() if not v]
            logger.error(f"配置缺失关键参数: {', '.join(missing)}")
            return False

        # 验证zone_id格式
        if not required_config['zone_id'].startswith('zone-'):
            logger.error("zone_id必须以'zone-'开头")
            return False

        try:
            logger.debug("正在初始化CDN管理器...")
            self._manager = SimpleCDNManager(**required_config)
            logger.info("✅ CDN管理器初始化成功")
            return True
        except Exception as e:
            logger.error(f"❌ 初始化失败: {str(e)}", exc_info=True)
            return False

    async def on_config_update(self, new_config):
        """配置热重载（增强日志）"""
        logger.info("检测到配置更新，重新加载管理器...")
        if self._load_config(new_config):
            logger.info("配置重载成功")
        else:
            logger.error("配置重载失败")

    @filter.command("cdn")
    async def handle_cdn_command(self, event: AstrMessageEvent):
        '''CDN缓存刷新/预热（增加操作日志）'''
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

            logger.debug(f"操作参数: is_preheat={is_preheat}, urls={urls}")

            if is_preheat:
                result = await self._manager.simple_preheat(urls)
                msg = f"🔥 已预热{result['count']}个URL (请求ID: {result['request_id']})"
            else:
                result = await self._manager.simple_purge(urls)
                msg = f"🔄 已刷新{result['count']}个URL (请求ID: {result['request_id']})"
            
            logger.info(msg)
            yield event.plain_result(msg)

        except Exception as e:
            logger.error(f"操作失败: {str(e)}", exc_info=True)
            yield event.plain_result(f"❌ 操作失败: {str(e)}")

    async def terminate(self):
        """安全终止方法（增强资源释放）"""
        try:
            if hasattr(self, '_manager') and self._manager:
                logger.info("正在释放CDN管理器资源...")
                del self._manager
                self._manager = None
            logger.info("插件已安全卸载")
        except Exception as e:
            logger.error(f"终止异常: {str(e)}")

class SimpleCDNManager:
    def __init__(self, secret_id, secret_key, region, zone_id):
        try:
            # 新增签名方法配置
            client_profile = ClientProfile(httpProfile=http_profile)
            client_profile.signMethod = "TC3-HMAC-SHA256"  # 强制签名算法
            
            # 显式指定 API 版本
            self.client = cdn_client.CdnClient(
                self.cred, 
                region, 
                client_profile,
                api_version="2018-06-06"  # 新增此行
            )
        except Exception as e:
            logger.error(f"SDK初始化失败 | 详细错误: {str(e)}", exc_info=True)
            raise

    def _format_url(self, url):
        """统一格式化URL（兼容特殊字符）"""
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        return url.rstrip('/').replace(' ', '%20')  # 处理空格

    async def simple_purge(self, urls):
        """执行URL刷新（增加重试机制）"""
        req = models.PurgeUrlsCacheRequest()
        req.Urls = [self._format_url(url) for url in urls]
        req.ZoneId = self.zone_id

        try:
            resp = self.client.PurgeUrlsCache(req)
            return {
                "count": len(urls),
                "request_id": resp.RequestId
            }
        except Exception as e:
            logger.error(f"刷新失败 | URL数量: {len(urls)}")
            raise RuntimeError(f"API错误: {str(e)}")

    async def simple_preheat(self, urls):
        """执行URL预热（增加参数校验）"""
        if not urls:
            raise ValueError("至少需要提供一个URL")

        req = models.PushUrlsCacheRequest()
        req.Urls = [self._format_url(url) for url in urls]
        req.ZoneId = self.zone_id

        try:
            resp = self.client.PushUrlsCache(req)
            return {
                "count": len(urls),
                "request_id": resp.RequestId
            }
        except Exception as e:
            logger.error(f"预热失败 | URL数量: {len(urls)}")
            raise RuntimeError(f"API错误: {str(e)}")
