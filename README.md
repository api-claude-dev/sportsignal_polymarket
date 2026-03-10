# SportSignals

A real-time sports arbitrage bot that exploits information latency between live sports data feeds and prediction market pricing on Polymarket.

## How It Works

Sports results are often known seconds to minutes before prediction market prices update. SportSignals monitors live scores continuously and places trades when outcomes become highly probable but markets have not repriced yet.

## Strategy: Live Score Arbitrage

Edge source: Information latency between sports data feeds and on-chain market pricing.

Flow:
1. Map active Polymarket sports markets to real-world fixtures
2. Poll live scores every 15 seconds via multiple data sources
3. Detect high-probability outcomes (e.g. 2-0 lead in 80th minute, or full-time result confirmed)
4. Calculate fair win probability vs current market price
5. Buy underpriced outcome before the market reprices

## Data Sources

| Source | Usage |
|--------|-------|
| ESPN Live Score API | Real-time scores and match status |
| API-Football | Fixtures, lineups, live events |
| TheSportsDB | Backup score feed and historical data |
| Polymarket Markets API | Current market prices and liquidity |

## Setup

npm install
cp .env.example .env

Configure your .env:

POLYMARKET_API_KEY=
ESPN_API_KEY=
API_FOOTBALL_KEY=
THESPORTSDB_KEY=
POLL_INTERVAL_MS=15000

Never commit your .env file - excluded via .gitignore.

## Project Structure

SportSignals/
|-- sports-bot.js
|-- .env.example
|-- .gitignore
|-- README.md
|-- logs/

## Disclaimer
For educational and research purposes only. Trading prediction markets involves financial risk.
