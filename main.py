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
        """统一格式化URL"""
        # 补全协议头
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        # 统一去除路径末尾斜杠
        return url.rstrip('/')

    async def simple_purge(self, urls):
        """执行刷新操作"""
        paths = []
        files = []
        
        for raw_url in urls:
            formatted = self._format_url(raw_url)
            # 判断是否为目录（以/结尾）
            if raw_url.endswith('/'):
                paths.append(formatted + '/')  # 补充结尾斜杠
            else:
                files.append(formatted)

        # 提交文件刷新
        if files:
            req = models.PurgeUrlsCacheRequest()
            req.Urls = files
            self.client.PurgeUrlsCache(req)
        
        # 提交目录刷新
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
        # 从配置加载腾讯云凭证
        secret_id = self.config.get("secret_id")
        secret_key = self.config.get("secret_key")
        self.manager = SimpleCDNManager(secret_id, secret_key)

    async def handle_command(self, session: MessageSession):
        args = session.command_args
        is_preheat = "--preheat" in args
        urls = [arg for arg in args if not arg.startswith("--")]
        
        try:
            if is_preheat:
                # 立即返回提交结果
                count = await self.manager.simple_preheat(urls)
                await session.send(f"🔥 已提交{count}个预热请求")
                # 启动后台队列处理
                asyncio.create_task(self._background_preheat(urls))
            else:
                # 处理刷新请求
                count = await self.manager.simple_purge(urls)
                await session.send(f"🔄 已提交{count}个刷新请求")
                
        except Exception as e:
            await session.send(f"❌ 操作失败：{str(e)}")

    async def _background_preheat(self, urls):
        """后台预热队列处理器"""
        for url in urls:
            try:
                await self.manager.simple_preheat([url])
                await asyncio.sleep(5)  # 严格保持5秒间隔
            except Exception:
                pass  # 静默失败不通知

# plugin.yaml
name: SimpleCDN
version: 1.1
author: YourName
description: 腾讯云CDN缓存管理插件
entry_point: main.py
config_schema:
  secret_id:
    type: string
    label: 腾讯云SecretId
  secret_key:
    type: string
    label: 腾讯云SecretKey
    input_type: password
commands:
  - name: cdn
    description: CDN缓存管理
    usage: |
      /cdn <链接...> [--preheat]
      示例：
      /cdn example.com/static/ --preheat
      /cdn example.com/image.jpg

# requirements.txt
tencentcloud-sdk-python>=3.0.950
