from typing import Optional

from app.integrations.base import ToolDefinition, ToolResult
from app.integrations.binance.client import BinanceClient
from app.integrations.binance import analysis


BINANCE_TOOLS = [
    # =====================================================
    # MARKET DATA — no signing required
    # =====================================================
    ToolDefinition(
        name="binance.market.klines",
        description=(
            "Get candlestick (OHLCV) chart data with optional technical indicators.\n"
            "\n"
            "Returns a formatted table of recent candles plus computed indicators with "
            "AI-friendly interpretations (bullish/bearish/neutral signals).\n"
            "\n"
            "WORKFLOW: Start with klines to understand price action, then use depth for order book, "
            "and top_movers to scan the market. Use indicators=['rsi','macd','bbands','sma'] "
            "for full technical analysis.\n"
            "\n"
            "Intervals: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading pair, e.g. BTCUSDT, ETHUSDT, SOLUSDT",
                },
                "interval": {
                    "type": "string",
                    "description": "Candle interval: 1m, 5m, 15m, 1h, 4h, 1d, 1w (default: 1h)",
                    "default": "1h",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of candles, 1-500 (default: 50). More data = better indicators but larger response.",
                    "default": 50,
                },
                "indicators": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["rsi", "macd", "bbands", "sma"],
                    },
                    "description": (
                        "Technical indicators to compute: rsi (RSI 14), macd (MACD 12/26/9), "
                        "bbands (Bollinger 20/2), sma (SMA 20). "
                        "Use all four for comprehensive analysis."
                    ),
                },
            },
            "required": ["symbol"],
        },
    ),
    ToolDefinition(
        name="binance.market.ticker",
        description=(
            "Get 24-hour price statistics for a trading pair.\n"
            "Returns: current price, 24h change %, high, low, volume.\n"
            "Omit symbol to get top 20 pairs by volume."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading pair (e.g. BTCUSDT). Omit for top 20 by volume.",
                },
            },
        },
    ),
    ToolDefinition(
        name="binance.market.depth",
        description=(
            "Get the order book (bids and asks) for a trading pair.\n"
            "Returns formatted depth with spread, bid/ask ratio, and wall detection.\n"
            "Use to gauge buy/sell pressure and identify support/resistance."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading pair, e.g. BTCUSDT",
                },
                "limit": {
                    "type": "integer",
                    "description": "Depth levels: 5, 10, 20, 50, 100 (default: 20)",
                    "default": 20,
                },
            },
            "required": ["symbol"],
        },
    ),
    ToolDefinition(
        name="binance.market.top_movers",
        description=(
            "Find top gaining and losing coins in the last 24 hours.\n"
            "Great for scanning the market and finding momentum plays.\n"
            "Filters out low-volume pairs automatically."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["gainers", "losers", "both"],
                    "description": "Which movers to show (default: both)",
                    "default": "both",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of results per direction (default: 10)",
                    "default": 10,
                },
                "quote_asset": {
                    "type": "string",
                    "description": "Quote currency to filter by (default: USDT)",
                    "default": "USDT",
                },
            },
        },
    ),
    # =====================================================
    # ACCOUNT — requires signing
    # =====================================================
    ToolDefinition(
        name="binance.account.portfolio",
        description=(
            "Get your spot wallet balances with estimated USD values.\n"
            "Shows all non-zero assets with free and locked amounts.\n"
            "Use this to check what you hold before trading."
        ),
        input_schema={"type": "object", "properties": {}},
    ),
    ToolDefinition(
        name="binance.account.open_orders",
        description=(
            "List all open (unfilled) orders.\n"
            "Optionally filter by symbol. Shows order type, price, quantity, and status."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Filter by trading pair (optional — omit for all)",
                },
            },
        },
    ),
    ToolDefinition(
        name="binance.account.trade_history",
        description=(
            "Get your recent executed trades for a specific pair.\n"
            "Shows time, side, price, quantity, and total value."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading pair, e.g. BTCUSDT",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of trades (default: 20, max: 500)",
                    "default": 20,
                },
            },
            "required": ["symbol"],
        },
    ),
    # =====================================================
    # TRADING — requires signing. SPOT ONLY.
    # =====================================================
    ToolDefinition(
        name="binance.trade.buy",
        description=(
            "Place a BUY order on Binance Spot.\n"
            "\n"
            "WARNING: This places a REAL order with REAL money. "
            "Always confirm the details with the user before executing.\n"
            "\n"
            "For MARKET orders: set quote_quantity to buy with a specific USDT amount "
            "(e.g. quote_quantity='100' to spend 100 USDT), or set quantity for exact coin amount.\n"
            "For LIMIT orders: set quantity and price."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading pair, e.g. BTCUSDT",
                },
                "type": {
                    "type": "string",
                    "enum": ["MARKET", "LIMIT"],
                    "description": "Order type",
                },
                "quantity": {
                    "type": "string",
                    "description": "Amount of base asset to buy (e.g. '0.001' BTC). Use this OR quote_quantity.",
                },
                "quote_quantity": {
                    "type": "string",
                    "description": "Amount of quote asset to spend (e.g. '100' USDT). For MARKET orders only.",
                },
                "price": {
                    "type": "string",
                    "description": "Limit price (required for LIMIT orders)",
                },
            },
            "required": ["symbol", "type"],
        },
    ),
    ToolDefinition(
        name="binance.trade.sell",
        description=(
            "Place a SELL order on Binance Spot.\n"
            "\n"
            "WARNING: This places a REAL order with REAL money. "
            "Always confirm the details with the user before executing.\n"
            "\n"
            "For MARKET orders: set quantity for exact coin amount to sell.\n"
            "For LIMIT orders: set quantity and price."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading pair, e.g. BTCUSDT",
                },
                "type": {
                    "type": "string",
                    "enum": ["MARKET", "LIMIT"],
                    "description": "Order type",
                },
                "quantity": {
                    "type": "string",
                    "description": "Amount of base asset to sell (e.g. '0.001' BTC)",
                },
                "price": {
                    "type": "string",
                    "description": "Limit price (required for LIMIT orders)",
                },
            },
            "required": ["symbol", "type", "quantity"],
        },
    ),
    ToolDefinition(
        name="binance.trade.cancel",
        description="Cancel an open order by its order ID.",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading pair, e.g. BTCUSDT",
                },
                "order_id": {
                    "type": "integer",
                    "description": "Order ID to cancel (from open_orders or order creation response)",
                },
            },
            "required": ["symbol", "order_id"],
        },
    ),
    ToolDefinition(
        name="binance.trade.order_status",
        description="Check the status of a specific order.",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading pair, e.g. BTCUSDT",
                },
                "order_id": {
                    "type": "integer",
                    "description": "Order ID to check",
                },
            },
            "required": ["symbol", "order_id"],
        },
    ),
]


async def execute_tool(
    tool_name: str,
    args: dict,
    access_token: str,
    meta: Optional[dict] = None,
) -> ToolResult:
    client = BinanceClient(access_token)

    try:
        # ── Market Data ──

        if tool_name == "binance.market.klines":
            klines = await client.get_klines(
                symbol=args["symbol"],
                interval=args.get("interval", "1h"),
                limit=min(args.get("limit", 50), 500),
            )
            text = analysis.format_klines_with_indicators(
                klines=klines,
                symbol=args["symbol"].upper(),
                interval=args.get("interval", "1h"),
                indicators=args.get("indicators"),
            )
            return ToolResult(success=True, data={"output": text})

        elif tool_name == "binance.market.ticker":
            symbol = args.get("symbol")
            if symbol:
                ticker = await client.get_ticker_24hr(symbol)
                text = analysis.format_ticker(ticker)
            else:
                all_tickers = await client.get_ticker_24hr()
                # Top 20 by quote volume for USDT pairs
                usdt_tickers = [
                    t for t in all_tickers
                    if t.get("symbol", "").endswith("USDT")
                ]
                top = sorted(
                    usdt_tickers,
                    key=lambda t: float(t.get("quoteVolume", 0)),
                    reverse=True,
                )[:20]
                lines = ["Top 20 USDT pairs by volume:", ""]
                for i, t in enumerate(top, 1):
                    lines.append(f"  {i:>2}. {analysis.format_ticker(t)}")
                text = "\n".join(lines)
            return ToolResult(success=True, data={"output": text})

        elif tool_name == "binance.market.depth":
            depth = await client.get_depth(
                symbol=args["symbol"],
                limit=args.get("limit", 20),
            )
            text = analysis.format_depth(depth, args["symbol"].upper())
            return ToolResult(success=True, data={"output": text})

        elif tool_name == "binance.market.top_movers":
            all_tickers = await client.get_ticker_24hr()
            text = analysis.format_top_movers(
                tickers=all_tickers,
                direction=args.get("direction", "both"),
                limit=args.get("limit", 10),
                quote_asset=args.get("quote_asset", "USDT"),
            )
            return ToolResult(success=True, data={"output": text})

        # ── Account ──

        elif tool_name == "binance.account.portfolio":
            account = await client.get_account()
            prices = await client.get_price()
            text = analysis.format_portfolio(account, prices)
            return ToolResult(success=True, data={"output": text})

        elif tool_name == "binance.account.open_orders":
            orders = await client.get_open_orders(args.get("symbol"))
            if not orders:
                return ToolResult(success=True, data={"output": "No open orders."})
            lines = ["Open orders:", ""]
            for o in orders:
                lines.append(analysis.format_order(o))
            return ToolResult(success=True, data={"output": "\n".join(lines)})

        elif tool_name == "binance.account.trade_history":
            trades = await client.get_my_trades(
                symbol=args["symbol"],
                limit=args.get("limit", 20),
            )
            text = analysis.format_trades(trades, args["symbol"].upper())
            return ToolResult(success=True, data={"output": text})

        # ── Trading ──

        elif tool_name == "binance.trade.buy":
            order = await client.create_order(
                symbol=args["symbol"],
                side="BUY",
                order_type=args["type"],
                quantity=args.get("quantity"),
                quote_order_qty=args.get("quote_quantity"),
                price=args.get("price"),
            )
            text = "Order placed!\n" + analysis.format_order(order)
            return ToolResult(success=True, data={"output": text})

        elif tool_name == "binance.trade.sell":
            order = await client.create_order(
                symbol=args["symbol"],
                side="SELL",
                order_type=args["type"],
                quantity=args["quantity"],
                price=args.get("price"),
            )
            text = "Order placed!\n" + analysis.format_order(order)
            return ToolResult(success=True, data={"output": text})

        elif tool_name == "binance.trade.cancel":
            result = await client.cancel_order(
                symbol=args["symbol"],
                order_id=args["order_id"],
            )
            text = "Order cancelled.\n" + analysis.format_order(result)
            return ToolResult(success=True, data={"output": text})

        elif tool_name == "binance.trade.order_status":
            order = await client.get_order(
                symbol=args["symbol"],
                order_id=args["order_id"],
            )
            return ToolResult(success=True, data={"output": analysis.format_order(order)})

        else:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    except Exception as e:
        return ToolResult(success=False, error=str(e))
