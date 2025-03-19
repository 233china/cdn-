# main.py
import re
import asyncio
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.cdn.v20180606 import cdn_client, models
from astrbot.core.plugin import Plugin
from astrbot.core.types import MessageSession

class SimpleCDNManager:
    def __init__(self, secret_id, secret_key):
        cred = credential.Credential(secret_id, secret_key)
        http_profile = HttpProfile(endpoint="cdn.tencentcloudapi.com")
        client_profile = ClientProfile(httpProfile=http_profile)
        self.client = cdn_client.CdnClient(cred, "", client_profile)

    def _format_url(self, url):
        """基础URL格式化"""
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        return url.rstrip('/')

    async def simple_purge(self, urls):
        """执行刷新操作"""
        paths = []
        files = []
        
        for url in urls:
            formatted = self._format_url(url)
            if url.endswith('/'):
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

class SimpleCdnPlugin(Plugin):
    def __init__(self, bot):
        super().__init__(bot)
        self.manager = None
        
    async def on_load(self):
        secret_id = self.config.get("secret_id")
        secret_key = self.config.get("secret_key")
        self.manager = SimpleCDNManager(secret_id, secret_key)

    async def handle_command(self, session: MessageSession):
        args = session.command_args
        is_preheat = "--preheat" in args
        urls = [arg for arg in args if not arg.startswith("--")]
        
        try:
            if is_preheat:
                count = await self.manager.simple_preheat(urls)
                await session.send(f"🔥 已提交{count}个预热请求")
                asyncio.create_task(self._background_preheat(urls))
            else:
                count = await self.manager.simple_purge(urls)
                await session.send(f"🔄 已提交{count}个刷新请求")
                
        except Exception as e:
            await session.send(f"❌ 操作失败：{str(e)}")

    async def _background_preheat(self, urls):
        """后台预热队列"""
        for url in urls:
            try:
                await self.manager.simple_preheat([url])
                await asyncio.sleep(5)
            except:
                pass
