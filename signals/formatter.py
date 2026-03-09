"""Clean JSON response formatting for signal outputs."""

from .engine import MarketSignal, OutcomeSignal


def _fmt_outcome(o: OutcomeSignal) -> dict:
    return {
        "outcome":       o.outcome,
        "market_prob":   f"{o.market_prob*100:.1f}%",
        "fair_prob":     f"{o.fair_prob*100:.1f}%",
        "edge":          f"{o.edge*100:+.1f}%",
        "ev_per_dollar": f"{o.ev_per_dollar:+.3f}",
        "kelly":         f"{o.kelly*100:.1f}% of bankroll",
        "american_odds": o.american_odds,
        "has_value":     o.has_value,
    }


def _star_rating(edge: float) -> str:
    if edge >= 0.15: return "★★★★★"
    if edge >= 0.12: return "★★★★☆"
    if edge >= 0.08: return "★★★☆☆"
    if edge >= 0.05: return "★★☆☆☆"
    return "★☆☆☆☆"


def format_signal(sig: MarketSignal) -> dict:
    top = sig.top_pick
    signal_block = None
    if top:
        signal_block = {
            "summary":   (
                f"Model sees {top.edge*100:+.1f}% edge on '{top.outcome}' "
                f"(market: {top.market_prob*100:.0f}% → model: {top.fair_prob*100:.0f}%)"
            ),
            "top_pick": {
                "bet":          top.outcome,
                "edge":         f"{top.edge*100:+.1f}%",
                "ev_per_dollar":f"{top.ev_per_dollar:+.3f}",
                "kelly":        f"{top.kelly*100:.1f}% of bankroll",
                "american_odds":top.american_odds,
                "rating":       _star_rating(top.edge),
            },
            "confidence": sig.confidence,
        }
    else:
        signal_block = {
            "summary":    "No value detected — market appears efficiently priced",
            "top_pick":   None,
            "confidence": "none",
        }

    return {
        "event":        sig.event_title,
        "sport":        sig.sport,
        "model_source": "season-bot Monte Carlo" if sig.bot_live else "stub (bot offline)",
        "signal":       signal_block,
        "all_outcomes": [_fmt_outcome(o) for o in sig.outcomes],
        "market_info": {
            "slug":         sig.slug,
            "volume_24h":   f"${sig.volume_24h:,.0f}",
            "liquidity":    f"${sig.liquidity:,.0f}",
        },
    }


def format_signal_list(signals: list[MarketSignal]) -> dict:
    value_sigs  = [s for s in signals if s.top_pick]
    no_value    = [s for s in signals if not s.top_pick]

    return {
        "total_markets": len(signals),
        "value_bets":    len(value_sigs),
        "bot_live":      any(s.bot_live for s in signals),
        "signals": [
            {
                "event":      s.event_title,
                "slug":       s.slug,
                "top_pick":   {
                    "bet":    s.top_pick.outcome,
                    "edge":   f"{s.top_pick.edge*100:+.1f}%",
                    "kelly":  f"{s.top_pick.kelly*100:.1f}%",
                    "rating": _star_rating(s.top_pick.edge),
                } if s.top_pick else None,
                "confidence": s.confidence,
                "volume_24h": f"${s.volume_24h:,.0f}",
            }
            for s in (value_sigs + no_value)
        ],
    }
