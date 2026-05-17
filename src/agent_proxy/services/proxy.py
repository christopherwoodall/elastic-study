import httpx

from agent_proxy.config import TARGET_URL


class ProxyClient:
    def __init__(self):
        self.client: httpx.AsyncClient | None = None

    def start(self):
        self.client = httpx.AsyncClient(
            base_url=TARGET_URL,
            timeout=httpx.Timeout(300.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )

    async def close(self):
        if self.client and not self.client.is_closed:
            await self.client.aclose()

    def get(self) -> httpx.AsyncClient:
        if not self.client:
            raise RuntimeError("Proxy client is not initialized.")
        return self.client


# Singleton instance
http_proxy = ProxyClient()
