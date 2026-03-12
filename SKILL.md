---
name: ultimate-scraper
description: Scrapes web pages with intelligent tier escalation and AI extraction. Use when user provides a URL and needs to extract content, bypass anti-bot protection, or parse protected pages. Handles static data extraction (__NEXT_DATA__, JSON-LD), TLS fingerprint spoofing, stealth browsers (CloakBrowser + Patchright), Cloudflare bypass, CAPTCHA solving, proxy rotation, rate limiting, session persistence, fingerprint persistence, visual extraction, behavioral simulation, tracker blocking, shadow DOM piercing, WebMCP extraction, and LLM-powered data extraction.
allowed-tools: Bash(python*)
version: 2.0.0
compatibility: python>=3.8
triggers:
  - scrape
  - extract
  - crawl
  - fetch
  - web scraping
  - anti-bot
  - cloudflare bypass
---

# Ultimate Web Scraper

## Quick Start

```bash
python scripts/scrape.py "https://example.com"
```

With AI extraction:

```bash
python scripts/scrape.py "https://example.com" \
  -e "Extract all product names and prices" -o json
```

## Workflow

### 1. Basic Scrape

```bash
python scripts/scrape.py "URL"
```

Output: Markdown content to stdout.

### 2. With AI Extraction

```bash
python scripts/scrape.py "URL" \
  -e "Natural language instruction" -o json
```

Output: JSON with `data` field containing extracted info.

### 3. Protected Sites

```bash
python scripts/scrape.py "URL" \
  -m stealth -g us
```

Output: Content fetched via Camoufox + US residential proxy.

### 4. Handle Failures

If exit code 2 (premium proxy required), use your preferred unlocker/proxy service.

## Decision Tree

```
User wants to scrape?
├─ Simple page, no anti-bot → python scripts/scrape.py "URL"
├─ Need specific data → python scripts/scrape.py "URL" -e "Extract X" -o json
├─ Protected site → python scripts/scrape.py "URL" -m stealth -g us
├─ Multiple URLs → python scripts/scrape.py URL1 URL2 -p 10
├─ URLs from file → python scripts/scrape.py --batch urls.jsonl -p 10
├─ Save to separate files → python scripts/scrape.py --batch urls.txt --output-dir ./articles/
├─ Long-running job → python scripts/scrape.py --batch FILE --output-dir ./ --checkpoint job.json
├─ Exit code 1 + NotFound → Page doesn't exist (404), no action needed
├─ Exit code 2 → Requires premium proxy/unlocker service
└─ Detect protection → python scripts/scrape.py "URL" --probe-only
```

## CLI Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--mode MODE` | `-m` | auto\|static\|http\|browser\|agent\|stealth\|ai\|visual | auto |
| `--output FMT` | `-o` | markdown\|json\|raw | markdown |
| `--json` | `-j` | Alias for `-o json` | |
| `--extract PROMPT` | `-e` | Natural language extraction instruction | |
| `--schema JSON` | `-s` | JSON schema for structured extraction | |
| `--visual` | | Enable visual extraction (screenshot + Vision LLM) | false |
| `--proxy-geo GEO` | `-g` | us, uk, de, us-newyork, uk-london, etc. | |
| `--proxy-sticky` | | Same IP across requests | false |
| `--session NAME` | | Named session for cookie persistence | |
| `--max-tier N` | | Limit escalation (0-5) | 4 |
| `--timeout SEC` | `-t` | Request timeout in seconds | 30 |
| `--no-cache` | | Bypass 24h cache | false |
| `--verbose` | `-v` | Show tier progression | false |
| `--probe-only` | | Detect site profile only | false |
| `--parallel N` | `-p` | Concurrent scrapes (batch mode) | 5 |
| `--batch FILE` | | Read URLs from file (JSONL or text) | |
| `--batch-output FILE` | | JSONL output for batch (after completion) | |
| `--output-stream FILE` | | Stream results to JSONL (as each completes) | |
| `--output-dir DIR` | | Write each result to separate file in directory | |
| `--output-ext EXT` | | File extension for --output-dir (default: md) | md |
| `--checkpoint FILE` | | Resume file for long-running jobs | |
| `--import-state FILE` | | Import agent-browser state | |
| `--export-state FILE` | | Export state for agent-browser | |
| `--actions JSON` | | Browser actions array | |
| `--wait-for SEL` | | CSS selector to wait for | |
| `--behavior-intensity N` | | Behavioral simulation intensity (0.5-2.0) | 1.0 |
| `--no-rate-limit` | | Disable per-domain rate limiting | false |
| `--no-trackers` | | Disable tracker/fingerprinter blocking | false |
| `--captcha-solve` | | Force CAPTCHA solving attempt | false |

## Architecture

| Component | Implementation |
|-----------|----------------|
| Static extraction | chompjs + extruct (__NEXT_DATA__, JSON-LD) |
| TLS spoofing | curl_cffi + BrowserForge headers |
| Light stealth | CloakBrowser (C++ patches, preferred) + Patchright fallback |
| Tracker blocking | CDP network interception (25 patterns, all browser tiers) |
| Full anti-detect | Camoufox (C++ fingerprint spoofing) |
| CAPTCHA solving | CapSolver (AI) + 2Captcha (human) with auto-detection |
| Visual extraction | Screenshot + Vision LLM |
| AI extraction | Crawl4AI + 3-tier LLM routing |
| WebMCP extraction | Chrome 147+ navigator.modelContext tool discovery |
| Proxy | Bring-your-own residential/mobile proxy |
| Cache | SQLite, 24h TTL |
| Sessions | SQLite-backed, auto-persist on anti-bot |
| Fingerprint persistence | SQLite-backed, per-domain consistent identity |
| Tier history | Per-domain tier success tracking for faster starts |
| Behavioral simulation | Bezier curves, human typing, reading pauses |
| Rate limiting | Per-domain sliding window (60s) for browser tiers |
| Sensitive sites | Auto-detected (LinkedIn, X, etc.) with enhanced stealth |
| Loop detection | Action loop detector (WARNING/STUCK/CRITICAL thresholds) |
| Shadow DOM | Recursive deepQuery/deepQueryAll for piercing shadow roots |
| JA4T detection | Transport-layer fingerprint detection, auto-skip Tier 1 |

### Tier System

| Tier | Mode | Technology | Use Case |
|------|------|------------|----------|
| 0 | static | chompjs/extruct | __NEXT_DATA__, JSON-LD (fastest) |
| 1 | http | curl_cffi | TLS fingerprint spoofing |
| 2 | browser | CloakBrowser/Patchright | Stealth browser (CAPTCHA solving) |
| 2.5 | agent | agent-browser | CLI automation + tracker blocking |
| 3 | stealth | Camoufox | Full anti-detect (Cloudflare bypass) |
| 4 | ai | Crawl4AI + LLM | AI-powered extraction |
| 5 | visual | Screenshot + Vision | Visual LLM extraction (bypasses DOM detection) |

Auto-escalation: Tier N fails → rotate proxy → retry → escalate to N+1.

### JA4T Detection

Sites using transport-layer fingerprinting (JA4T) are automatically detected. When JA4T is detected:
- Tier 1 (HTTP with TLS spoofing) is skipped
- Starts at Tier 2 (browser) minimum
- Verbose mode shows: `[JA4T] Skipping Tier 1 - transport-layer fingerprinting detected`

### CAPTCHA Solving

When a CAPTCHA is encountered at Tier 2 or 3:
1. Detects type (reCAPTCHA v2/v3, hCaptcha, Cloudflare Turnstile)
2. Extracts sitekey from page
3. Sends to CapSolver (AI, ~5s) or 2Captcha (human, ~30s) for solving
4. Injects token into page and continues

Requires `CAPSOLVER_API_KEY` or `TWOCAPTCHA_API_KEY` env var. Without keys, CAPTCHAs trigger tier escalation as before.

### CloakBrowser

Tier 2 prefers CloakBrowser (C++ patched Chromium with 26 source-level patches) over Patchright. Falls back to Patchright if CloakBrowser is not installed. Set `CLOAKBROWSER_ENABLED=0` to force Patchright.

### Per-Domain Rate Limiting

Browser tiers (2+) enforce per-domain rate limits via sliding window (60s). Default: 8 req/min. Sensitive sites have lower limits (LinkedIn: 4, Instagram: 4, Facebook: 5). Disable with `--no-rate-limit`.

### Sensitive Site Mode

Sites like LinkedIn, X/Twitter, Facebook, Instagram, TikTok are auto-detected as sensitive:
- Minimum tier 2 (browser) in auto mode
- Fingerprint rotation locked (no rotation on block)
- Behavior intensity boosted (minimum 1.3x)
- Rate limits enforced at lower thresholds

### Tier History

Successful tier usage is tracked per domain. On repeat visits, auto mode starts at the lowest known-good tier (requires 3+ successes with 80%+ success ratio). This skips unnecessary lower-tier attempts.

### Fingerprint Persistence

Consistent browser fingerprints per domain:
- Same browser/version for each domain (not randomized)
- Fingerprints stored in SQLite, linked to sessions
- Auto-rotation after blocks or 30+ days
- Market-share weighted browser selection by geo

### LLM Routing (--extract)

The default fallback chain reflects the developer's setup. **Models and providers are user preference** — modify `scripts/extraction/ai_router.py` to wire in your own. Any OpenAI-compatible API works for Tier 1.

Recommended local model: [GLM-4.7-Flash-UD Q4](https://huggingface.co/THUDM/glm-4-9b-hf) via vLLM/llama.cpp, or any instruction-following model with JSON output (Qwen 2.5, Llama 3.1, Mistral, etc.).

```
1. Local LLM (any OpenAI-compatible API) → configure via LOCAL_LLM_URL
   ↓ unavailable
2. z.ai GLM-4.5-Air → configure via ZAI_API_KEY
   ↓ rate limited
3. Claude Haiku → configure via ANTHROPIC_API_KEY
```

## Error Handling

| Error | Auto-Handled | Action |
|-------|--------------|--------|
| Blocked | Yes | Rotates proxy, escalates tier |
| CaptchaRequired | Yes | Solves via CapSolver/2Captcha, then escalates |
| PaywallDetected | No | Exit 2 → Use premium proxy/unlocker service |
| NotFound | No | Exit 1 → Page doesn't exist (verified via HEAD request) |
| RateLimited | Yes | Waits 5s, rotates proxy, retries |
| Timeout | Yes | Retries once, then escalates |
| LoginRequired | Informational | Not actionable |

### 404 Detection

Pages that don't exist are detected via:
1. HTTP 404 status code (99% confidence)
2. Content patterns ("page not found", "404", etc.) + HEAD request verification

When detected:
- Marked as failed with `error_type="NotFound"`
- Does NOT trigger fallback (page genuinely doesn't exist)
- Skipped in batch processing (won't waste retries)

### Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | Parse output |
| 1 | Failed (all tiers exhausted or NotFound) | Report failure |
| 2 | Premium proxy required | Use unlocker service |
| 130 | Interrupted | User cancelled |

## Output Formats

### markdown (default)

Clean markdown converted from HTML via html2text. Best for reading/summarizing.

### json

```json
{
  "success": true,
  "url": "...",
  "final_url": "...",
  "tier_used": 1,
  "data": { ... },
  "static_data": { ... },
  "markdown": "...",
  "metadata": { ... }
}
```

### raw

Raw HTML. Use when processing HTML directly.

## Examples

### E-commerce Product

```bash
python scripts/scrape.py \
  "https://amazon.com/dp/B0ABC123" \
  -m stealth -g us \
  -e "Extract product name, price, rating, review count" -j
```

### News Article (Potential Paywall)

```bash
python scripts/scrape.py \
  "https://nytimes.com/article" \
  -e "Extract title, author, date, full text" -j
```

If exit code 2: use premium proxy/unlocker service.

### Recipe (Structured Data)

```bash
python scripts/scrape.py \
  "https://recipe-site.com/cake" \
  -m static -j
```

Returns JSON-LD recipe schema if available.

### Visual Extraction (Screenshot + Vision LLM)

For heavily protected pages or canvas-rendered content:

```bash
python scripts/scrape.py \
  "https://protected-site.com/data" \
  --visual -e "Extract all prices and product names visible on the page" -j
```

Visual extraction:
- Takes full-page screenshot using Tier 3 (Camoufox)
- Extracts data using Vision LLM
- Bypasses DOM monitoring/mutation detection
- Works on canvas-rendered or heavily obfuscated pages

### Multi-page Session

```bash
# Login and save session
python scripts/scrape.py \
  "https://site.com/login" --session acct -m stealth \
  --actions '[{"type":"fill","selector":"#email","text":"user@example.com"},{"type":"fill","selector":"#pass","text":"xxx"},{"type":"click","selector":"#submit"}]'

# Reuse session
python scripts/scrape.py \
  "https://site.com/dashboard" --session acct -e "Extract user data" -j
```

### Batch Processing

```bash
# From command line args
python scripts/scrape.py \
  URL1 URL2 URL3 -p 10 --batch-output results.jsonl

# From file (JSONL or plain text)
python scripts/scrape.py \
  --batch urls.jsonl -p 10 --batch-output results.jsonl

# Write each result to separate markdown file (filename from URL slug)
python scripts/scrape.py \
  --batch urls.txt --output-dir ./articles/ -p 10

# Write as JSON files instead
python scripts/scrape.py \
  --batch urls.txt --output-dir ./data/ --output-ext json -o json
```

### Streaming Output (Long-Running Jobs)

```bash
# Stream results as they complete + checkpoint for resume
python scripts/scrape.py \
  --batch urls.jsonl \
  --output-stream results.jsonl \
  --checkpoint job1.json \
  -p 10 -v

# Resume interrupted job (skips already-processed URLs)
python scripts/scrape.py \
  --batch urls.jsonl \
  --output-stream results.jsonl \
  --checkpoint job1.json \
  -p 10
```

### Cross-tool Workflow (agent-browser state import)

```bash
# Login with agent-browser (or any tool that exports state)
# ... login flow ...

# Scrape with imported state
python scripts/scrape.py \
  "https://site.com/dashboard" \
  --session imported --import-state ~/auth.json \
  -e "Extract user data" -j
```

## Cache

- Location: `~/.cache/ultimate-scraper/cache.db`
- TTL: 24 hours
- Bypass: `--no-cache`
- Key includes: URL + mode + extract_prompt (different prompts = different entries)

## Dependencies

**Core (all tiers):**
- Python 3.8+
- httpx (`pip install httpx`) — async HTTP client
- beautifulsoup4 (`pip install beautifulsoup4`) — HTML parsing
- lxml (`pip install lxml`) — fast XML/HTML parser
- html2text (`pip install html2text`) — HTML→Markdown conversion
- pyyaml (`pip install pyyaml`) — YAML config loading
- python-dotenv (`pip install python-dotenv`) — .env file loading

**Tier 0 — Static extraction:**
- chompjs (`pip install chompjs`) — JavaScript object→Python dict parsing
- extruct (`pip install extruct`) — JSON-LD, Microdata, OpenGraph extraction

**Tier 1 — HTTP with TLS spoofing:**
- curl_cffi (`pip install curl_cffi`) — HTTP client with browser TLS fingerprint impersonation

**Tier 2 — Stealth browser:**
- scrapling (`pip install scrapling`) — Patchright-based stealth browser automation
- cloakbrowser (`pip install cloakbrowser`) — 26 C++ source-level Chromium patches (preferred over Patchright). Binary auto-downloads ~200MB on first use. Set `CLOAKBROWSER_ENABLED=0` to force Patchright fallback.

**Tier 3 — Anti-detect browser:**
- camoufox (`pip install camoufox[geoip] && python -m camoufox fetch`) — C++ anti-detect Firefox with hardware-backed fingerprinting. First run downloads ~780MB browser package.

**Tier 4 — AI extraction:**
- crawl4ai (`pip install crawl4ai`) — AI-powered web crawling with LLM integration

**Test dependencies:**
- pytest, pytest-asyncio, pytest-cov, scipy, httpx

**Install order:**
```bash
# 1. Core
pip install httpx beautifulsoup4 lxml html2text pyyaml python-dotenv

# 2. Static extraction (Tier 0)
pip install chompjs extruct

# 3. HTTP tier (Tier 1)
pip install curl_cffi

# 4. Browser tiers (Tier 2-3)
pip install scrapling cloakbrowser
pip install 'camoufox[geoip]' && python -m camoufox fetch

# 5. AI tier (Tier 4)
pip install crawl4ai

# 6. Test dependencies (optional)
pip install pytest pytest-asyncio pytest-cov scipy
```

## WSL2 Known Issues

| Issue | Tier | Symptom | Workaround |
|-------|------|---------|------------|
| Camoufox Turnstile failure | 3 | Cloudflare Turnstile never solves (90s poll, zero captures) | Run on native Linux or VM via SSH |
| Virtual GPU fingerprinting | 3 | WSL2's synthetic GPU produces fingerprints Turnstile detects as non-human | Native Linux VM passes; WSL2 does not |
| CloakBrowser display | 2 | Headed mode may fail without X server | Install VcXsrv or use headless mode |

Tier 3 on WSL2 is unreliable for Turnstile-protected sites. WSL2's virtual GPU produces inconsistent canvas, WebGL, and audio fingerprints. Tiers 0-2 and 4-5 work normally on WSL2.

## Environment Variables

See `.env.example` for all configurable options. Key variables:

```bash
# Proxy (bring your own)
PROXY_HOST=                    # Proxy hostname
PROXY_PORT=                    # Proxy port
PROXY_USERNAME=                # Auth username
PROXY_PASSWORD=                # Auth password

# AI extraction (optional)
LOCAL_LLM_URL=                 # OpenAI-compatible endpoint
LOCAL_LLM_ENABLED=false        # Enable local LLM
ZAI_API_KEY=                   # z.ai API key
ANTHROPIC_API_KEY=             # Anthropic API key

# CAPTCHA solving (optional)
CAPSOLVER_API_KEY=             # AI-based solver (faster)
TWOCAPTCHA_API_KEY=            # Human workers fallback

# CloakBrowser — auto|1|0
CLOAKBROWSER_ENABLED=auto

# WebMCP — auto|1|0
WEBMCP_ENABLED=auto
CHROME_CHANNEL=                # chrome-dev, chrome-beta, chrome-canary
```

## Testing

```bash
# Run fast tests (unit + integration, ~5s)
cd scripts
python -m pytest tests/ -v

# Run all tests including E2E (~15s)
python -m pytest tests/ -m "" -v

# Run with coverage report
python -m pytest tests/ --cov=. --cov-report=html
```

### Test Categories

| Category | Tests | Description |
|----------|-------|-------------|
| Unit | 188 | Pure function logic (fingerprint, behavior, detection, proxy, etc.) |
| Integration | 46 | SQLite operations (persistence, sessions, cache) |
| E2E | 40 | Network tests against real sites (httpbin, practice sites) |

### Test Dependencies

See Dependencies section above for install commands.
