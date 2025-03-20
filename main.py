import re
import asyncio
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.cdn.v20180606 import cdn_client, models

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("simplecdn", "YourName", "腾讯云CDN管理插件", "1.1.0")
class SimpleCdnPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.manager = None
        self.secret_id = context.config.get("secret_id")
        self.secret_key = context.config.get("secret_key")
    
    async def on_load(self):
        """插件加载时初始化"""
        self.manager = SimpleCDNManager(self.secret_id, self.secret_key)

    @filter.command("cdn")
    async def handle_cdn_command(self, event: AstrMessageEvent):
        '''CDN缓存刷新/预热'''
        args = event.message_str.split()[1:]  # 解析命令参数
        is_preheat = "--preheat" in args
        urls = [arg for arg in args if not arg.startswith("--")]
        
        try:
            if not self.manager:
                self.manager = SimpleCDNManager(self.secret_id, self.secret_key)

            if is_preheat:
                count = await self.manager.simple_preheat(urls)
                yield event.plain_result(f"🔥 已提交{count}个预热请求")
                # 启动后台队列处理
                asyncio.create_task(self._background_preheat(urls))
            else:
                count = await self.manager.simple_purge(urls)
                yield event.plain_result(f"🔄 已提交{count}个刷新请求")
                
        except Exception as e:
            logger.error(f"操作失败: {str(e)}")
            yield event.plain_result(f"❌ 操作失败：{str(e)}")

    async def _background_preheat(self, urls):
        """后台预热队列处理器"""
        for url in urls:
            try:
                await self.manager.simple_preheat([url])
                await asyncio.sleep(5)  # 严格保持5秒间隔
            except Exception as e:
                logger.error(f"后台预热失败: {str(e)}")

    async def terminate(self):
        """插件卸载时清理"""
        self.manager = None

class SimpleCDNManager:
    # 保持原有实现不变
    def __init__(self, secret_id, secret_key):
        cred = credential.Credential(secret_id, secret_key)
        http_profile = HttpProfile(endpoint="cdn.tencentcloudapi.com")
        client_profile = ClientProfile(httpProfile=http_profile)
        self.client = cdn_client.CdnClient(cred, "", client_profile)

    def _format_url(self, url):
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        return url.rstrip('/')

    async def simple_purge(self, urls):
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
        req = models.PushUrlsCacheRequest()
        req.Urls = [self._format_url(url) for url in urls]
        self.client.PushUrlsCache(req)
        return len(urls)
