import json
import hmac
import hashlib
import time
import asyncio
import logging
from typing import Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2
MAX_RETRY_DELAY = 30

BASE_URL = "https://api.binance.com"


class BinanceClient:
    def __init__(self, access_token: str):
        creds = json.loads(access_token)
        self.api_key = creds["api_key"]
        self.api_secret = creds["api_secret"]

    def _headers(self) -> dict:
        return {
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/json",
        }

    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        signed: bool = False,
    ) -> dict:
        params = dict(params or {})
        if signed:
            params = self._sign(params)

        url = f"{BASE_URL}{endpoint}"

        for attempt in range(MAX_RETRIES + 1):
            async with httpx.AsyncClient() as client:
                # Binance expects all params (including signed) as query string
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self._headers(),
                    params=params,
                    timeout=30.0,
                )

            if response.status_code == 429:
                if attempt >= MAX_RETRIES:
                    raise httpx.HTTPStatusError(
                        f"Binance rate limit exceeded after {MAX_RETRIES} retries.",
                        request=response.request,
                        response=response,
                    )
                retry_after = int(response.headers.get("Retry-After", DEFAULT_RETRY_DELAY))
                delay = min(retry_after, MAX_RETRY_DELAY)
                logger.warning("Binance 429, retrying in %ds (attempt %d)", delay, attempt + 1)
                await asyncio.sleep(delay)
                continue

            if response.status_code == 418:
                raise httpx.HTTPStatusError(
                    "Binance IP banned. Too many requests were sent after receiving 429.",
                    request=response.request,
                    response=response,
                )

            if response.status_code >= 400:
                body = response.text[:500]
                raise httpx.HTTPStatusError(
                    f"Binance API error (HTTP {response.status_code}): {body}",
                    request=response.request,
                    response=response,
                )

            return response.json()

        raise RuntimeError("Unexpected end of retry loop")

    # ── Public endpoints (no signing) ──

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 50,
    ) -> list:
        return await self._request("GET", "/api/v3/klines", {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit,
        })

    async def get_ticker_24hr(self, symbol: Optional[str] = None) -> dict | list:
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return await self._request("GET", "/api/v3/ticker/24hr", params)

    async def get_depth(self, symbol: str, limit: int = 20) -> dict:
        return await self._request("GET", "/api/v3/depth", {
            "symbol": symbol.upper(),
            "limit": limit,
        })

    async def get_price(self, symbol: Optional[str] = None) -> dict | list:
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return await self._request("GET", "/api/v3/ticker/price", params)

    async def get_exchange_info(self, symbol: Optional[str] = None) -> dict:
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return await self._request("GET", "/api/v3/exchangeInfo", params)

    # ── Signed endpoints ──

    async def get_account(self) -> dict:
        return await self._request("GET", "/api/v3/account", signed=True)

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Optional[str] = None,
        quote_order_qty: Optional[str] = None,
        price: Optional[str] = None,
        time_in_force: Optional[str] = None,
    ) -> dict:
        params = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
        }
        if quantity:
            params["quantity"] = quantity
        if quote_order_qty:
            params["quoteOrderQty"] = quote_order_qty
        if price:
            params["price"] = price
        if time_in_force:
            params["timeInForce"] = time_in_force
        elif order_type.upper() == "LIMIT":
            params["timeInForce"] = "GTC"

        return await self._request("POST", "/api/v3/order", params, signed=True)

    async def cancel_order(self, symbol: str, order_id: int) -> dict:
        return await self._request("DELETE", "/api/v3/order", {
            "symbol": symbol.upper(),
            "orderId": order_id,
        }, signed=True)

    async def get_open_orders(self, symbol: Optional[str] = None) -> list:
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return await self._request("GET", "/api/v3/openOrders", params, signed=True)

    async def get_order(self, symbol: str, order_id: int) -> dict:
        return await self._request("GET", "/api/v3/order", {
            "symbol": symbol.upper(),
            "orderId": order_id,
        }, signed=True)

    async def get_my_trades(self, symbol: str, limit: int = 20) -> list:
        return await self._request("GET", "/api/v3/myTrades", {
            "symbol": symbol.upper(),
            "limit": limit,
        }, signed=True)
