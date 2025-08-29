import asyncio
import random
import time
from typing import List
from typing import TypedDict

import httpx

from bot.core.config import settings
from bot.core.logging_setup import log


class ProxyResult(TypedDict):
    proxy: str
    latency: float
    score: float
    status: str


class ProxyService:
    def __init__(self):
        self._proxy_pool: List[ProxyResult] = []
        self._lock = asyncio.Lock()

    async def _fetch_proxy_list(self, limit: int = 40) -> list[str]:
        # ... (Your fetch_proxy_list logic goes here) ...
        # Make sure to handle potential errors and return []
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                resp = await client.get(settings.PROXYSCRAPE_URL, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                proxies_data = data.get("proxies", [])
                proxies = [f"http://{p['proxy']}" for p in proxies_data]
                return random.sample(proxies, k=min(limit, len(proxies)))
        except Exception as e:
            log.error(f"Failed to fetch proxy list: {repr(e)}")
            return []

    async def _check_proxy(
        self, proxy: str, sem: asyncio.Semaphore, retries: int
    ) -> ProxyResult:
        async with sem:
            for _ in range(retries):
                start_time = time.monotonic()
                try:
                    async with httpx.AsyncClient(proxy=proxy) as client:
                        resp = await client.get(
                            "https://api.telegram.org/bot1/getMe", timeout=7
                        )
                    # We expect a 401 Unauthorized,
                    # which is a SUCCESS for the connection.
                    if resp.status_code == 401:
                        latency = time.monotonic() - start_time
                        score = max(0.0, 100 - (latency * 20))
                        return {
                            "proxy": proxy,
                            "latency": latency,
                            "score": round(score, 2),
                            "status": "ok",
                        }
                except httpx.ConnectError as e:
                    # This will catch the SSL verification error
                    if "CERTIFICATE_VERIFY_FAILED" in str(e):
                        # This is a bad proxy, don't even retry.
                        break
                    await asyncio.sleep(0.5)
                    continue
                except (httpx.RequestError, asyncio.TimeoutError):
                    await asyncio.sleep(0.5)
                    continue
        return {"proxy": proxy, "latency": float("inf"), "score": 0, "status": "failed"}

    async def build_pool(self, fetch_limit: int = 50, max_concurrent: int = 25):
        """Builds and rates the proxy pool. Should be called on startup."""
        log.info("Building a new rated proxy pool...")
        async with self._lock:
            raw_proxies = await self._fetch_proxy_list(limit=fetch_limit)
            if not raw_proxies:
                self._proxy_pool = []
                log.warning("Could not fetch any proxies to build a pool.")
                return

            sem = asyncio.Semaphore(max_concurrent)
            tasks = [self._check_proxy(p, sem, 2) for p in raw_proxies]
            results = await asyncio.gather(*tasks)

            valid_proxies = [
                res
                for res in results
                if isinstance(res, dict) and res.get("status") == "ok"
            ]
            if valid_proxies:
                valid_proxies.sort(key=lambda x: x["score"], reverse=True)
                self._proxy_pool = valid_proxies
                log.success(
                    f"Built proxy pool with {len(self._proxy_pool)} valid proxies."
                )
            else:
                self._proxy_pool = []
                log.warning("Could not find any working free proxies.")

    async def get_proxy(self) -> str | None:
        """Returns the best available proxy URL."""
        async with self._lock:
            if not self._proxy_pool:
                log.warning("Proxy pool is empty. Attempting to rebuild...")
                # You might want to add a cooldown here to prevent constant rebuilding
                await self.build_pool()  # Attempt to rebuild on the fly

            if self._proxy_pool:
                # Basic rotation: use the best one, then move it to the back
                best_proxy = self._proxy_pool.pop(0)
                self._proxy_pool.append(best_proxy)
                return best_proxy["proxy"]
        return None
