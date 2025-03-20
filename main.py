# main.py
import logging
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.cdn.v20180606 import cdn_client, models
from astrbot.api.star import register, Star, Context
from astrbot.api.event import filter, AstrMessageEvent

logger = logging.getLogger(__name__)

@register(
    "simplecdn",
    "eebk",
    "腾讯云CDN管理插件",
    "1.1.0"
)
class SimpleCDNPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._manager = None
        self._load_config()

    def _load_config(self):
        """直接从上下文中加载配置"""
        config = self.context._config  # 通过 Context 获取配置
        
        required_keys = ['secret_id', 'secret_key', 'zone_id']
        missing = [k for k in required_keys if not config.get(k)]
        if missing:
            logger.error(f"❌ 配置缺失关键参数: {', '.join(missing)}")
            return False

        if not config['zone_id'].startswith('zone-'):
            logger.error("❌ zone_id 必须包含 'zone-' 前缀")
            return False

        try:
            self._manager = CDNManager(
                secret_id=config['secret_id'],
                secret_key=config['secret_key'],
                region=config.get('region', 'ap-singapore'),
                zone_id=config['zone_id']
            )
            logger.info("✅ CDN 管理器初始化成功")
            return True
        except Exception as e:
            logger.error(f"❌ 初始化失败: {str(e)}", exc_info=True)
            return False

    @filter.command("cdn")
    async def handle_cdn_command(self, event: AstrMessageEvent):
        """处理 /cdn 指令"""
        try:
            # 解析命令参数
            parts = event.message_str.strip().split()
            if len(parts) < 2 or not parts[1].startswith(('http://', 'https://')):
                yield event.plain_result("❌ 格式错误: /cdn <URL> [--preheat]")
                return

            # 提取参数
            is_preheat = "--preheat" in parts
            urls = [p for p in parts[1:] if p not in ('--preheat')]

            # 执行操作
            if is_preheat:
                result = await self._manager.preheat_urls(urls)
                msg = f"🔥 已预热 {result['count']} 个URL (请求ID: {result['request_id']})"
            else:
                result = await self._manager.purge_urls(urls)
                msg = f"🔄 已刷新 {result['count']} 个URL (请求ID: {result['request_id']})"
            
            yield event.plain_result(msg)

        except Exception as e:
            logger.error(f"❌ 操作失败: {str(e)}", exc_info=True)
            yield event.plain_result(f"❌ 错误: {str(e)}")

    async def terminate(self):
        """资源清理"""
        if self._manager:
            logger.info("🛑 正在释放 CDN 管理器资源...")
            del self._manager
            self._manager = None

class CDNManager:
    """腾讯云 CDN 操作核心类"""
    def __init__(self, secret_id: str, secret_key: str, region: str, zone_id: str):
        # 凭证配置
        self.cred = credential.Credential(secret_id, secret_key)
        
        # HTTP 配置
        http_profile = HttpProfile(
            endpoint="cdn.tencentcloudapi.com",
            reqTimeout=30
        )
        
        # 客户端配置
        client_profile = ClientProfile(httpProfile=http_profile)
        client_profile.signMethod = "TC3-HMAC-SHA256"  # 强制签名算法
        
        # 创建客户端（关键修正点）
        self.client = cdn_client.CdnClient(
            cred=self.cred,
            region=region,
            profile=client_profile,
            version="2018-06-06"  # 正确参数名
        )
        
        self.zone_id = zone_id
        logger.debug("🔧 SDK 客户端初始化完成")

    def _format_url(self, url: str) -> str:
        """标准化 URL 格式"""
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        return url.strip().replace(' ', '%20')

    async def purge_urls(self, urls: list) -> dict:
        """刷新缓存"""
        req = models.PurgeUrlsCacheRequest()
        req.Urls = [self._format_url(url) for url in urls]
        req.ZoneId = self.zone_id
        
        try:
            resp = self.client.PurgeUrlsCache(req)
            return {"count": len(urls), "request_id": resp.RequestId}
        except Exception as e:
            logger.error(f"🔄 刷新失败 | 错误: {str(e)}")
            raise RuntimeError(f"API 错误: {str(e)}")

    async def preheat_urls(self, urls: list) -> dict:
        """预热缓存"""
        if not urls:
            raise ValueError("至少需要提供一个 URL")
            
        req = models.PushUrlsCacheRequest()
        req.Urls = [self._format_url(url) for url in urls]
        req.ZoneId = self.zone_id
        
        try:
            resp = self.client.PushUrlsCache(req)
            return {"count": len(urls), "request_id": resp.RequestId}
        except Exception as e:
            logger.error(f"🔥 预热失败 | 错误: {str(e)}")
            raise RuntimeError(f"API 错误: {str(e)}")
