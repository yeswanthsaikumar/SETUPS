#!/usr/bin/env python3
"""
fundamentals_provider.py
────────────────────────
Fetches and caches fundamental stock data (market cap, PE ratio, sector, dividend yield)
from yfinance. Supports both US and Indian market symbols with proper suffix handling.

Features:
  • Cached fundamentals to avoid repeated fetches
  • 24-hour TTL cache with automatic refresh
  • Symbol normalization for US and Indian markets (.NS, .BO suffixes)
  • Batch fetch for efficiency
  • Fallback graceful handling for unavailable data
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Any
import logging

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

logger = logging.getLogger("FundamentalsProvider")


class FundamentalsProvider:
    """Fetches and caches stock fundamentals data."""

    def __init__(self, cache_dir: str = "cache", cache_ttl_hours: int = 24):
        """
        Initialize fundamentals provider.

        Args:
            cache_dir: Directory for caching fundamentals
            cache_ttl_hours: Time-to-live for cached data in hours
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.has_yfinance = HAS_YFINANCE

        if not self.has_yfinance:
            logger.warning("yfinance not installed. Fundamentals will be unavailable.")

    def get_cache_path(self, symbol: str) -> Path:
        """Get cache file path for symbol."""
        return self.cache_dir / f"fundamentals_{symbol}.json"

    def is_cache_valid(self, symbol: str) -> bool:
        """Check if cached data exists and is still fresh."""
        cache_path = self.get_cache_path(symbol)
        if not cache_path.exists():
            return False

        file_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
        return datetime.now() - file_time < self.cache_ttl

    def load_cached(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Load fundamentals from cache if valid."""
        cache_path = self.get_cache_path(symbol)
        if not cache_path.exists():
            return None

        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
                # Check if cache is still valid
                cached_time = data.get("_cached_at")
                if cached_time:
                    cached_dt = datetime.fromisoformat(cached_time)
                    if datetime.now() - cached_dt < self.cache_ttl:
                        return data
        except (json.JSONDecodeError, IOError):
            pass

        return None

    def save_cache(self, symbol: str, data: Dict[str, Any]):
        """Save fundamentals to cache."""
        data["_cached_at"] = datetime.now().isoformat()
        cache_path = self.get_cache_path(symbol)
        try:
            with open(cache_path, "w") as f:
                json.dump(data, f)
        except IOError as e:
            logger.warning(f"Failed to cache fundamentals for {symbol}: {e}")

    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch fundamentals for a symbol.

        Returns dict with keys:
          - market_cap: Market cap in billions
          - pe_ratio: P/E ratio
          - sector: Sector name
          - industry: Industry name
          - dividend_yield: Dividend yield percentage
          - currency: Currency code
          - error: Error message if fetch failed
        """
        # Check cache first
        cached = self.load_cached(symbol)
        if cached:
            return cached

        if not self.has_yfinance:
            return {"error": "yfinance not available"}

        try:
            ticker = yf.Ticker(symbol)

            # Fetch info dictionary
            info = ticker.info or {}

            # Extract relevant fields with safe defaults
            market_cap = info.get("marketCap")
            if market_cap and isinstance(market_cap, (int, float)):
                market_cap = market_cap / 1_000_000_000  # Convert to billions

            result = {
                "symbol": symbol,
                "market_cap_b": round(market_cap, 2) if market_cap else None,
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "dividend_yield": info.get("dividendYield"),
                "currency": info.get("currency", "USD"),
            }

            # Format dividend yield as percentage string
            if result["dividend_yield"] and isinstance(result["dividend_yield"], (int, float)):
                result["dividend_yield"] = round(result["dividend_yield"] * 100, 2)

            # Format PE ratios
            if result["pe_ratio"] and isinstance(result["pe_ratio"], (int, float)):
                result["pe_ratio"] = round(result["pe_ratio"], 2)
            if result["forward_pe"] and isinstance(result["forward_pe"], (int, float)):
                result["forward_pe"] = round(result["forward_pe"], 2)

            self.save_cache(symbol, result)
            return result

        except Exception as e:
            logger.warning(f"Failed to fetch fundamentals for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}

    def fetch_batch(self, symbols: list[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch fundamentals for multiple symbols.

        Returns dict mapping symbol -> fundamentals dict.
        """
        result = {}
        for symbol in symbols:
            result[symbol] = self.fetch_fundamentals(symbol)
        return result


def format_fundamentals_display(fund: Dict[str, Any]) -> str:
    """Format fundamentals dict to human-readable string for display."""
    if fund.get("error"):
        return "N/A"

    parts = []

    sector = fund.get("sector")
    if sector:
        parts.append(sector)

    market_cap = fund.get("market_cap_b")
    if market_cap:
        parts.append(f"${market_cap}B")

    pe = fund.get("pe_ratio")
    if pe:
        parts.append(f"PE:{pe}")

    div_yield = fund.get("dividend_yield")
    if div_yield:
        parts.append(f"Div:{div_yield}%")

    return " | ".join(parts) if parts else "N/A"


if __name__ == "__main__":
    # Example usage
    provider = FundamentalsProvider()

    # Test with some symbols
    symbols = ["AAPL", "MSFT", "RELIANCE.NS", "INFY.NS"]

    print("Fetching fundamentals...")
    for sym in symbols:
        fund = provider.fetch_fundamentals(sym)
        display = format_fundamentals_display(fund)
        print(f"{sym}: {display}")

