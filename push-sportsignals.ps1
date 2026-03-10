# ============================================================
#  push-sportsignals.ps1
#  Pushes C:\Users\ktguk\Downloads\SportSignals to GitHub
#
#  HOW TO RUN:
#    powershell -ExecutionPolicy Bypass -File "C:\Users\ktguk\Downloads\SportSignals\push-sportsignals.ps1"
# ============================================================

$GITHUB_USER = "api-claude-dev"
$REPO_NAME   = "SportSignals"
$LOCAL_PATH  = "C:\Users\ktguk\Downloads\SportSignals"

if (-not $env:GITHUB_TOKEN) {
    Write-Error "ERROR: GITHUB_TOKEN not set. Run: `$env:GITHUB_TOKEN = 'your_token_here'"
    exit 1
}

# 1. Create repo on GitHub
Write-Host "[1/4] Creating GitHub repo '$REPO_NAME'..." -ForegroundColor Cyan
$body = @{
    name        = $REPO_NAME
    description = "Live sports arbitrage bot - detects game result latency between sports feeds and Polymarket pricing"
    private     = $false
    auto_init   = $false
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri "https://api.github.com/user/repos" `
    -Method POST `
    -Headers @{ Authorization = "token $env:GITHUB_TOKEN"; Accept = "application/vnd.github.v3+json" } `
    -Body $body `
    -ContentType "application/json" `
    -ErrorAction SilentlyContinue | Out-Null

Write-Host "    Done (or repo already exists)." -ForegroundColor Green

# 2. Write .gitignore
Write-Host "[2/4] Writing .gitignore..." -ForegroundColor Cyan
$gitignore = ".env`n.env.*`n*.env`nlogs/`n*.log`nnode_modules/`nnpm-debug.log*`n.DS_Store`nThumbs.db"
Set-Content "$LOCAL_PATH\.gitignore" -Value $gitignore -Encoding UTF8

# 3. Write README
Write-Host "[2b/4] Writing README.md..." -ForegroundColor Cyan
$readme = @"
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
"@
Set-Content "$LOCAL_PATH\README.md" -Value $readme -Encoding UTF8
Write-Host "    Files written." -ForegroundColor Green

# 3. Git commit
Write-Host "[3/4] Git init and commit..." -ForegroundColor Cyan
Set-Location $LOCAL_PATH
git init
git add .
git commit -m "Initial commit: SportSignals live arbitrage bot"

# 4. Push
Write-Host "[4/4] Pushing to GitHub..." -ForegroundColor Cyan
$remote = "https://$($env:GITHUB_TOKEN)@github.com/$GITHUB_USER/$REPO_NAME.git"
git remote remove origin 2>$null
git remote add origin $remote
git branch -M main
git push -u origin main

# Sanitise remote URL
git remote set-url origin "https://github.com/$GITHUB_USER/$REPO_NAME.git"

Write-Host "DONE: https://github.com/$GITHUB_USER/$REPO_NAME" -ForegroundColor Green
Write-Host "Token removed from git remote config." -ForegroundColor DarkGray
