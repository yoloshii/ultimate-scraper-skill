# X.com Scraping Methodology

*Source: OpenClaw community (Discord, Feb 2026). Proven: 15-20s for 5 most recent posts, bookmarks, or search.*

---

## Core Principles

### Connection: CDP Debug Port Only
- Chrome debug-port profile local (CDP 9222)
- No API, no browser extension

### Tab Management: Cached Reuse
- Per-mode cached tab IDs: `profile`, `bookmarks`, `search`
- If mode tab missing: open once and cache — never open new tabs per run
- Warm dedicated search tab + one reusable profile tab

### Navigation: Direct URL Only
- Direct URL navigation (no typing/clicking in X UI)
- Navigate to `x.com/search?q=...`, `x.com/<username>`, `x.com/i/bookmarks` directly

### Extraction: Single-Pass Evaluate
- Run single-pass JS evaluation first (no snapshot/click loops)
- Stable selectors:
```
article                              # Tweet container
a[href*="/status/"]                  # Tweet permalink
[data-testid="tweetText"]           # Tweet text body
[data-testid="User-Name"]           # Username display
time[datetime]                       # Timestamp
```

### DOM Scoping
- Scope queries to `main` first (not whole document)

### Feed Order
- Keep top→down (DOM order = feed order)
- No timestamp resort

### Output: Lean Default
- Default: `url + text_200`
- If `tweetText` missing: article-text fallback, strip UI junk / trailing "Show more"

### Scrolling: Zero-First
- Zero-scroll first pass
- Micro-scroll only if needed to hit target count

### Timing: Adaptive Short Waits
- 250-350ms waits with bounded loops
- Fail fast: quick no-data signal → hard bail with partial results + reason

### Caching: Short Same-Query
- 30-60s cache for immediate reruns

---

## Recommended Invocation

```bash
# Posts from a profile (requires active X session)
python scrape.py "https://x.com/<username>" \
  --session x-primary -m browser \
  -e "Extract latest 5 posts: url, text (200 chars), timestamp" -j

# Search
python scrape.py "https://x.com/search?q=<query>&src=typed_query" \
  --session x-primary -m browser \
  -e "Extract top 5 results: url, text (200 chars), username, timestamp" -j

# Bookmarks (auth required)
python scrape.py "https://x.com/i/bookmarks" \
  --session x-primary -m browser \
  -e "Extract bookmarked posts: url, text (200 chars), timestamp" -j
```

---

## Anti-Patterns (Avoid)

| Pattern | Problem |
|---------|---------|
| New tab per run | Tab explosion, visible stealing |
| Search box interaction | Slow, detectable, fragile selectors |
| Full page snapshot for data | Overhead — JS evaluate is 10x faster |
| Timestamp resorting | Breaks feed context, wastes compute |
| Long fixed waits | Wasted time on fast loads |
| Infinite scroll harvesting | Rate limiting, detection, memory |
| Full document scope | Picks up sidebar/nav noise |
