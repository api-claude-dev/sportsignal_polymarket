"""
SportSignals API — Polymarket odds + season bot model signals
Gated with x402: pay per query in USDC on Base chain.

Endpoints:
  GET /                         Free  — health check + docs
  GET /markets                  Free  — list live sports markets on Polymarket
  GET /signal/{slug}            $0.005 — full signal for one market
  GET /scan/{sport}             $0.01  — scan all markets for a sport, return value bets
  GET /search?q=...             $0.003 — search by team/event name
"""

import os
import sys
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from polymarket.client import (
    get_live_sports_markets,
    search_sports_markets,
    get_market_by_slug,
)
from signals.engine import compute_signal_async
from signals.formatter import format_signal, format_signal_list

# ── Configuration ─────────────────────────────────────────────────────────────
X402_ENABLED = os.getenv("X402_ENABLED", "false").lower() == "true"
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "")
X402_NETWORK = os.getenv("X402_NETWORK", "base-sepolia")

# EVM chain IDs: base-sepolia = eip155:84532, base mainnet = eip155:8453
NETWORK_CHAIN_ID = "eip155:84532" if "sepolia" in X402_NETWORK else "eip155:8453"

app = FastAPI(
    title="SportSignals API",
    description=(
        "Polymarket sports odds + AI model edge signals.\n\n"
        "Compares Polymarket implied probabilities against a sports prediction model "
        "to surface value bets with edge, EV, and Kelly fraction.\n\n"
        "Payments: USDC on Base via x402 protocol."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── x402 payment middleware ───────────────────────────────────────────────────
if X402_ENABLED:
    try:
        from x402.http.middleware.fastapi import PaymentMiddlewareASGI
        from x402.http import HTTPFacilitatorClient, FacilitatorConfig, PaymentOption
        from x402.http.types import RouteConfig
        from x402.server import x402ResourceServer
        from x402.mechanisms.evm.exact import ExactEvmServerScheme

        if not WALLET_ADDRESS:
            raise ValueError("WALLET_ADDRESS must be set in .env")

        facilitator_url = "https://x402.org/facilitator"
        server = x402ResourceServer(
            HTTPFacilitatorClient(FacilitatorConfig(url=facilitator_url))
        )
        server.register(NETWORK_CHAIN_ID, ExactEvmServerScheme())

        routes = {
            "GET /signal/{slug}": RouteConfig(
                accepts=[
                    PaymentOption(
                        scheme="exact",
                        price="$0.005",
                        network=NETWORK_CHAIN_ID,
                        pay_to=WALLET_ADDRESS,
                    )
                ]
            ),
            "GET /scan/{sport}": RouteConfig(
                accepts=[
                    PaymentOption(
                        scheme="exact",
                        price="$0.01",
                        network=NETWORK_CHAIN_ID,
                        pay_to=WALLET_ADDRESS,
                    )
                ]
            ),
            "GET /search": RouteConfig(
                accepts=[
                    PaymentOption(
                        scheme="exact",
                        price="$0.003",
                        network=NETWORK_CHAIN_ID,
                        pay_to=WALLET_ADDRESS,
                    )
                ]
            ),
        }

        app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)

        print(f" x402 payments ENABLED on {X402_NETWORK} ({NETWORK_CHAIN_ID})")
        print(f" Receiving wallet: {WALLET_ADDRESS}")
        print(f" Facilitator: {facilitator_url}")

    except ImportError as e:
        print(f" WARNING: x402 import failed: {e}")
        print(" Run: pip install x402[fastapi,evm]")
        X402_ENABLED = False
    except Exception as e:
        print(f" WARNING: x402 setup failed: {e}")
        X402_ENABLED = False
else:
    print(" x402 payments: DISABLED (free mode)")


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", tags=["Info"])
async def root():
    return {
        "service":      "SportSignals API",
        "version":      "1.0.0",
        "description":  "Polymarket sports odds + model edge signals",
        "x402_enabled": X402_ENABLED,
        "network":      X402_NETWORK if X402_ENABLED else "disabled",
        "chain_id":     NETWORK_CHAIN_ID if X402_ENABLED else "n/a",
        "wallet":       WALLET_ADDRESS or "not configured",
        "endpoints": {
            "GET /markets?sport=soccer": "free   — list live Polymarket sports markets",
            "GET /signal/{slug}":        "$0.005 — full signal for one market",
            "GET /scan/{sport}":         "$0.01  — scan sport for value bets",
            "GET /search?q=arsenal":     "$0.003 — search by team/event name",
            "GET /docs":                 "free   — interactive API docs",
        },
        "supported_sports": ["soccer", "nba", "nfl", "tennis"],
    }


@app.get("/health", tags=["Info"])
async def health():
    return {
        "status":       "ok",
        "x402_enabled": X402_ENABLED,
        "wallet":       WALLET_ADDRESS or "not configured",
        "network":      X402_NETWORK,
    }


@app.get("/markets", tags=["Markets"])
async def list_markets(
    sport: str = Query(None, description="Filter by sport: soccer, nba, nfl, tennis"),
    limit: int = Query(20, ge=1, le=50),
):
    """FREE — List active sports markets on Polymarket. Use slugs with /signal/{slug}."""
    try:
        markets = await get_live_sports_markets(sport=sport, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Polymarket API error: {e}")

    return {
        "count":        len(markets),
        "sport_filter": sport or "all",
        "markets": [
            {
                "title":      m.event_title,
                "slug":       m.slug,
                "url":        m.url,
                "volume_24h": f"${m.volume_24h:,.0f}",
                "liquidity":  f"${m.liquidity:,.0f}",
                "end_date":   m.end_date,
                "outcomes":   m.outcomes,
            }
            for m in markets
        ],
    }


@app.get("/bot", tags=["Info"])
async def bot_status():
    """FREE — Check if the season-bot Monte Carlo model is live."""
    try:
        async with __import__("httpx").AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{__import__('os').getenv('BOT_SIGNAL_URL','http://localhost:8003')}/health")
            if r.status_code == 200:
                data = r.json()
                return {"bot_live": True, **data}
    except Exception:
        pass
    return {"bot_live": False, "reason": "season-bot not reachable on port 8003"}


@app.get("/scan-bot/{league}", tags=["Signals"])
async def scan_bot_direct(
    league: str,
    type: str = Query("winner", description="Market type: winner, top4, top2, relegated"),
):
    """
    FREE preview — Direct scan from the season-bot Monte Carlo model.
    Returns fair probabilities for all teams in a league.
    No Polymarket price comparison — raw model output only.
    League: EPL, Bundesliga, 'Ligue 1'
    """
    import httpx, os
    bot_url = os.getenv("BOT_SIGNAL_URL", "http://localhost:8003")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{bot_url}/scan", params={"league": league, "type": type})
            if r.status_code == 200:
                return r.json()
            raise HTTPException(status_code=r.status_code, detail=r.text)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="season-bot not reachable — is it running?")



async def get_signal(
    slug: str,
    sport: str = Query("sports", description="sport context for model"),
    league: str = Query("", description="league name for model context"),
):
    """
    PAID ($0.005 USDC) — Full signal for one Polymarket market.
    Get slugs from GET /markets or polymarket.com/event/{slug}.
    """
    poly = await get_market_by_slug(slug)
    if not poly:
        raise HTTPException(status_code=404, detail=f"Market '{slug}' not found on Polymarket")

    signal = await compute_signal_async(poly, sport=sport, league=league)
    return format_signal(signal)


@app.get("/scan/{sport}", tags=["Signals"])
async def scan_sport(
    sport: str,
    limit: int = Query(20, ge=1, le=50),
    min_edge: float = Query(0.04, description="Minimum edge % to include (default 4%)"),
    min_volume: float = Query(1000, description="Minimum 24h volume in USD"),
):
    """
    PAID ($0.01 USDC) — Scan all active Polymarket markets for a sport,
    return only markets where the model detects edge.
    Sports: soccer, nba, nfl, tennis
    """
    if sport not in ["soccer", "nba", "nfl", "tennis", "sports"]:
        raise HTTPException(status_code=400, detail=f"Unsupported sport: {sport}")

    try:
        markets = await get_live_sports_markets(sport=sport, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Polymarket API error: {e}")

    signals = [await compute_signal_async(m, sport=sport) for m in markets]

    for sig in signals:
        if sig.top_pick:
            if sig.top_pick.edge < min_edge or sig.volume_24h < min_volume:
                sig.top_pick = None

    return format_signal_list(signals)


@app.get("/search", tags=["Signals"])
async def search(
    q: str = Query(..., description="Team name, event, or league to search"),
    sport: str = Query(None, description="Narrow by sport"),
    limit: int = Query(10, ge=1, le=30),
):
    """
    PAID ($0.003 USDC) — Search Polymarket for a team or event, return signals.
    Example: /search?q=arsenal&sport=soccer
    """
    try:
        markets = await search_sports_markets(query=q, sport=sport, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Polymarket API error: {e}")

    if not markets:
        return {"query": q, "results": 0, "signals": []}

    signals = [await compute_signal_async(m, sport=sport or "sports") for m in markets]
    result = format_signal_list(signals)
    result["query"] = q
    return result


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8001))
    print(f"\n SportSignals API starting on port {port}")
    print(f" Wallet: {WALLET_ADDRESS or 'not set'}")
    print(f" Public URL: {os.getenv('API_BASE_URL', 'http://localhost:' + str(port))}")
    print(f"\n Docs: http://localhost:{port}/docs")
    print(f" Markets: http://localhost:{port}/markets\n")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True, loop="asyncio")
