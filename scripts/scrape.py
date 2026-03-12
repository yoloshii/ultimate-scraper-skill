#!/usr/bin/env python3
"""Ultimate Web Scraper CLI - Multi-tier scraping with AI extraction."""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Set

# Add scripts directory to path for imports
SCRIPTS_DIR = Path(__file__).parent.resolve()
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from core.scraper import UltimateScraper
from core.result import ScrapeResult


def url_to_slug(url: str) -> str:
    """
    Convert URL to filesystem-safe slug for filename.

    Examples:
        https://example.com/blog/my-article/ -> my-article
        https://example.com/products/item-123 -> item-123
        https://example.com/ -> index
    """
    from urllib.parse import urlparse
    import re

    parsed = urlparse(url)
    path = parsed.path.strip('/')

    if not path:
        return "index"

    # Take the last path segment
    slug = path.split('/')[-1]

    # Remove file extensions
    slug = re.sub(r'\.(html?|php|aspx?)$', '', slug, flags=re.IGNORECASE)

    # Clean up the slug
    slug = re.sub(r'[^\w\-]', '-', slug)  # Replace non-word chars with dash
    slug = re.sub(r'-+', '-', slug)        # Collapse multiple dashes
    slug = slug.strip('-').lower()

    return slug or "page"


def load_urls_from_file(filepath: str) -> List[Dict]:
    """
    Load URLs from file. Supports:
    - JSONL with 'url' field (from seo-crawler discover)
    - Plain text (one URL per line)

    Returns list of dicts with at minimum {'url': '...'}
    """
    urls = []
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(f"Batch file not found: {filepath}")

    with open(path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Try JSONL first
            if line.startswith('{'):
                try:
                    data = json.loads(line)
                    if 'url' in data:
                        urls.append(data)
                    else:
                        print(f"Warning: Line {line_num} missing 'url' field, skipping", file=sys.stderr)
                except json.JSONDecodeError:
                    # Fallback to plain URL
                    urls.append({'url': line})
            else:
                # Plain URL
                if line.startswith('http://') or line.startswith('https://'):
                    urls.append({'url': line})
                else:
                    print(f"Warning: Line {line_num} not a valid URL, skipping: {line[:50]}", file=sys.stderr)

    return urls


class CheckpointManager:
    """Manage checkpoint state for resumable batch jobs."""

    def __init__(self, checkpoint_file: Optional[str] = None):
        self.file = Path(checkpoint_file) if checkpoint_file else None
        self.processed: Set[str] = set()
        self.failed: Set[str] = set()
        self.stats = {
            'started_at': None,
            'last_updated': None,
            'total_urls': 0,
            'processed_count': 0,
            'success_count': 0,
            'failed_count': 0,
        }
        if self.file:
            self._load()

    def _load(self):
        """Load checkpoint from file if exists."""
        if self.file and self.file.exists():
            try:
                with open(self.file, 'r') as f:
                    data = json.load(f)
                self.processed = set(data.get('processed', []))
                self.failed = set(data.get('failed', []))
                self.stats = data.get('stats', self.stats)
                print(f"[Checkpoint] Loaded: {len(self.processed)} processed, {len(self.failed)} failed", file=sys.stderr)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Checkpoint] Warning: Could not load checkpoint: {e}", file=sys.stderr)

    def save(self):
        """Save checkpoint to file."""
        if not self.file:
            return

        self.stats['last_updated'] = datetime.now().isoformat()
        data = {
            'processed': list(self.processed),
            'failed': list(self.failed),
            'stats': self.stats,
        }

        # Write atomically
        tmp_file = self.file.with_suffix('.tmp')
        with open(tmp_file, 'w') as f:
            json.dump(data, f, indent=2)
        tmp_file.rename(self.file)

    def is_processed(self, url: str) -> bool:
        """Check if URL was already processed."""
        return url in self.processed

    def mark_processed(self, url: str, success: bool):
        """Mark URL as processed."""
        self.processed.add(url)
        self.stats['processed_count'] = len(self.processed)
        if success:
            self.stats['success_count'] += 1
        else:
            self.failed.add(url)
            self.stats['failed_count'] = len(self.failed)

        # Auto-save every 10 URLs
        if len(self.processed) % 10 == 0:
            self.save()

    def start_job(self, total_urls: int):
        """Initialize job stats."""
        if not self.stats['started_at']:
            self.stats['started_at'] = datetime.now().isoformat()
        self.stats['total_urls'] = total_urls


class StreamingOutput:
    """Handle streaming JSONL output."""

    def __init__(self, filepath: Optional[str] = None):
        self.file = None
        if filepath:
            self.file = open(filepath, 'a', encoding='utf-8')

    def write(self, result: ScrapeResult, metadata: Optional[Dict] = None):
        """Write a single result to stream."""
        if not self.file:
            return

        output_data = {
            'timestamp': datetime.now().isoformat(),
            'success': result.success,
            'url': result.url,
            'final_url': result.final_url,
            'tier_used': result.tier_used,
            'error': result.error,
            'error_type': result.error_type,
            'data': result.extracted_data,
            'static_data': result.static_data,
            'markdown': result.markdown,
        }

        if metadata:
            output_data['metadata'] = metadata

        # Remove None values
        output_data = {k: v for k, v in output_data.items() if v is not None}

        self.file.write(json.dumps(output_data, ensure_ascii=False) + '\n')
        self.file.flush()  # Ensure immediate write

    def close(self):
        if self.file:
            self.file.close()


class DirectoryOutput:
    """Write each result to a separate file in a directory."""

    def __init__(self, directory: str, extension: str = "md", output_format: str = "markdown"):
        self.directory = Path(directory)
        self.extension = extension.lstrip('.')
        self.output_format = output_format
        self.written_files: List[str] = []
        self._slug_counts: Dict[str, int] = {}  # Handle duplicate slugs

        # Create directory if it doesn't exist
        self.directory.mkdir(parents=True, exist_ok=True)

    def _get_unique_filename(self, slug: str) -> str:
        """Get unique filename, handling duplicates."""
        if slug not in self._slug_counts:
            self._slug_counts[slug] = 0
            return f"{slug}.{self.extension}"

        self._slug_counts[slug] += 1
        return f"{slug}-{self._slug_counts[slug]}.{self.extension}"

    def write(self, result: ScrapeResult, metadata: Optional[Dict] = None):
        """Write a single result to its own file."""
        if not result.success:
            return  # Skip failed results

        slug = url_to_slug(result.url)
        filename = self._get_unique_filename(slug)
        filepath = self.directory / filename

        # Determine content based on format
        if self.output_format == "json":
            content = json.dumps({
                'url': result.url,
                'final_url': result.final_url,
                'tier_used': result.tier_used,
                'data': result.extracted_data,
                'static_data': result.static_data,
                'markdown': result.markdown,
            }, indent=2, ensure_ascii=False)
        elif self.output_format == "raw":
            content = result.html or ""
        else:  # markdown (default)
            content = result.markdown or ""

        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        self.written_files.append(str(filepath))

    def close(self):
        """No-op for directory output (files are written immediately)."""
        pass

    def summary(self) -> str:
        """Return summary of written files."""
        return f"Wrote {len(self.written_files)} files to {self.directory}"


HELP_EPILOG = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                              TIER ESCALATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Tier 0  static      chompjs/extruct     __NEXT_DATA__, JSON-LD extraction
  Tier 1  http        curl_cffi           TLS fingerprint spoofing
  Tier 2  browser     Scrapling           Stealth browser (patchright)
  Tier 2.5 agent      agent-browser       Network interception, tracker blocking
  Tier 3  stealth     Camoufox            Full anti-detect (C++ fingerprints)
  Tier 4  ai          Crawl4AI + LLM      AI-powered extraction
  Tier 5  visual      Screenshot + Vision Screenshot-based visual extraction
  ────────────────────────────────────────────────────────────────────────────
  Fallback: Brightdata Web Unlocker       Paywall/CAPTCHA bypass (MCP tool)

  Auto-escalation: Tier N fails → rotate proxy → retry → escalate to N+1.
  JA4T sites: Tier 1 auto-skipped (transport-layer fingerprinting detected).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                                 EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Basic:
    scrape.py "https://example.com"                     # Auto-detect tier
    scrape.py "https://example.com" -o json             # JSON output
    scrape.py "https://example.com" -o raw              # Raw HTML

  AI Extraction:
    scrape.py URL -e "Extract product names and prices"
    scrape.py URL -e "Get all article titles" -o json
    scrape.py URL -e "Extract data" -s '{"name":"str","price":"num"}'

  Visual Extraction (Screenshot + Vision LLM):
    scrape.py URL --visual -e "Extract all visible prices"
    scrape.py URL -m visual -e "Extract product information"

  Stealth + Proxy:
    scrape.py URL -m stealth -g us                      # US residential proxy
    scrape.py URL -m stealth -g uk-london --proxy-sticky
    scrape.py URL -m browser -g de-berlin

  Sessions (multi-page):
    scrape.py "https://site.com/login" --session acct -m stealth
    scrape.py "https://site.com/dashboard" --session acct

  State Transfer (agent-browser compatible):
    scrape.py URL --session s1 --export-state auth.json
    scrape.py URL --session s2 --import-state auth.json

  Batch Processing:
    scrape.py url1 url2 url3 -p 10                      # 10 concurrent
    scrape.py url1 url2 --batch-output results.jsonl    # JSONL output
    scrape.py --batch urls.jsonl -p 10                  # Read URLs from file
    scrape.py --batch urls.txt --output-stream out.jsonl  # Stream to JSONL
    scrape.py --batch urls.txt --output-dir ./articles/   # Individual .md files
    scrape.py --batch urls.txt --output-dir ./data/ --output-ext json -o json

  Composition (with seo-crawler):
    seo-crawler discover https://docs.example.com -o urls.jsonl
    scrape.py --batch urls.jsonl --output-dir ./docs/ --checkpoint job1.json

  Diagnostics:
    scrape.py URL --probe-only                          # Detect anti-bot
    scrape.py URL -v                                    # Verbose output
    scrape.py URL --no-cache                            # Skip cache

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                             OUTPUT OPTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Single URL:     stdout (markdown/json/raw based on -o flag)
  --batch-output: Single JSONL file with all results (after completion)
  --output-stream: JSONL file with results streamed as they complete
  --output-dir:   Separate file per URL (filename from URL slug)
                  Combine with --output-ext to change extension (default: md)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                               EXIT CODES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  0   Success
  1   Failed (all tiers exhausted, or page not found/404)
  2   Brightdata required (paywall/CAPTCHA detected)
  130 Interrupted (Ctrl+C)

  Note: 404 pages are detected via HTTP status + content pattern + HEAD
        verification. They exit with code 1 (NotFound), not code 2.
"""


def parse_args():
    parser = argparse.ArgumentParser(
        prog="scrape.py",
        description="Ultimate Web Scraper — Intelligent multi-tier scraping with AI extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=HELP_EPILOG,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Positional
    # ─────────────────────────────────────────────────────────────────────────
    parser.add_argument(
        "url",
        nargs="*",
        metavar="URL",
        help="Target URL(s). Multiple URLs enable batch mode. Use --batch FILE for file input."
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Mode & Tier
    # ─────────────────────────────────────────────────────────────────────────
    mode_group = parser.add_argument_group(
        "Mode Control",
        "Select scraping strategy and escalation limits"
    )
    mode_group.add_argument(
        "-m", "--mode",
        choices=["auto", "static", "http", "browser", "agent", "stealth", "ai", "visual", "brightdata"],
        default="auto",
        metavar="MODE",
        help="auto|static|http|browser|agent|stealth|ai|visual|brightdata (default: auto)"
    )
    mode_group.add_argument(
        "--visual",
        action="store_true",
        help="Enable visual extraction (screenshot + Vision LLM). Shorthand for --mode visual"
    )
    mode_group.add_argument(
        "--max-tier",
        type=int,
        choices=[0, 1, 2, 3, 4],
        default=4,
        metavar="N",
        help="Maximum tier for escalation: 0-4 (default: 4)"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Output
    # ─────────────────────────────────────────────────────────────────────────
    output_group = parser.add_argument_group(
        "Output",
        "Control output format"
    )
    output_group.add_argument(
        "-o", "--output",
        choices=["markdown", "json", "raw"],
        default="markdown",
        metavar="FMT",
        help="markdown|json|raw (default: markdown)"
    )
    output_group.add_argument(
        "-j", "--json",
        action="store_true",
        help="Shorthand for --output json"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # AI Extraction
    # ─────────────────────────────────────────────────────────────────────────
    ai_group = parser.add_argument_group(
        "AI Extraction",
        "LLM-powered data extraction (uses 3-tier routing: Local→z.ai→Haiku)"
    )
    ai_group.add_argument(
        "-e", "--extract",
        metavar="PROMPT",
        help="Natural language extraction prompt"
    )
    ai_group.add_argument(
        "-s", "--schema",
        metavar="JSON",
        help="JSON schema for structured output"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Proxy
    # ─────────────────────────────────────────────────────────────────────────
    proxy_group = parser.add_argument_group(
        "Proxy (ProxyEmpire)",
        "Residential proxy with geo-targeting"
    )
    proxy_group.add_argument(
        "-g", "--proxy-geo",
        metavar="GEO",
        help="Geo target: us, uk, de, us-newyork, uk-london, etc."
    )
    proxy_group.add_argument(
        "--proxy-sticky",
        action="store_true",
        help="Maintain same IP across requests"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Session
    # ─────────────────────────────────────────────────────────────────────────
    session_group = parser.add_argument_group(
        "Session",
        "Persist cookies/state across scrapes"
    )
    session_group.add_argument(
        "--session",
        metavar="NAME",
        help="Named session for cookie/state persistence"
    )
    session_group.add_argument(
        "--import-state",
        metavar="FILE",
        help="Import state from agent-browser JSON file"
    )
    session_group.add_argument(
        "--export-state",
        metavar="FILE",
        help="Export state to agent-browser JSON file"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Browser
    # ─────────────────────────────────────────────────────────────────────────
    browser_group = parser.add_argument_group(
        "Browser Actions",
        "For browser tiers (2, 2.5, 3)"
    )
    browser_group.add_argument(
        "--actions",
        metavar="JSON",
        help='Actions array: [{"click":".btn"},{"wait":1000}]'
    )
    browser_group.add_argument(
        "--wait-for",
        metavar="SEL",
        help="CSS selector to wait for before extraction"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Batch
    # ─────────────────────────────────────────────────────────────────────────
    batch_group = parser.add_argument_group(
        "Batch Processing",
        "Scrape multiple URLs concurrently"
    )
    batch_group.add_argument(
        "-p", "--parallel",
        type=int,
        default=5,
        metavar="N",
        help="Max concurrent scrapes (default: 5)"
    )
    batch_group.add_argument(
        "--batch",
        metavar="FILE",
        help="Read URLs from file (JSONL with 'url' field, or plain text one per line)"
    )
    batch_group.add_argument(
        "--batch-output",
        metavar="FILE",
        help="Write all results to JSON Lines file (after completion)"
    )
    batch_group.add_argument(
        "--output-stream",
        metavar="FILE",
        help="Stream results to JSON Lines file (write each as it completes)"
    )
    batch_group.add_argument(
        "--checkpoint",
        metavar="FILE",
        help="Checkpoint file for resume capability (skip already-processed URLs)"
    )
    batch_group.add_argument(
        "--output-dir",
        metavar="DIR",
        help="Write each result to separate file in directory (filename from URL slug)"
    )
    batch_group.add_argument(
        "--output-ext",
        metavar="EXT",
        default="md",
        help="File extension for --output-dir files (default: md)"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Advanced
    # ─────────────────────────────────────────────────────────────────────────
    adv_group = parser.add_argument_group("Advanced")
    adv_group.add_argument(
        "-t", "--timeout",
        type=int,
        default=30,
        metavar="SEC",
        help="Request timeout in seconds (default: 30)"
    )
    adv_group.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass 24h result cache"
    )
    adv_group.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show tier progression and metadata"
    )
    adv_group.add_argument(
        "--probe-only",
        action="store_true",
        help="Detect site profile without scraping"
    )
    adv_group.add_argument(
        "--behavior-intensity",
        type=float,
        default=1.0,
        metavar="N",
        help="Behavioral simulation intensity: 0.5=fast, 1.0=normal, 2.0=slow (default: 1.0)"
    )

    return parser.parse_args()


async def main():
    args = parse_args()

    # Handle --json alias
    output_format = "json" if args.json else args.output

    # Handle --visual alias
    mode = args.mode
    if args.visual:
        mode = "visual"

    # Parse schema if provided
    schema = None
    if args.schema:
        try:
            schema = json.loads(args.schema)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON schema: {e}", file=sys.stderr)
            sys.exit(1)

    # Parse actions if provided
    actions = None
    if args.actions:
        try:
            actions = json.loads(args.actions)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid actions JSON: {e}", file=sys.stderr)
            sys.exit(1)

    # Initialize scraper
    scraper = UltimateScraper()

    # Override behavior intensity if specified
    if args.behavior_intensity != 1.0:
        scraper.config.behavior_intensity = args.behavior_intensity

    # Handle URL sources: --batch file or positional args
    url_entries = []  # List of {'url': ..., 'source': ..., ...}

    if args.batch:
        try:
            url_entries = load_urls_from_file(args.batch)
            if not url_entries:
                print(f"Error: No valid URLs found in {args.batch}", file=sys.stderr)
                sys.exit(1)
            if args.verbose:
                print(f"[Batch] Loaded {len(url_entries)} URLs from {args.batch}", file=sys.stderr)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.url:
        url_entries = [{'url': u} for u in args.url]
    else:
        print("Error: No URLs provided. Use positional args or --batch FILE", file=sys.stderr)
        sys.exit(1)

    urls = [entry['url'] for entry in url_entries]
    is_batch = len(urls) > 1

    try:
        # Import state if specified
        if args.import_state and args.session:
            from session.manager import SessionManager
            session_mgr = SessionManager()
            imported = session_mgr.import_from_agentbrowser(
                args.session,
                Path(args.import_state)
            )
            if imported and args.verbose:
                print(f"[State] Imported session from {args.import_state}", file=sys.stderr)

        # Probe only mode
        if args.probe_only:
            profile = await scraper.probe(urls[0])
            result = {
                "url": urls[0],
                "domain": profile.domain,
                "antibot": profile.antibot,
                "antibot_confidence": profile.antibot_confidence,
                "recommended_tier": profile.recommended_tier,
                "needs_proxy": profile.needs_proxy,
                "needs_sticky": profile.needs_sticky,
                "has_static_data": profile.has_static_data,
                "requires_js": profile.requires_js,
                "detected_framework": profile.detected_framework,
                "metadata": profile.metadata,
            }
            print(json.dumps(result, indent=2))
            return

        # Execute scrape (batch or single)
        if is_batch:
            # Initialize checkpoint manager
            checkpoint = CheckpointManager(args.checkpoint)

            # Filter out already-processed URLs
            pending_urls = [u for u in urls if not checkpoint.is_processed(u)]
            skipped_count = len(urls) - len(pending_urls)

            if skipped_count > 0 and args.verbose:
                print(f"[Checkpoint] Skipping {skipped_count} already-processed URLs", file=sys.stderr)

            if not pending_urls:
                print("All URLs already processed (checkpoint). Nothing to do.", file=sys.stderr)
                return

            checkpoint.start_job(len(urls))

            # Initialize output handlers
            stream = StreamingOutput(args.output_stream)
            dir_output = DirectoryOutput(args.output_dir, args.output_ext, output_format) if args.output_dir else None

            try:
                # Batch mode with streaming: process URLs and stream results
                if args.output_stream or args.output_dir:
                    # Use streaming mode: process one at a time with concurrency control
                    semaphore = asyncio.Semaphore(args.parallel)
                    results = []
                    start_time = time.time()

                    async def process_url(url: str, entry: Dict):
                        async with semaphore:
                            result = await scraper.scrape(
                                url=url,
                                mode=mode,
                                output=output_format,
                                extract_prompt=args.extract,
                                extract_schema=schema,
                                session_id=args.session,
                                proxy_geo=args.proxy_geo,
                                proxy_sticky=args.proxy_sticky,
                                max_tier=args.max_tier,
                                timeout=args.timeout,
                                actions=actions,
                                wait_for=args.wait_for,
                                use_cache=not args.no_cache,
                                verbose=args.verbose,
                            )
                            # Write result to outputs
                            stream.write(result, metadata=entry.get('metadata'))
                            if dir_output:
                                dir_output.write(result, metadata=entry.get('metadata'))
                            checkpoint.mark_processed(url, result.success)

                            # Progress indicator
                            processed = len(checkpoint.processed)
                            total = len(urls)
                            elapsed = time.time() - start_time
                            rate = processed / elapsed if elapsed > 0 else 0
                            print(f"\r[Progress] {processed}/{total} ({rate:.1f}/s)", end="", file=sys.stderr)

                            return result

                    # Create tasks for pending URLs
                    pending_entries = [e for e in url_entries if e['url'] in pending_urls]
                    tasks = [process_url(e['url'], e) for e in pending_entries]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # Handle exceptions
                    for i, r in enumerate(results):
                        if isinstance(r, Exception):
                            print(f"\nError processing {pending_urls[i]}: {r}", file=sys.stderr)

                    print(f"\n[Complete] Processed {len(pending_urls)} URLs", file=sys.stderr)

                else:
                    # Standard batch mode (existing behavior)
                    results = await scraper.scrape_batch(
                        urls=pending_urls,
                        max_concurrent=args.parallel,
                        mode=mode,
                        output=output_format,
                        extract_prompt=args.extract,
                        extract_schema=schema,
                        session_id=args.session,
                        proxy_geo=args.proxy_geo,
                        proxy_sticky=args.proxy_sticky,
                        max_tier=args.max_tier,
                        timeout=args.timeout,
                        actions=actions,
                        wait_for=args.wait_for,
                        use_cache=not args.no_cache,
                        verbose=args.verbose,
                    )

                    # Mark all as processed in checkpoint
                    for r in results:
                        checkpoint.mark_processed(r.url, r.success)

                # Save final checkpoint
                checkpoint.save()

            finally:
                stream.close()
                if dir_output:
                    dir_output.close()

            # Write to output directory for non-streaming batch mode
            if args.output_dir and not args.output_stream:
                # dir_output wasn't used yet, write now
                dir_output = DirectoryOutput(args.output_dir, args.output_ext, output_format)
                for r in results:
                    if isinstance(r, Exception):
                        continue
                    dir_output.write(r)
                print(dir_output.summary(), file=sys.stderr)

            # Output batch results (if not streaming)
            if args.batch_output and not args.output_stream:
                # JSON Lines format to file
                with open(args.batch_output, "w") as f:
                    for r in results:
                        if isinstance(r, Exception):
                            continue
                        output_data = {
                            "success": r.success,
                            "url": r.url,
                            "final_url": r.final_url,
                            "tier_used": r.tier_used,
                            "error": r.error,
                            "error_type": r.error_type,
                            "data": r.extracted_data,
                            "static_data": r.static_data,
                            "markdown": r.markdown,
                        }
                        # Remove None values for cleaner output
                        output_data = {k: v for k, v in output_data.items() if v is not None}
                        f.write(json.dumps(output_data, ensure_ascii=False) + "\n")
                print(f"Batch results written to {args.batch_output}")
            elif not args.output_stream and not args.output_dir:
                # Print summary to stdout (only if no file output specified)
                valid_results = [r for r in results if not isinstance(r, Exception)]
                success_count = sum(1 for r in valid_results if r.success)
                print(f"\n# Batch Results: {success_count}/{len(valid_results)} successful\n")
                for r in valid_results:
                    status = "✅" if r.success else "❌"
                    tier = f"T{r.tier_used}" if r.tier_used is not None else "?"
                    error = f" - {r.error}" if r.error else ""
                    print(f"{status} [{tier}] {r.url}{error}")

            # Exit with error if any failed
            valid_results = [r for r in results if not isinstance(r, Exception)]
            if not all(r.success for r in valid_results):
                sys.exit(1)
            return

        # Single URL mode
        result = await scraper.scrape(
            url=urls[0],
            mode=mode,
            output=output_format,
            extract_prompt=args.extract,
            extract_schema=schema,
            session_id=args.session,
            proxy_geo=args.proxy_geo,
            proxy_sticky=args.proxy_sticky,
            max_tier=args.max_tier,
            timeout=args.timeout,
            actions=actions,
            wait_for=args.wait_for,
            use_cache=not args.no_cache,
            verbose=args.verbose,
        )

        # Export state if specified
        if args.export_state and args.session and result.success:
            from session.manager import SessionManager
            session_mgr = SessionManager()
            exported = session_mgr.export_to_agentbrowser(
                args.session,
                Path(args.export_state)
            )
            if exported and args.verbose:
                print(f"[State] Exported session to {args.export_state}", file=sys.stderr)

        # Handle Brightdata recommendation
        if result.error_type == "BrightdataRequired":
            if args.verbose:
                print("[Info] Brightdata Web Unlocker recommended for this URL", file=sys.stderr)
            # Output instruction for agent/user
            brightdata_info = {
                "status": "brightdata_required",
                "url": urls[0],
                "message": "All tiers exhausted. Use a premium proxy/web unlocker service for this URL.",
                "extract_prompt": args.extract,
                "extract_schema": schema,
            }
            print(json.dumps(brightdata_info, indent=2))
            sys.exit(2)  # Special exit code for Brightdata needed

        # Output result
        if not result.success:
            error_output = {
                "success": False,
                "url": urls[0],
                "error": result.error,
                "error_type": result.error_type,
                "tier_used": result.tier_used,
            }
            print(json.dumps(error_output, indent=2), file=sys.stderr)
            sys.exit(1)

        # Output based on format
        if output_format == "json":
            output_data = {
                "success": True,
                "url": urls[0],
                "final_url": result.final_url,
                "tier_used": result.tier_used,
                "data": result.extracted_data,
                "static_data": result.static_data,
                "markdown": result.markdown if not result.extracted_data else None,
                "metadata": result.metadata,
            }
            # Clean up None values
            output_data = {k: v for k, v in output_data.items() if v is not None}
            print(json.dumps(output_data, indent=2, ensure_ascii=False))

        elif output_format == "markdown":
            # Print formatted markdown output
            if result.extracted_data:
                # If we have extracted data, format it nicely
                print(f"# Extracted Data from {urls[0]}\n")
                print(f"**Tier Used:** {result.tier_used}")
                if result.final_url and result.final_url != args.url:
                    print(f"**Final URL:** {result.final_url}")
                print("\n## Data\n")
                print("```json")
                print(json.dumps(result.extracted_data, indent=2, ensure_ascii=False))
                print("```")
            elif result.markdown:
                print(result.markdown)
            elif result.static_data:
                print(f"# Static Data from {urls[0]}\n")
                print("```json")
                print(json.dumps(result.static_data, indent=2, ensure_ascii=False))
                print("```")
            else:
                print(f"# Content from {urls[0]}\n")
                print("No content extracted.")

        elif output_format == "raw":
            print(result.html or "")

        # Print metadata to stderr in verbose mode
        if args.verbose and result.metadata:
            print(f"\n[Metadata] {json.dumps(result.metadata)}", file=sys.stderr)

    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
