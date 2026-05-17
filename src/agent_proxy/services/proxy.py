import httpx

from agent_proxy.config import TARGET_URL


class ProxyClient:
    """
    An asynchronous HTTP client service designed to forward requests to an upstream target.

    This class encapsulates an `httpx.AsyncClient` configured specifically for
    reverse-proxy operations, including high connection limits, extended timeouts (to accommodate slow LLM responses), and automatic redirect handling.
    """

    def __init__(self):
        """
        Initializes the ProxyClient.

        The actual `httpx.AsyncClient` is not created until `start()` is called
        to ensure it attaches to the correct running asyncio event loop.
        """
        self.client: httpx.AsyncClient | None = None

    def start(self) -> None:
        """
        Instantiates and configures the underlying HTTP client.

        This method configures the client with the `TARGET_URL` as the base address. It sets a high timeout (300 seconds) to handle long-running generations, and configures connection limits to maintain an efficient connection pool for high-throughput traffic.

        This should be called during the application startup phase.
        """
        self.client = httpx.AsyncClient(
            base_url=TARGET_URL,
            timeout=httpx.Timeout(300.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )

    async def close(self) -> None:
        """
        Gracefully closes the HTTP client and terminates all active connections.

        This ensures that keep-alive connections are properly shut down to prevent resource leaks. This should be called during the application shutdown phase.
        """
        if self.client and not self.client.is_closed:
            await self.client.aclose()

    def get(self) -> httpx.AsyncClient:
        """
        Retrieves the active, configured `httpx.AsyncClient` instance.

        Returns:
            httpx.AsyncClient: The active HTTP client ready to dispatch requests.

        Raises:
            RuntimeError: If this method is called before the client has been
                initialized via the `start()` method.
        """
        if not self.client:
            raise RuntimeError("Proxy client is not initialized. Call start() first.")
        return self.client


# Singleton instance to be used across the app
http_proxy = ProxyClient()
