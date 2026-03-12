# ultimate-scraper

CLI-based multi-tier web scraper with intelligent tier escalation, AI extraction, CAPTCHA solving, and anti-bot bypass.

## Running

```bash
# Basic scrape
python scripts/scrape.py "https://example.com"

# With AI extraction
python scripts/scrape.py "https://example.com" -e "Extract product names and prices" -o json

# Protected sites (stealth browser + US proxy)
python scripts/scrape.py "https://example.com" -m stealth -g us

# Batch processing
python scripts/scrape.py --batch urls.jsonl -p 10 --output-dir ./results/
```

## Core Loop

1. Detect site profile (protection level, content type)
2. Start at lowest viable tier (or known-good tier from history)
3. Attempt extraction at current tier
4. On failure → rotate proxy → retry → escalate to next tier
5. On CAPTCHA → attempt solve (CapSolver/2Captcha) → escalate if unsolvable
6. Return content as markdown, JSON, or raw HTML

## Tier System

| Tier | Mode | Technology | Use Case |
|------|------|------------|----------|
| 0 | static | chompjs/extruct | `__NEXT_DATA__`, JSON-LD (fastest) |
| 1 | http | curl_cffi | TLS fingerprint spoofing |
| 2 | browser | CloakBrowser/Patchright | Stealth browser + CAPTCHA solving |
| 2.5 | agent | agent-browser CLI | CLI automation + tracker blocking |
| 3 | stealth | Camoufox | Full anti-detect (Cloudflare bypass) |
| 4 | ai | Crawl4AI + LLM | AI-powered extraction |
| 5 | visual | Screenshot + Vision LLM | Visual extraction (bypasses DOM detection) |

Auto-escalation: Tier N fails → rotate proxy → retry → escalate to N+1.

## Decision Tree

```
Simple page, no anti-bot → python scripts/scrape.py "URL"
Need specific data       → python scripts/scrape.py "URL" -e "Extract X" -o json
Protected site           → python scripts/scrape.py "URL" -m stealth -g us
Multiple URLs            → python scripts/scrape.py URL1 URL2 -p 10
URLs from file           → python scripts/scrape.py --batch urls.jsonl -p 10
Save to separate files   → python scripts/scrape.py --batch urls.txt --output-dir ./
Long-running job         → python scripts/scrape.py --batch FILE --output-dir ./ --checkpoint job.json
Detect protection        → python scripts/scrape.py "URL" --probe-only
```

## Key Files

| File | Purpose |
|------|---------|
| `scripts/scrape.py` | CLI entry point |
| `scripts/core/scraper.py` | Main orchestrator, tier escalation, rate limiting |
| `scripts/core/config.py` | Centralized configuration (env vars + YAML) |
| `scripts/core/result.py` | Result types and error classification |
| `scripts/tiers/tier0_static.py` | Static data extraction (`__NEXT_DATA__`, JSON-LD) |
| `scripts/tiers/tier1_http.py` | TLS fingerprint spoofing via curl_cffi |
| `scripts/tiers/tier2_scrapling.py` | CloakBrowser/Patchright stealth browser |
| `scripts/tiers/tier2_5_agentbrowser.py` | agent-browser CLI automation |
| `scripts/tiers/tier3_camoufox.py` | Camoufox anti-detect Firefox |
| `scripts/tiers/tier4_ai.py` | Crawl4AI + LLM extraction |
| `scripts/tiers/tier5_visual.py` | Screenshot + Vision LLM |
| `scripts/extraction/ai_router.py` | 3-tier LLM routing |
| `scripts/proxy/manager.py` | Proxy management with geo-targeting |
| `scripts/detection/` | Site profiling, paywall detection, loop detection |
| `scripts/captcha/solver.py` | CAPTCHA solving (CapSolver + 2Captcha) |
| `scripts/rate_limiting/limiter.py` | Per-domain sliding window rate limiter |
| `scripts/fingerprint/manager.py` | Browser fingerprint persistence |

## Configuration

All settings via environment variables (see `.env.example`) or `config/default.yaml`. Env vars take precedence.

### Proxy

Bring your own proxy. Any HTTP/SOCKS5 proxy provider works:

```bash
PROXY_HOST=your-proxy-host        # Hostname
PROXY_PORT=5000                   # Port
PROXY_USERNAME=your_username      # Auth username
PROXY_PASSWORD=your_password      # Auth password
```

- Proxy is optional — all tiers work without one
- Residential proxies recommended for anti-bot sites
- Geo-targeting via `-g us`, `-g uk`, `-g de`, etc.
- GeoIP timezone/locale auto-correlation when proxy is configured

### AI Extraction

3-tier LLM routing for `--extract` mode:

```bash
# Tier 1: Any OpenAI-compatible local LLM (free)
LOCAL_LLM_URL=http://localhost:8080/v1/chat/completions
LOCAL_LLM_ENABLED=true

# Tier 2: z.ai GLM-4.5-Air (rate-limited)
ZAI_API_KEY=your_key

# Tier 3: Anthropic Claude Haiku (paid fallback)
ANTHROPIC_API_KEY=your_key
```

### CAPTCHA Solving

```bash
CAPSOLVER_API_KEY=your_key        # AI solver (fast, ~$1-3/1000)
TWOCAPTCHA_API_KEY=your_key       # Human fallback (slower, broadest coverage)
```

Without keys, CAPTCHAs trigger tier escalation.

## Error Handling

| Error | Auto-Handled | Action |
|-------|--------------|--------|
| Blocked | Yes | Rotates proxy, escalates tier |
| CaptchaRequired | Yes | Solves via CapSolver/2Captcha, then escalates |
| PaywallDetected | No | Exit 2 |
| NotFound | No | Exit 1 (page doesn't exist) |
| RateLimited | Yes | Waits, rotates proxy, retries |
| Timeout | Yes | Retries once, then escalates |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Failed (all tiers exhausted or page not found) |
| 2 | Requires premium proxy/unlocker service |
| 130 | Interrupted |

## Rate Limiting

Browser tiers (2+) enforce per-domain sliding window rate limits. Sensitive sites (LinkedIn, Instagram, Facebook, X/Twitter, TikTok) have lower thresholds. Disable with `--no-rate-limit`.

## Testing

```bash
cd scripts
python -m pytest tests/ -v

# Unit tests only (~5s)
python -m pytest tests/unit/ -v

# With coverage
python -m pytest tests/ --cov=. --cov-report=html
```

## Dependencies

```bash
pip install scrapling camoufox crawl4ai curl_cffi chompjs extruct \
  html2text beautifulsoup4 lxml httpx pyyaml python-dotenv

# Optional: CloakBrowser (C++ patched Chromium for enhanced stealth)
pip install cloakbrowser

# Optional: CAPTCHA solving
# Configure via CAPSOLVER_API_KEY or TWOCAPTCHA_API_KEY env vars

# Test dependencies
pip install pytest pytest-asyncio pytest-cov
```

Note: First Camoufox run downloads ~780MB browser package.
