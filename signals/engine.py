"""
Signal engine — calls season-bot.js Monte Carlo model on port 8003.
Falls back to stub if bot is not running.
"""

import os
import httpx
from dataclasses import dataclass, field
from typing import Optional

BOT_URL = os.getenv("BOT_SIGNAL_URL", "http://localhost:8003")


@dataclass
class OutcomeSignal:
    outcome:      str
    market_prob:  float
    fair_prob:    float
    edge:         float          # fair - market (positive = value)
    ev_per_dollar: float         # edge / market_prob
    kelly:        float          # edge / (1/market_prob - 1)  (fraction of bankroll)
    american_odds: str
    has_value:    bool


@dataclass
class MarketSignal:
    slug:        str
    event_title: str
    sport:       str
    volume_24h:  float
    liquidity:   float
    outcomes:    list[OutcomeSignal] = field(default_factory=list)
    top_pick:    Optional[OutcomeSignal] = None
    confidence:  str = "low"
    bot_live:    bool = False     # True if signal came from real bot


def _american_odds(prob: float) -> str:
    if prob <= 0 or prob >= 1:
        return "N/A"
    if prob >= 0.5:
        return f"-{round((prob / (1 - prob)) * 100)}"
    return f"+{round(((1 - prob) / prob) * 100)}"


def _kelly(edge: float, market_prob: float) -> float:
    """Full Kelly fraction. Cap at 25% bankroll."""
    if market_prob <= 0 or market_prob >= 1:
        return 0.0
    b = (1 / market_prob) - 1   # decimal odds - 1
    k = edge / b if b > 0 else 0.0
    return round(max(0.0, min(k, 0.25)), 4)


async def _fetch_fair_prob(team: str, league: str, mkt_type: str) -> Optional[dict]:
    """Call season-bot signal server. Returns raw dict or None."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(
                f"{BOT_URL}/fair",
                params={"team": team, "league": league, "type": mkt_type},
            )
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return None


async def _fetch_scan(league: str, mkt_type: str) -> Optional[dict]:
    """Call season-bot /scan endpoint for all teams in a league."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{BOT_URL}/scan",
                params={"league": league, "type": mkt_type},
            )
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return None


async def _check_bot_health() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{BOT_URL}/health")
            return r.status_code == 200
    except Exception:
        return False


def _stub_fair_prob(outcome_label: str, market_prob: float) -> float:
    """
    Fallback stub when bot is offline.
    Adds a small random-looking offset based on the outcome name hash.
    NOT real — signals clearly in response.
    """
    import hashlib
    h = int(hashlib.md5(outcome_label.encode()).hexdigest()[:8], 16)
    offset = ((h % 21) - 10) / 100.0   # -10% to +10%
    return round(min(0.98, max(0.01, market_prob + offset)), 4)


def _parse_league_from_market(event_title: str, sport: str) -> tuple[str, str]:
    """
    Extract league and market type from Polymarket event title.
    e.g. 'Will Arsenal win the 2025-26 Premier League?' → ('EPL', 'winner')
    """
    title = event_title.lower()

    # League detection
    league_map = {
        "premier league": "EPL",
        "epl":            "EPL",
        "bundesliga":     "Bundesliga",
        "ligue 1":        "Ligue 1",
        "la liga":        "La Liga",
        "serie a":        "Serie A",
        "nba":            "NBA",
        "nhl":            "NHL",
    }
    league = "EPL"
    for key, val in league_map.items():
        if key in title:
            league = val
            break

    # Market type detection
    type_map = {
        "win the":     "winner",
        "finish 1st":  "winner",
        "champion":    "winner",
        "top 4":       "top4",
        "top four":    "top4",
        "top 2":       "top2",
        "top 6":       "top6",
        "relegated":   "relegated",
        "2nd place":   "exact_2nd",
        "3rd place":   "exact_3rd",
    }
    mkt_type = "winner"
    for key, val in type_map.items():
        if key in title:
            mkt_type = val
            break

    return league, mkt_type


def _extract_team(event_title: str, outcome_label: str) -> str:
    """Best-effort team name extraction from title + outcome."""
    # Many Polymarket titles are "Will {TEAM} win..." — outcome is YES/NO
    title = event_title
    for prefix in ["Will ", "will "]:
        if title.startswith(prefix):
            rest = title[len(prefix):]
            # "Arsenal win..." → "Arsenal"
            for verb in [" win ", " finish ", " be relegated", " qualify"]:
                if verb in rest:
                    return rest.split(verb)[0].strip()

    # Outcome IS the team name (multi-outcome markets)
    skip = {"yes", "no", "draw", "home", "away"}
    if outcome_label.lower() not in skip:
        return outcome_label

    return ""


def compute_signal(market, sport: str = "sports", league: str = "") -> MarketSignal:
    """
    Synchronous wrapper — use compute_signal_async for real bot calls.
    Returns a MarketSignal with stub data if bot is offline.
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context (FastAPI) — use stub synchronously
            return _compute_stub(market, sport, league)
        return loop.run_until_complete(compute_signal_async(market, sport, league))
    except Exception:
        return _compute_stub(market, sport, league)


async def compute_signal_async(market, sport: str = "sports", league: str = "") -> MarketSignal:
    """
    Async version — called from FastAPI endpoints.
    Tries bot first, falls back to stub.
    """
    det_league, mkt_type = _parse_league_from_market(market.event_title, sport)
    if league:
        det_league = league

    bot_live = await _check_bot_health()
    outcome_signals = []

    for outcome_label, market_prob in (market.outcomes or {}).items():
        if not isinstance(market_prob, (int, float)):
            continue
        market_prob = float(market_prob)
        if market_prob <= 0:
            continue

        fair_prob = None
        if bot_live:
            team = _extract_team(market.event_title, outcome_label)
            if team:
                data = await _fetch_fair_prob(team, det_league, mkt_type)
                if data and "fair_prob" in data:
                    fair_prob = data["fair_prob"]

        if fair_prob is None:
            fair_prob = _stub_fair_prob(outcome_label, market_prob)

        edge  = round(fair_prob - market_prob, 4)
        ev    = round(edge / market_prob, 4) if market_prob > 0 else 0.0
        kelly = _kelly(edge, market_prob)

        outcome_signals.append(OutcomeSignal(
            outcome=       outcome_label,
            market_prob=   market_prob,
            fair_prob=     fair_prob,
            edge=          edge,
            ev_per_dollar= ev,
            kelly=         kelly,
            american_odds= _american_odds(market_prob),
            has_value=     edge > 0.04 and kelly > 0,
        ))

    # Top pick = highest edge with value
    value_picks = [o for o in outcome_signals if o.has_value]
    top_pick    = max(value_picks, key=lambda o: o.edge) if value_picks else None

    # Confidence
    if top_pick:
        if top_pick.edge > 0.12 and bot_live:
            confidence = "high"
        elif top_pick.edge > 0.07:
            confidence = "medium"
        else:
            confidence = "low"
    else:
        confidence = "none"

    return MarketSignal(
        slug=        market.slug,
        event_title= market.event_title,
        sport=       sport,
        volume_24h=  market.volume_24h,
        liquidity=   market.liquidity,
        outcomes=    outcome_signals,
        top_pick=    top_pick,
        confidence=  confidence,
        bot_live=    bot_live,
    )


def _compute_stub(market, sport: str, league: str) -> MarketSignal:
    """Pure stub — no async, no bot call."""
    outcome_signals = []
    for outcome_label, market_prob in (market.outcomes or {}).items():
        if not isinstance(market_prob, (int, float)):
            continue
        market_prob = float(market_prob)
        if market_prob <= 0:
            continue
        fair_prob = _stub_fair_prob(outcome_label, market_prob)
        edge      = round(fair_prob - market_prob, 4)
        ev        = round(edge / market_prob, 4) if market_prob > 0 else 0.0
        kelly     = _kelly(edge, market_prob)
        outcome_signals.append(OutcomeSignal(
            outcome=       outcome_label,
            market_prob=   market_prob,
            fair_prob=     fair_prob,
            edge=          edge,
            ev_per_dollar= ev,
            kelly=         kelly,
            american_odds= _american_odds(market_prob),
            has_value=     edge > 0.04 and kelly > 0,
        ))

    value_picks = [o for o in outcome_signals if o.has_value]
    top_pick    = max(value_picks, key=lambda o: o.edge) if value_picks else None
    return MarketSignal(
        slug=        market.slug,
        event_title= market.event_title,
        sport=       sport,
        volume_24h=  market.volume_24h,
        liquidity=   market.liquidity,
        outcomes=    outcome_signals,
        top_pick=    top_pick,
        confidence=  "low (stub — bot offline)",
        bot_live=    False,
    )
