"""
Polymarket Gamma + CLOB API client.
Fetches live sports markets, outcomes, and prices.
"""

import httpx
from dataclasses import dataclass, field
from typing import Optional

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL  = "https://clob.polymarket.com"

SPORTS_KEYWORDS = [
    "premier league", "bundesliga", "ligue 1", "la liga", "serie a",
    "champions league", "nba", "nfl", "nhl", "tennis", "world cup",
    "epl", "soccer", "football", "basketball", "hockey",
    "win the", "finish", "relegated", "top 4", "top four",
    "arsenal", "chelsea", "manchester", "liverpool", "barcelona", "real madrid",
]


@dataclass
class PolyMarket:
    slug:        str
    event_title: str
    url:         str
    volume_24h:  float
    liquidity:   float
    end_date:    str
    outcomes:    dict   # {label: implied_prob}
    best_ask:    Optional[float] = None


async def _get(url: str, params: dict = None) -> dict | list | None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        print(f"[polymarket] HTTP error: {e}")
        return None


def _is_sports(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in SPORTS_KEYWORDS)


def _parse_market(raw: dict) -> Optional[PolyMarket]:
    try:
        title = raw.get("question") or raw.get("title") or ""
        slug  = raw.get("slug") or raw.get("conditionId") or ""
        if not title or not slug:
            return None

        # Outcomes — try tokens array first, then outcomes array
        outcomes = {}
        tokens = raw.get("tokens") or []
        for tok in tokens:
            label = tok.get("outcome", "")
            price = float(tok.get("price", 0))
            if label:
                outcomes[label] = round(price, 4)

        if not outcomes:
            for o in (raw.get("outcomes") or []):
                if isinstance(o, dict):
                    outcomes[o.get("value", "")] = round(float(o.get("probability", 0)), 4)
                elif isinstance(o, str):
                    outcomes[o] = 0.5  # no price available

        vol  = float(raw.get("volume24hr") or raw.get("volume") or 0)
        liq  = float(raw.get("liquidity")  or 0)
        end  = raw.get("endDate") or raw.get("endDateIso") or ""

        return PolyMarket(
            slug=        slug,
            event_title= title,
            url=         f"https://polymarket.com/event/{slug}",
            volume_24h=  vol,
            liquidity=   liq,
            end_date=    end,
            outcomes=    outcomes,
            best_ask=    None,
        )
    except Exception:
        return None


async def get_live_sports_markets(sport: str = None, limit: int = 20) -> list[PolyMarket]:
    """Fetch active sports markets from Polymarket Gamma API."""
    params = {
        "active":   "true",
        "closed":   "false",
        "limit":    min(limit * 3, 100),   # fetch extra, filter down
        "order":    "volume24hr",
        "ascending":"false",
    }
    if sport:
        params["tag"] = sport

    data = await _get(f"{GAMMA_URL}/markets", params)
    if not data:
        return []

    markets = []
    for raw in (data if isinstance(data, list) else data.get("markets", [])):
        m = _parse_market(raw)
        if m and _is_sports(m.event_title):
            markets.append(m)
        if len(markets) >= limit:
            break

    return markets


async def search_sports_markets(query: str, sport: str = None, limit: int = 10) -> list[PolyMarket]:
    """Search Polymarket markets by keyword."""
    params = {
        "active":  "true",
        "closed":  "false",
        "limit":   50,
        "order":   "volume24hr",
        "ascending": "false",
    }
    data = await _get(f"{GAMMA_URL}/markets", params)
    if not data:
        return []

    q = query.lower()
    results = []
    for raw in (data if isinstance(data, list) else data.get("markets", [])):
        title = (raw.get("question") or raw.get("title") or "").lower()
        if q in title:
            m = _parse_market(raw)
            if m:
                results.append(m)
        if len(results) >= limit:
            break

    return results


async def get_market_by_slug(slug: str) -> Optional[PolyMarket]:
    """Fetch a single market by slug."""
    data = await _get(f"{GAMMA_URL}/markets", {"slug": slug})
    if not data:
        return None
    items = data if isinstance(data, list) else data.get("markets", [])
    if not items:
        return None
    return _parse_market(items[0])
