# ultimate-scraper

Multi-tier web scraper with intelligent tier escalation, anti-bot bypass, CAPTCHA solving, and AI-powered data extraction.

## Features

- **6 scraping tiers** with automatic escalation (static → HTTP → stealth browser → anti-detect → AI → visual)
- **CloakBrowser** (C++ patched Chromium) and **Camoufox** (C++ anti-detect Firefox) for stealth
- **CAPTCHA solving** via CapSolver (AI) and 2Captcha (human workers)
- **AI extraction** with 3-tier LLM routing (local → z.ai → Claude Haiku)
- **Per-domain rate limiting** with sliding window
- **Fingerprint persistence** (consistent identity per domain)
- **Proxy support** with geo-targeting and timezone/locale correlation
- **Tracker blocking** via CDP network interception
- **Shadow DOM piercing** for web components
- **WebMCP extraction** for Chrome 147+ structured tool discovery
- **Batch processing** with checkpointing and streaming output
- **Session persistence** with cookie/state management

## Quick Start

```bash
# Install core + all tiers
pip install httpx beautifulsoup4 lxml html2text pyyaml python-dotenv
pip install chompjs extruct              # Tier 0: static extraction
pip install curl_cffi                     # Tier 1: TLS spoofing
pip install scrapling cloakbrowser        # Tier 2: stealth browser
pip install 'camoufox[geoip]' && python -m camoufox fetch  # Tier 3: anti-detect (~780MB)
pip install crawl4ai                      # Tier 4: AI extraction

# Basic scrape
python scripts/scrape.py "https://example.com"

# With AI extraction
python scripts/scrape.py "https://example.com" \
  -e "Extract all product names and prices" -o json

# Protected sites (stealth browser + US proxy)
python scripts/scrape.py "https://example.com" -m stealth -g us
```

## Tier System

| Tier | Mode | Technology | Use Case |
|------|------|------------|----------|
| 0 | static | chompjs/extruct | `__NEXT_DATA__`, JSON-LD (fastest) |
| 1 | http | curl_cffi | TLS fingerprint spoofing |
| 2 | browser | CloakBrowser/Patchright | Stealth browser + CAPTCHA solving |
| 2.5 | agent | agent-browser CLI | CLI automation + tracker blocking |
| 3 | stealth | Camoufox | Full anti-detect (Cloudflare bypass) |
| 4 | ai | Crawl4AI + LLM | AI-powered extraction |
| 5 | visual | Screenshot + Vision LLM | Visual extraction |

Auto-escalation: Tier N fails → rotate proxy → retry → escalate to N+1.

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

### Proxy (Bring Your Own)

Any HTTP/SOCKS5 proxy provider works. Set via environment variables:

```bash
PROXY_HOST=your-proxy-host
PROXY_PORT=5000
PROXY_USERNAME=your_username
PROXY_PASSWORD=your_password
```

Residential proxies recommended for anti-bot sites. Geo-targeting via `-g us`, `-g uk`, `-g de`, etc.

### AI Extraction

3-tier LLM routing for `--extract` mode. The default chain reflects the developer's setup — **swap in whichever models and providers you prefer.** Any OpenAI-compatible API works for Tier 1, and the fallback tiers are simple to rewire in `scripts/extraction/ai_router.py`.

The dev's local model is [GLM-4.7-Flash-UD Q4](https://huggingface.co/THUDM/glm-4-9b-hf) served via vLLM/llama.cpp, but any instruction-following model with JSON output works (Qwen 2.5, Llama 3.1, Mistral, etc.).

```bash
# Tier 1: Any OpenAI-compatible local LLM
LOCAL_LLM_URL=http://localhost:8080/v1/chat/completions
LOCAL_LLM_ENABLED=true

# Tier 2: z.ai GLM-4.5-Air (or any cloud LLM — modify ai_router.py)
ZAI_API_KEY=your_key

# Tier 3: Anthropic Claude Haiku (or any fallback — modify ai_router.py)
ANTHROPIC_API_KEY=your_key
```

### CAPTCHA Solving

```bash
CAPSOLVER_API_KEY=your_key     # AI solver (~$1-3/1000 solves)
TWOCAPTCHA_API_KEY=your_key    # Human fallback
```

## CLI Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--mode MODE` | `-m` | auto\|static\|http\|browser\|agent\|stealth\|ai\|visual | auto |
| `--output FMT` | `-o` | markdown\|json\|raw | markdown |
| `--extract PROMPT` | `-e` | Natural language extraction instruction | |
| `--schema JSON` | `-s` | JSON schema for structured extraction | |
| `--visual` | | Screenshot + Vision LLM extraction | false |
| `--proxy-geo GEO` | `-g` | us, uk, de, jp, etc. | |
| `--session NAME` | | Named session for cookie persistence | |
| `--max-tier N` | | Limit escalation (0-5) | 4 |
| `--batch FILE` | | Read URLs from file (JSONL or text) | |
| `--parallel N` | `-p` | Concurrent scrapes (batch mode) | 5 |
| `--output-dir DIR` | | Write each result to separate file | |
| `--checkpoint FILE` | | Resume file for long-running jobs | |
| `--verbose` | `-v` | Show tier progression | false |
| `--no-rate-limit` | | Disable per-domain rate limiting | false |
| `--no-trackers` | | Disable tracker blocking | false |
| `--captcha-solve` | | Force CAPTCHA solving attempt | false |

## Examples

### E-commerce Product

```bash
python scripts/scrape.py \
  "https://amazon.com/dp/B0ABC123" \
  -m stealth -g us \
  -e "Extract product name, price, rating, review count" -j
```

### Batch Processing with Checkpointing

```bash
# Stream results as they complete + checkpoint for resume
python scripts/scrape.py \
  --batch urls.jsonl \
  --output-stream results.jsonl \
  --checkpoint job1.json \
  -p 10 -v

# Resume interrupted job
python scripts/scrape.py \
  --batch urls.jsonl \
  --output-stream results.jsonl \
  --checkpoint job1.json \
  -p 10
```

### Visual Extraction

For heavily protected pages or canvas-rendered content:

```bash
python scripts/scrape.py \
  "https://protected-site.com/data" \
  --visual -e "Extract all prices and product names" -j
```

## Agent Integration

This project includes `CLAUDE.md` and `AGENTS.md` for agent-first deployment. These files provide structured instructions for AI agents (Claude Code, Cursor, Windsurf, or any agent framework) to use the scraper autonomously.

## WSL2 Known Issues

| Issue | Tier | Workaround |
|-------|------|------------|
| Camoufox Turnstile failure | 3 | Run on native Linux or VM via SSH |
| Virtual GPU fingerprinting | 3 | Native Linux VM passes; WSL2 does not |
| CloakBrowser headed mode | 2 | Install VcXsrv or use headless mode |

Tier 3 is unreliable on WSL2 for Turnstile-protected sites due to virtual GPU fingerprinting. Tiers 0-2 and 4-5 work normally.

## Testing

```bash
pip install pytest pytest-asyncio pytest-cov scipy  # Test dependencies

cd scripts
python -m pytest tests/ -v                    # Unit + integration tests
python -m pytest tests/ -m "" -v              # All tests including E2E
python -m pytest tests/ --cov=. --cov-report=html  # With coverage
```

## Architecture

```
scripts/
├── scrape.py                 # CLI entry point
├── core/
│   ├── scraper.py            # Main orchestrator, tier escalation
│   ├── config.py             # Configuration (env vars + YAML)
│   └── result.py             # Result types and errors
├── tiers/
│   ├── tier0_static.py       # __NEXT_DATA__, JSON-LD extraction
│   ├── tier1_http.py         # TLS spoofing via curl_cffi
│   ├── tier2_scrapling.py    # CloakBrowser/Patchright stealth
│   ├── tier2_5_agentbrowser.py  # agent-browser CLI
│   ├── tier3_camoufox.py     # Camoufox anti-detect Firefox
│   ├── tier4_ai.py           # Crawl4AI + LLM
│   └── tier5_visual.py       # Screenshot + Vision LLM
├── extraction/               # AI router, shadow DOM, WebMCP
├── detection/                # Site profiling, paywall, loop detection
├── captcha/                  # CAPTCHA solving (CapSolver + 2Captcha)
├── proxy/                    # Proxy management with geo-targeting
├── fingerprint/              # Per-domain fingerprint persistence
├── rate_limiting/            # Per-domain sliding window
├── session/                  # Cookie/state persistence
├── cache/                    # SQLite response cache
└── tests/                    # Unit, integration, E2E tests
```

## License

MIT
