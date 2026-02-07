"""Pure-Python technical indicators and AI-friendly formatters for Binance data."""

from datetime import datetime, timezone


# ── Indicators ──


def compute_sma(values: list[float], period: int) -> list[float | None]:
    result = [None] * (period - 1)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1: i + 1]
        result.append(sum(window) / period)
    return result


def compute_ema(values: list[float], period: int) -> list[float | None]:
    if len(values) < period:
        return [None] * len(values)
    k = 2 / (period + 1)
    result: list[float | None] = [None] * (period - 1)
    ema = sum(values[:period]) / period
    result.append(ema)
    for i in range(period, len(values)):
        ema = values[i] * k + ema * (1 - k)
        result.append(ema)
    return result


def compute_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    if len(closes) < period + 1:
        return [None] * len(closes)

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    result: list[float | None] = [None] * period
    if avg_loss == 0:
        result.append(100.0)
    else:
        rs = avg_gain / avg_loss
        result.append(100 - (100 / (1 + rs)))

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - (100 / (1 + rs)))

    return result


def compute_macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> dict:
    ema_fast = compute_ema(closes, fast)
    ema_slow = compute_ema(closes, slow)

    macd_line: list[float | None] = []
    for f, s in zip(ema_fast, ema_slow):
        if f is not None and s is not None:
            macd_line.append(f - s)
        else:
            macd_line.append(None)

    macd_values = [v for v in macd_line if v is not None]
    signal_raw = compute_ema(macd_values, signal_period) if macd_values else []

    signal_line: list[float | None] = []
    idx = 0
    for v in macd_line:
        if v is not None:
            signal_line.append(signal_raw[idx] if idx < len(signal_raw) else None)
            idx += 1
        else:
            signal_line.append(None)

    histogram: list[float | None] = []
    for m, s in zip(macd_line, signal_line):
        if m is not None and s is not None:
            histogram.append(m - s)
        else:
            histogram.append(None)

    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def compute_bollinger(
    closes: list[float], period: int = 20, std_dev: float = 2.0
) -> dict:
    sma = compute_sma(closes, period)
    upper: list[float | None] = []
    lower: list[float | None] = []

    for i, m in enumerate(sma):
        if m is None:
            upper.append(None)
            lower.append(None)
        else:
            window = closes[i - period + 1: i + 1]
            variance = sum((x - m) ** 2 for x in window) / period
            sd = variance ** 0.5
            upper.append(m + std_dev * sd)
            lower.append(m - std_dev * sd)

    return {"upper": upper, "middle": sma, "lower": lower}


# ── Interpretation ──


def interpret_rsi(value: float) -> str:
    if value >= 80:
        return f"{value:.1f} — Strongly overbought (extreme)"
    if value >= 70:
        return f"{value:.1f} — Overbought (potential reversal)"
    if value >= 60:
        return f"{value:.1f} — Bullish momentum"
    if value >= 40:
        return f"{value:.1f} — Neutral"
    if value >= 30:
        return f"{value:.1f} — Bearish momentum"
    if value >= 20:
        return f"{value:.1f} — Oversold (potential bounce)"
    return f"{value:.1f} — Strongly oversold (extreme)"


def interpret_macd(macd_val: float, signal_val: float, hist_val: float) -> str:
    parts = f"Line {macd_val:+.2f} | Signal {signal_val:+.2f} | Hist {hist_val:+.2f}"
    if hist_val > 0 and macd_val > signal_val:
        if hist_val > abs(signal_val) * 0.5:
            return f"{parts} — Strong bullish"
        return f"{parts} — Bullish"
    if hist_val < 0 and macd_val < signal_val:
        if abs(hist_val) > abs(signal_val) * 0.5:
            return f"{parts} — Strong bearish"
        return f"{parts} — Bearish"
    return f"{parts} — Transitioning"


def interpret_bollinger(price: float, upper: float, middle: float, lower: float) -> str:
    band_width = upper - lower
    if band_width == 0:
        return f"Upper {upper:.2f} | Mid {middle:.2f} | Lower {lower:.2f} — Flat"
    position = (price - lower) / band_width
    parts = f"Upper {upper:.2f} | Mid {middle:.2f} | Lower {lower:.2f}"
    if position > 0.95:
        return f"{parts} — Price at upper band (overbought zone)"
    if position > 0.7:
        return f"{parts} — Price in upper half (bullish bias)"
    if position > 0.3:
        return f"{parts} — Price near middle (neutral)"
    if position > 0.05:
        return f"{parts} — Price in lower half (bearish bias)"
    return f"{parts} — Price at lower band (oversold zone)"


def generate_signal_summary(
    rsi_val: float | None,
    macd_hist: float | None,
    bb_position: float | None,
    price: float,
    sma_val: float | None,
) -> str:
    signals = []
    bullish = 0
    bearish = 0

    if rsi_val is not None:
        if rsi_val >= 70:
            bearish += 1
            signals.append("RSI overbought")
        elif rsi_val <= 30:
            bullish += 1
            signals.append("RSI oversold (reversal potential)")
        elif rsi_val > 50:
            bullish += 1
            signals.append("RSI above 50")
        else:
            bearish += 1
            signals.append("RSI below 50")

    if macd_hist is not None:
        if macd_hist > 0:
            bullish += 1
            signals.append("MACD positive histogram")
        else:
            bearish += 1
            signals.append("MACD negative histogram")

    if sma_val is not None:
        if price > sma_val:
            bullish += 1
            signals.append("price above SMA")
        else:
            bearish += 1
            signals.append("price below SMA")

    if bb_position is not None:
        if bb_position > 0.8:
            bearish += 0.5
            signals.append("near upper Bollinger")
        elif bb_position < 0.2:
            bullish += 0.5
            signals.append("near lower Bollinger")

    total = bullish + bearish
    if total == 0:
        return "Insufficient data for signal."
    ratio = bullish / total
    if ratio > 0.7:
        bias = "Bullish"
    elif ratio > 0.55:
        bias = "Moderately bullish"
    elif ratio > 0.45:
        bias = "Mixed/Neutral"
    elif ratio > 0.3:
        bias = "Moderately bearish"
    else:
        bias = "Bearish"

    return f"{bias}. {', '.join(signals)}."


# ── Formatters ──


def _ts_to_str(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%m-%d %H:%M")


def _fmt_num(val: float, decimals: int = 2) -> str:
    if abs(val) >= 1_000_000:
        return f"{val / 1_000_000:.2f}M"
    if abs(val) >= 1_000:
        return f"{val / 1_000:.2f}K"
    return f"{val:.{decimals}f}"


def format_klines_with_indicators(
    klines: list,
    symbol: str,
    interval: str,
    indicators: list[str] | None = None,
) -> str:
    if not klines:
        return f"{symbol} — no data"

    indicators = indicators or []

    # Parse kline data: [open_time, open, high, low, close, volume, ...]
    opens = [float(k[1]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    closes = [float(k[4]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    first_time = _ts_to_str(klines[0][0])
    last_time = _ts_to_str(klines[-1][0])
    price = closes[-1]

    # Determine display precision from price magnitude
    if price >= 1000:
        dp = 2
    elif price >= 1:
        dp = 4
    else:
        dp = 8

    lines = [f"{symbol} {interval} | {len(klines)} candles | {first_time} to {last_time}", ""]

    # Show last N candles (max 15)
    show_count = min(len(klines), 15)
    recent = klines[-show_count:]
    lines.append(f"{'Time':>12}  {'Open':>12}  {'High':>12}  {'Low':>12}  {'Close':>12}  {'Volume':>10}")
    for k in recent:
        t = _ts_to_str(k[0])
        o, h, l, c, v = float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])
        lines.append(
            f"{t:>12}  {o:>12.{dp}f}  {h:>12.{dp}f}  {l:>12.{dp}f}  {c:>12.{dp}f}  {_fmt_num(v):>10}"
        )

    # Indicators
    computed = {}
    if "rsi" in indicators:
        computed["rsi"] = compute_rsi(closes)
    if "macd" in indicators:
        computed["macd"] = compute_macd(closes)
    if "bbands" in indicators:
        computed["bbands"] = compute_bollinger(closes)
    if "sma" in indicators:
        computed["sma"] = compute_sma(closes, 20)

    if computed:
        lines.append("")
        lines.append("Indicators (latest):")

        rsi_val = None
        if "rsi" in computed:
            v = computed["rsi"][-1]
            if v is not None:
                rsi_val = v
                lines.append(f"  RSI(14): {interpret_rsi(v)}")

        macd_hist = None
        if "macd" in computed:
            md = computed["macd"]
            m, s, h = md["macd"][-1], md["signal"][-1], md["histogram"][-1]
            if m is not None and s is not None and h is not None:
                macd_hist = h
                lines.append(f"  MACD(12,26,9): {interpret_macd(m, s, h)}")

        bb_pos = None
        if "bbands" in computed:
            bd = computed["bbands"]
            u, mid, lo = bd["upper"][-1], bd["middle"][-1], bd["lower"][-1]
            if u is not None and mid is not None and lo is not None:
                lines.append(f"  BB(20,2): {interpret_bollinger(price, u, mid, lo)}")
                if u != lo:
                    bb_pos = (price - lo) / (u - lo)

        sma_val = None
        if "sma" in computed:
            v = computed["sma"][-1]
            if v is not None:
                sma_val = v
                diff_pct = ((price - v) / v) * 100
                direction = "above" if diff_pct > 0 else "below"
                lines.append(f"  SMA(20): {v:.{dp}f} — price {direction} by {abs(diff_pct):.1f}%")

        # Signal summary
        lines.append("")
        lines.append(
            "Signal: "
            + generate_signal_summary(rsi_val, macd_hist, bb_pos, price, sma_val)
        )

    return "\n".join(lines)


def format_depth(depth: dict, symbol: str) -> str:
    bids = depth.get("bids", [])
    asks = depth.get("asks", [])

    if not bids or not asks:
        return f"{symbol} — order book empty"

    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    spread = best_ask - best_bid
    spread_pct = (spread / best_ask) * 100 if best_ask else 0

    # Determine display precision
    if best_bid >= 1000:
        dp = 2
    elif best_bid >= 1:
        dp = 4
    else:
        dp = 8

    lines = [f"{symbol} Order Book ({len(bids)} levels)", ""]

    # Asks (reversed so highest is first, best ask is last)
    lines.append(f"{'Asks (sells)':>14}  {'Price':>14}  {'Qty':>12}  {'Cumulative':>12}")
    cum = 0
    ask_rows = []
    for p, q in asks:
        cum += float(q)
        ask_rows.append((float(p), float(q), cum))
    # Show top asks in reverse (highest to lowest)
    display_asks = ask_rows[:min(len(ask_rows), 10)]
    for p, q, c in reversed(display_asks):
        marker = ">>> " if p == best_ask else "    "
        suffix = "  <<< Best Ask" if p == best_ask else ""
        lines.append(f"{marker:>14}  {p:>14.{dp}f}  {_fmt_num(q):>12}  {_fmt_num(c):>12}{suffix}")

    lines.append("")

    # Bids
    lines.append(f"{'Bids (buys)':>14}  {'Price':>14}  {'Qty':>12}  {'Cumulative':>12}")
    cum = 0
    for i, (p, q) in enumerate(bids[:10]):
        cum += float(q)
        marker = ">>> " if i == 0 else "    "
        suffix = "  <<< Best Bid" if i == 0 else ""
        lines.append(f"{marker:>14}  {float(p):>14.{dp}f}  {_fmt_num(float(q)):>12}  {_fmt_num(cum):>12}{suffix}")

    # Summary
    total_bid_qty = sum(float(q) for _, q in bids)
    total_ask_qty = sum(float(q) for _, q in asks)
    ratio = total_bid_qty / total_ask_qty if total_ask_qty > 0 else 0

    lines.append("")
    lines.append(f"Spread: {spread:.{dp}f} ({spread_pct:.3f}%)")
    if ratio > 1.2:
        lines.append(f"Bid/Ask Ratio: {ratio:.2f}x (buy pressure)")
    elif ratio < 0.8:
        lines.append(f"Bid/Ask Ratio: {ratio:.2f}x (sell pressure)")
    else:
        lines.append(f"Bid/Ask Ratio: {ratio:.2f}x (balanced)")

    # Detect walls (largest orders)
    if bids:
        max_bid = max(bids, key=lambda x: float(x[1]))
        lines.append(f"Largest bid wall: {float(max_bid[0]):.{dp}f} ({_fmt_num(float(max_bid[1]))})")
    if asks:
        max_ask = max(asks, key=lambda x: float(x[1]))
        lines.append(f"Largest ask wall: {float(max_ask[0]):.{dp}f} ({_fmt_num(float(max_ask[1]))})")

    return "\n".join(lines)


def format_ticker(ticker: dict) -> str:
    symbol = ticker.get("symbol", "?")
    price = float(ticker.get("lastPrice", 0))
    change = float(ticker.get("priceChangePercent", 0))
    high = float(ticker.get("highPrice", 0))
    low = float(ticker.get("lowPrice", 0))
    volume = float(ticker.get("volume", 0))
    quote_vol = float(ticker.get("quoteVolume", 0))

    direction = "+" if change >= 0 else ""
    return (
        f"{symbol}: {price:.8g} ({direction}{change:.2f}%) "
        f"| H: {high:.8g} L: {low:.8g} | Vol: {_fmt_num(quote_vol)} USDT"
    )


def format_top_movers(tickers: list, direction: str, limit: int, quote_asset: str) -> str:
    # Filter by quote asset
    filtered = [
        t for t in tickers
        if t.get("symbol", "").endswith(quote_asset.upper())
        and float(t.get("quoteVolume", 0)) > 10000  # min volume filter
    ]

    if direction in ("gainers", "both"):
        gainers = sorted(filtered, key=lambda t: float(t.get("priceChangePercent", 0)), reverse=True)[:limit]
    if direction in ("losers", "both"):
        losers = sorted(filtered, key=lambda t: float(t.get("priceChangePercent", 0)))[:limit]

    lines = []
    if direction in ("gainers", "both"):
        lines.append(f"Top {len(gainers)} Gainers ({quote_asset}):")
        for i, t in enumerate(gainers, 1):
            lines.append(f"  {i}. {format_ticker(t)}")

    if direction == "both":
        lines.append("")

    if direction in ("losers", "both"):
        lines.append(f"Top {len(losers)} Losers ({quote_asset}):")
        for i, t in enumerate(losers, 1):
            lines.append(f"  {i}. {format_ticker(t)}")

    return "\n".join(lines) if lines else "No data"


def format_portfolio(account: dict, prices: list) -> str:
    balances = account.get("balances", [])
    non_zero = [
        b for b in balances
        if float(b.get("free", 0)) > 0 or float(b.get("locked", 0)) > 0
    ]

    if not non_zero:
        return "Portfolio is empty — no non-zero balances."

    # Build price lookup (USDT pairs)
    price_map = {}
    for p in prices:
        price_map[p["symbol"]] = float(p["price"])

    lines = ["Portfolio:", ""]
    lines.append(f"{'Asset':>8}  {'Free':>14}  {'Locked':>14}  {'~USD Value':>14}")
    lines.append("-" * 58)

    total_usd = 0.0
    for b in sorted(non_zero, key=lambda x: x["asset"]):
        asset = b["asset"]
        free = float(b["free"])
        locked = float(b["locked"])
        total_qty = free + locked

        # Estimate USD value
        usd_val = 0.0
        if asset in ("USDT", "BUSD", "USDC", "TUSD", "FDUSD"):
            usd_val = total_qty
        elif f"{asset}USDT" in price_map:
            usd_val = total_qty * price_map[f"{asset}USDT"]
        elif f"{asset}BUSD" in price_map:
            usd_val = total_qty * price_map[f"{asset}BUSD"]

        total_usd += usd_val

        lines.append(
            f"{asset:>8}  {free:>14.8g}  {locked:>14.8g}  ${usd_val:>13,.2f}"
        )

    lines.append("-" * 58)
    lines.append(f"{'Total':>8}  {'':>14}  {'':>14}  ${total_usd:>13,.2f}")

    return "\n".join(lines)


def format_order(order: dict) -> str:
    return (
        f"Order #{order.get('orderId')} | {order.get('symbol')} | "
        f"{order.get('side')} {order.get('type')} | "
        f"Qty: {order.get('origQty')} | Price: {order.get('price', 'MARKET')} | "
        f"Status: {order.get('status')} | "
        f"Filled: {order.get('executedQty', '0')}"
    )


def format_trades(trades: list, symbol: str) -> str:
    if not trades:
        return f"No recent trades for {symbol}"

    lines = [f"Recent trades for {symbol}:", ""]
    lines.append(f"{'Time':>12}  {'Side':>5}  {'Price':>14}  {'Qty':>14}  {'Total':>14}")

    for t in trades:
        ts = _ts_to_str(t["time"])
        side = "SELL" if t.get("isBuyer") is False else "BUY"
        price = float(t["price"])
        qty = float(t["qty"])
        total = price * qty
        lines.append(
            f"{ts:>12}  {side:>5}  {price:>14.8g}  {qty:>14.8g}  {total:>14.2f}"
        )

    return "\n".join(lines)
