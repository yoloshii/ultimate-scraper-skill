"""UltimateScraper - Main orchestrator for multi-tier web scraping."""

import asyncio
import json
from typing import Optional, Union
from urllib.parse import urlparse

from core.config import get_config, ScraperConfig
from core.result import ScrapeResult, Blocked, CaptchaRequired, RateLimited, PaywallDetected, StuckDetected
from tiers.tier0_static import Tier0Static
from tiers.tier1_http import Tier1HTTP
from tiers.tier2_scrapling import Tier2Scrapling
from tiers.tier2_5_agentbrowser import Tier2_5AgentBrowser
from tiers.tier3_camoufox import Tier3Camoufox
from tiers.tier4_ai import Tier4AI
from tiers.tier5_visual import Tier5Visual
from detection.mode_detector import ModeDetector, ScrapeProfile
from detection.paywall_detector import PaywallDetector
from proxy.manager import ProxyEmpireManager, ProxyConfig
from session.manager import SessionManager
from fingerprint.manager import FingerprintManager, FingerprintProfile
from extraction.static import StaticExtractor
from extraction.ai_router import AIExtractionRouter
from output.formatter import OutputFormatter
from cache.manager import CacheManager
from rate_limiting.limiter import RateLimiter
from captcha.solver import CaptchaSolver


class UltimateScraper:
    """
    Ultimate Web Scraper - Intelligent multi-tier scraping with AI extraction.

    Modes:
        auto    - Skill determines optimal approach (default)
        static  - API/JSON extraction only (fastest)
        http    - TLS-spoofed HTTP (curl_cffi)
        browser - Stealth browser (Scrapling)
        stealth - Full anti-detect (Camoufox)
        ai      - LLM-assisted extraction (Crawl4AI)
        brightdata - Brightdata Web Unlocker (paywall/CAPTCHA bypass)

    Output:
        markdown - LLM-optimized (default)
        json     - Structured data
        raw      - Complete HTML
    """

    MODE_TO_TIER = {
        "static": 0,
        "http": 1,
        "browser": 2,
        "agent": 2.5,  # agent-browser (lighter than Camoufox)
        "stealth": 3,
        "ai": 4,
        "visual": 5,  # Visual LLM extraction (screenshot + vision)
    }

    # Tier escalation sequence (includes 2.5 and 5)
    TIER_SEQUENCE = [0, 1, 2, 2.5, 3, 4, 5]

    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or get_config()

        # Initialize components
        self.mode_detector = ModeDetector()
        self.paywall_detector = PaywallDetector()
        self.session_manager = SessionManager()
        self.proxy_manager = ProxyEmpireManager()
        self.fingerprint_manager = FingerprintManager()
        self.ai_router = AIExtractionRouter()
        self.cache_manager = CacheManager()

        # Rate limiting (E3)
        self.rate_limiter = RateLimiter(limits=self.config.rate_limits) if self.config.rate_limiting_enabled else None

        # CAPTCHA solving (E1)
        self.captcha_solver = CaptchaSolver(
            capsolver_key=self.config.capsolver_api_key,
            twocaptcha_key=self.config.twocaptcha_api_key,
        ) if self.config.captcha_solver_configured else None

        # Initialize tiers lazily (on first use)
        self._tiers: dict = {}

    def _get_tier(self, tier_num: float):
        """Get or create tier instance."""
        if tier_num not in self._tiers:
            if tier_num == 0:
                self._tiers[0] = Tier0Static()
            elif tier_num == 1:
                self._tiers[1] = Tier1HTTP()
            elif tier_num == 2:
                self._tiers[2] = Tier2Scrapling(captcha_solver=self.captcha_solver)
            elif tier_num == 2.5:
                self._tiers[2.5] = Tier2_5AgentBrowser()
            elif tier_num == 3:
                self._tiers[3] = Tier3Camoufox(captcha_solver=self.captcha_solver)
            elif tier_num == 4:
                self._tiers[4] = Tier4AI()
            elif tier_num == 5:
                self._tiers[5] = Tier5Visual()
        return self._tiers.get(tier_num)

    async def _verify_404(self, url: str, timeout: int = 10) -> Optional[int]:
        """
        Verify URL status with lightweight HEAD request.

        Returns:
            HTTP status code, or None if request failed
        """
        try:
            from curl_cffi.requests import AsyncSession

            async with AsyncSession() as session:
                response = await session.head(
                    url,
                    timeout=timeout,
                    allow_redirects=True,
                    impersonate="chrome"
                )
                return response.status_code
        except Exception:
            # If HEAD fails, try GET with stream to avoid downloading body
            try:
                from curl_cffi.requests import AsyncSession

                async with AsyncSession() as session:
                    response = await session.get(
                        url,
                        timeout=timeout,
                        allow_redirects=True,
                        impersonate="chrome",
                        stream=True
                    )
                    return response.status_code
            except Exception:
                return None

    async def scrape(
        self,
        url: str,
        mode: str = "auto",
        output: str = "markdown",
        # AI extraction
        extract_prompt: Optional[str] = None,
        extract_schema: Optional[dict] = None,
        # Session control
        session_id: Optional[str] = None,
        persist_session: Optional[bool] = None,
        # Proxy control
        proxy_geo: Optional[str] = None,
        proxy_sticky: Optional[bool] = None,
        # Advanced
        force_tier: Optional[int] = None,
        max_tier: int = 4,
        timeout: int = 30,
        actions: Optional[list] = None,
        wait_for: Optional[str] = None,
        headers: Optional[dict] = None,
        # Cache control
        use_cache: bool = True,
        # Verbose output
        verbose: bool = False,
    ) -> ScrapeResult:
        """
        Main scraping entry point.

        Args:
            url: Target URL
            mode: Scraping mode (auto, static, http, browser, stealth, ai, brightdata)
            output: Output format (markdown, json, raw)

            extract_prompt: Natural language extraction instruction
            extract_schema: JSON schema for structured extraction

            session_id: Session identifier for persistence
            persist_session: Force session persistence (auto-determined if None)

            proxy_geo: Geographic targeting ("us", "us-ny", "de-berlin")
            proxy_sticky: Use sticky session for proxy

            force_tier: Force specific tier (0-4)
            max_tier: Maximum tier to escalate to
            timeout: Request timeout in seconds
            actions: Browser actions for Tier 2-3
            wait_for: CSS selector to wait for
            headers: Custom HTTP headers

            use_cache: Use result cache (default True)
            verbose: Enable verbose logging

        Returns:
            ScrapeResult with html, markdown, extracted_data, etc.
        """
        # Step 0: Check cache
        if use_cache:
            cached_data = self.cache_manager.get(url, mode, extract_prompt)
            if cached_data:
                if verbose:
                    print(f"[Cache] Hit for {url}")
                # Convert dict back to ScrapeResult
                cached = ScrapeResult(
                    success=True,
                    tier_used=cached_data.get("tier_used"),
                    status_code=cached_data.get("status_code"),
                    url=cached_data.get("url"),
                    html=cached_data.get("html"),
                    markdown=cached_data.get("markdown"),
                    extracted_data=cached_data.get("extracted_data"),
                    static_data=cached_data.get("static_data"),
                    metadata=cached_data.get("metadata", {}),
                )
                cached.metadata["from_cache"] = True
                return cached

        # Step 1: Handle special modes
        if mode == "brightdata":
            return await self._fetch_with_brightdata(url, extract_prompt, extract_schema, output)

        # Step 2: Detect target profile
        profile = await self.mode_detector.detect(url)
        if verbose:
            print(f"[Mode] Detected profile: antibot={profile.antibot}, tier={profile.recommended_tier}")

        # Step 2.5: Sensitive mode logging (E9)
        if profile.is_sensitive:
            if verbose:
                print(f"[Sensitive] {profile.domain} - enforcing sensitive mode")

        # Step 3: Determine tier strategy
        if force_tier is not None:
            start_tier = force_tier
            max_tier = force_tier
        elif mode == "auto":
            start_tier = profile.recommended_tier
        else:
            start_tier = self.MODE_TO_TIER.get(mode, 1)
            if mode != "auto":
                max_tier = start_tier

        # Step 3.5: Auto-mode adjustments (E7, E9)
        if mode == "auto" and force_tier is None:
            # Tier history: start at known-good tier (E7)
            best_tier = self.fingerprint_manager.get_best_tier(urlparse(url).netloc)
            if best_tier is not None:
                start_tier = best_tier
                if verbose:
                    print(f"[History] {urlparse(url).netloc} → starting at tier {best_tier}")

            # Sensitive sites: minimum tier 2 (E9)
            if profile.is_sensitive:
                start_tier = max(start_tier, 2)

        # Step 4: Configure proxy (fingerprint will be set later if available)
        needs_sticky = proxy_sticky if proxy_sticky is not None else profile.needs_sticky
        proxy = None
        if self.proxy_manager.is_configured and (profile.needs_proxy or proxy_geo):
            # Note: fingerprint is set in Step 5.5 and will be used to update proxy if needed
            proxy = self.proxy_manager.get_proxy(
                geo=proxy_geo,
                sticky=needs_sticky,
            )
            if verbose:
                print(f"[Proxy] Using {proxy.geo or 'default'} geo, sticky={needs_sticky}")

        # Step 5: Configure session
        should_persist = self._should_persist_session(profile, persist_session)
        session = None
        if session_id or should_persist:
            actual_session_id = session_id or f"auto_{hash(url) % 10000000:08d}"
            session = self.session_manager.get(actual_session_id)
            if not session:
                session = self.session_manager.create(actual_session_id, url)
            if verbose:
                print(f"[Session] Using session {actual_session_id}")

        # Step 5.5: Configure fingerprint persistence
        fingerprint = None
        if self.config.fingerprint_persist and (should_persist or profile.needs_sticky):
            domain = urlparse(url).netloc
            proxy_geo = proxy.geo if proxy else self.config.default_proxy_geo

            # Try to get existing fingerprint from session
            if session and session.fingerprint_id:
                fingerprint = self.fingerprint_manager.get_for_domain(domain)
                # Verify fingerprint still exists and matches
                if fingerprint and fingerprint.fingerprint_id != session.fingerprint_id:
                    fingerprint = None

            # Create new fingerprint if needed
            if not fingerprint:
                fingerprint = self.fingerprint_manager.get_or_create(domain, proxy_geo)

                # Link fingerprint to session
                if session:
                    session.fingerprint_id = fingerprint.fingerprint_id

            if verbose:
                print(f"[Fingerprint] Using {fingerprint.browser_version} for {domain}")

        # Step 6: Execute tier escalation
        result = None
        last_error = None

        # Build tier sequence based on start and max
        tiers_to_try = [t for t in self.TIER_SEQUENCE if start_tier <= t <= max_tier]

        # Skip Tier 1 for JA4T sites (transport-layer fingerprinting defeats TLS spoofing)
        if profile.uses_ja4t and profile.ja4t_confidence > 0.5 and 1 in tiers_to_try:
            tiers_to_try = [t for t in tiers_to_try if t != 1]
            if verbose:
                print(f"[JA4T] Skipping Tier 1 - transport-layer fingerprinting detected (confidence: {profile.ja4t_confidence:.0%})")

        for tier in tiers_to_try:
            if verbose:
                print(f"[Tier {tier}] Attempting...")

            # Rate limit check for browser tiers (E3)
            # Record AFTER success, not before, so failed attempts don't burn quota
            if self.rate_limiter and tier >= 2:
                rl_domain = urlparse(url).netloc
                wait = self.rate_limiter.wait_time(rl_domain)
                if wait > 0:
                    if verbose:
                        print(f"[RateLimit] Waiting {wait:.1f}s for {rl_domain}")
                    await asyncio.sleep(wait)

            try:
                result = await self._execute_tier(
                    tier=tier,
                    url=url,
                    proxy=proxy,
                    session_id=session.session_id if session else None,
                    actions=actions,
                    wait_for=wait_for,
                    timeout=timeout,
                    headers=headers,
                    extract_prompt=extract_prompt if tier == 4 else None,
                    extract_schema=extract_schema if tier == 4 else None,
                    fingerprint=fingerprint,
                    behavior_intensity=max(self.config.behavior_intensity, 1.3) if profile.is_sensitive else None,
                )

                if result.success:
                    if verbose:
                        print(f"[Tier {tier}] Success!")

                    # Check for paywall/restriction BEFORE recording success (E7 fix)
                    restriction = None
                    if result.html:
                        restriction = self.paywall_detector.detect(
                            result.html,
                            result.status_code or 200
                        )

                    if restriction:
                        # Attach restriction info to metadata
                        result.metadata = result.metadata or {}
                        result.metadata["restriction"] = {
                            "type": restriction.type,
                            "confidence": restriction.confidence,
                            "message": restriction.message,
                        }
                        if verbose:
                            print(f"[Detection] {restriction.type} detected (confidence: {restriction.confidence})")

                        # Handle 404 Not Found - mark as failure, don't retry
                        if restriction.type == "not_found":
                            # If detected by HTTP status code, trust it
                            if restriction.pattern == "http_404":
                                if verbose:
                                    print(f"[Detection] Page not found (HTTP 404) - marking as failed")
                                result.success = False
                                result.error = restriction.message or "Page not found"
                                result.error_type = "NotFound"
                                break

                            # If detected by content patterns, verify with HEAD request
                            if verbose:
                                print(f"[Detection] 404 pattern detected, verifying with HEAD request...")
                            verified_status = await self._verify_404(url, timeout=timeout)

                            if verified_status == 404:
                                if verbose:
                                    print(f"[Detection] Verified: HTTP 404 - page does not exist")
                                result.success = False
                                result.error = "Page not found (verified)"
                                result.error_type = "NotFound"
                                result.metadata["restriction"]["verified"] = True
                                result.metadata["restriction"]["verified_status"] = 404
                                break
                            elif verified_status and verified_status < 400:
                                # Page actually exists, content pattern was a false positive
                                if verbose:
                                    print(f"[Detection] False positive: HEAD returned {verified_status}, page exists")
                                result.metadata["restriction"]["verified"] = False
                                result.metadata["restriction"]["verified_status"] = verified_status
                                # Don't mark as failed, continue with the content we have
                            else:
                                # Couldn't verify or got another error, trust pattern detection
                                if verbose:
                                    print(f"[Detection] Could not verify (status={verified_status}), trusting pattern")
                                result.success = False
                                result.error = restriction.message or "Page likely not found"
                                result.error_type = "NotFound"
                                break

                        # CAPTCHA detected — treat as failure, escalate tier (E1 fix)
                        if restriction.type == "captcha":
                            if verbose:
                                print(f"[Detection] CAPTCHA in response — escalating to next tier")
                            result.success = False
                            result.error = "CAPTCHA detected in response content"
                            result.error_type = "CaptchaRequired"
                            self.fingerprint_manager.record_tier_attempt(
                                urlparse(url).netloc, tier, success=False
                            )
                            last_error = result.error
                            continue

                        # Only escalate to Brightdata for actionable restrictions
                        if self.paywall_detector.needs_brightdata(restriction):
                            if verbose:
                                print(f"[Detection] Trying Brightdata fallback...")
                            bd_result = await self._fetch_with_brightdata(
                                url, extract_prompt, extract_schema, output
                            )
                            # Preserve BrightdataRequired so caller can handle it
                            if bd_result.error_type == "BrightdataRequired":
                                return bd_result
                            result = bd_result
                            break

                    # No restriction (or benign) — record success AFTER validation
                    if fingerprint:
                        self.fingerprint_manager.record_usage(fingerprint.fingerprint_id, success=True)
                    self.fingerprint_manager.record_tier_attempt(
                        urlparse(url).netloc, tier, success=True
                    )
                    # Record rate limit usage on success only (E3 fix)
                    if self.rate_limiter and tier >= 2:
                        self.rate_limiter.record(urlparse(url).netloc)
                    break

                # If not successful, record error and continue
                last_error = result.error

                # Record tier failure for domain (E7)
                self.fingerprint_manager.record_tier_attempt(
                    urlparse(url).netloc, tier, success=False
                )

                # Record fingerprint failure on block
                if fingerprint and result.error_type == "Blocked":
                    self.fingerprint_manager.record_usage(fingerprint.fingerprint_id, success=False)

                    # Check if we should rotate fingerprint (skip for sensitive sites - E9)
                    if self.config.fingerprint_rotate_on_block and not profile.is_sensitive:
                        if self.fingerprint_manager.should_rotate(fingerprint.fingerprint_id):
                            if verbose:
                                print(f"[Fingerprint] Rotating due to blocks...")
                            fingerprint = self.fingerprint_manager.rotate(fingerprint.fingerprint_id)
                            if session:
                                session.fingerprint_id = fingerprint.fingerprint_id

            except (Blocked, CaptchaRequired, RateLimited, StuckDetected) as e:
                last_error = str(e)
                if verbose:
                    print(f"[Tier {tier}] {type(e).__name__}: {e}")

                # Record tier failure in exception path too (E7 fix)
                self.fingerprint_manager.record_tier_attempt(
                    urlparse(url).netloc, tier, success=False
                )

                # Record fingerprint failure
                if fingerprint:
                    self.fingerprint_manager.record_usage(fingerprint.fingerprint_id, success=False)

                # Rotate proxy on block
                if proxy and proxy.session_id:
                    proxy = self.proxy_manager.rotate_session(proxy.session_id, proxy.geo)
                continue

            except Exception as e:
                last_error = str(e)
                if verbose:
                    print(f"[Tier {tier}] Error: {e}")
                # Record tier failure for unexpected errors too (E7 fix)
                self.fingerprint_manager.record_tier_attempt(
                    urlparse(url).netloc, tier, success=False
                )
                continue

        # Step 7: Handle all tiers exhausted
        if not result or not result.success:
            # Check if result is already a BrightdataRequired signal — preserve it
            if result and result.error_type == "BrightdataRequired":
                return result

            # Last resort: try Brightdata
            if verbose:
                print("[Fallback] All tiers exhausted, trying Brightdata")
            bd_result = await self._fetch_with_brightdata(url, extract_prompt, extract_schema, output)

            # Preserve BrightdataRequired signal for caller
            if bd_result.error_type == "BrightdataRequired":
                return bd_result

            if not bd_result.success:
                return ScrapeResult(
                    success=False,
                    url=url,
                    error=last_error or "All tiers exhausted",
                    tier_used=max_tier,
                    metadata={"exhausted_tiers": list(range(start_tier, max_tier + 1))},
                )
            result = bd_result

        # Step 8: AI extraction if requested (and not already done by Tier 4)
        if (extract_prompt or extract_schema) and result.tier_used != 4:
            content = result.markdown or result.html
            if content:
                # Truncate if too long
                max_chars = 50000
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n\n... (truncated)"

                extraction_result = await self.ai_router.extract(
                    content=content,
                    extraction_prompt=extract_prompt or self._schema_to_prompt(extract_schema),
                    schema=extract_schema,
                )
                if extraction_result.get("success"):
                    result.extracted_data = extraction_result.get("data")
                    result.metadata = result.metadata or {}
                    result.metadata["extraction_model"] = extraction_result.get("model")
                    result.metadata["extraction_tier"] = extraction_result.get("tier")

        # Step 9: Save session if needed
        if session and should_persist and result.success:
            if result.cookies:
                session.cookies.update(result.cookies)
            session.url = result.final_url or url
            session.tier_used = result.tier_used
            if fingerprint:
                session.fingerprint_id = fingerprint.fingerprint_id
            self.session_manager.save(session)

            # Add fingerprint_id to result metadata
            if fingerprint:
                result.metadata = result.metadata or {}
                result.metadata["fingerprint_id"] = fingerprint.fingerprint_id

        # Step 10: Cache result
        if use_cache and result.success:
            self.cache_manager.set(url, mode, result, extract_prompt)

        return result

    async def _execute_tier(
        self,
        tier: int,
        url: str,
        proxy: Optional[ProxyConfig],
        session_id: Optional[str],
        actions: Optional[list],
        wait_for: Optional[str],
        timeout: int,
        headers: Optional[dict],
        extract_prompt: Optional[str] = None,
        extract_schema: Optional[dict] = None,
        fingerprint: Optional[FingerprintProfile] = None,
        behavior_intensity: Optional[float] = None,
    ) -> ScrapeResult:
        """Execute specific tier."""
        executor = self._get_tier(tier)

        if tier == 0:
            # Tier 0: Static extraction (no network request needed if we have HTML)
            return await executor.fetch(url)

        elif tier == 1:
            # Tier 1: TLS-spoofed HTTP
            return await executor.fetch(
                url=url,
                proxy=proxy,
                headers=headers,
                timeout=timeout,
                fingerprint=fingerprint,
            )

        elif tier == 2:
            # Tier 2: Scrapling StealthyFetcher
            return await executor.fetch(
                url=url,
                proxy=proxy,
                headers=headers,
                timeout=timeout,
                wait_for=wait_for,
                actions=actions,
            )

        elif tier == 2.5:
            # Tier 2.5: Agent-browser with network interception
            return await executor.fetch(
                url=url,
                proxy=proxy,
                headers=headers,
                timeout=timeout,
                session_id=session_id,
                wait_for=wait_for,
                actions=actions,
                block_trackers=self.config.block_trackers,
            )

        elif tier == 3:
            # Tier 3: Camoufox anti-detect
            return await executor.fetch(
                url=url,
                proxy=proxy,
                headers=headers,
                timeout=timeout,
                session_id=session_id,
                wait_for=wait_for,
                actions=actions,
                behavior_intensity=behavior_intensity,
            )

        elif tier == 4:
            # Tier 4: AI-assisted extraction
            return await executor.fetch(
                url=url,
                proxy=proxy,
                headers=headers,
                timeout=timeout,
                extract_prompt=extract_prompt,
                schema=extract_schema,
            )

        elif tier == 5:
            # Tier 5: Visual LLM extraction (screenshot + vision)
            return await executor.fetch(
                url=url,
                proxy=proxy,
                headers=headers,
                timeout=timeout,
                extract_prompt=extract_prompt,
                extract_schema=extract_schema,
                session_id=session_id,
                wait_for=wait_for,
            )

        raise ValueError(f"Unknown tier: {tier}")

    async def _fetch_with_brightdata(
        self,
        url: str,
        extract_prompt: Optional[str],
        extract_schema: Optional[dict],
        output: str,
    ) -> ScrapeResult:
        """Fetch using Brightdata Web Unlocker MCP as final fallback."""
        try:
            # Import MCP client dynamically
            import httpx

            # Placeholder for premium proxy/unlocker integration
            # Override this method to call your preferred service
            async with httpx.AsyncClient() as client:
                pass

        except Exception as e:
            pass

        # Return a result that indicates premium proxy/unlocker is needed
        # The CLI or calling code will handle the service invocation
        return ScrapeResult(
            success=False,
            url=url,
            error="All tiers exhausted. Use a premium proxy/web unlocker service for this URL.",
            error_type="BrightdataRequired",
            tier_used=-1,
            metadata={
                "brightdata_recommended": True,
                "extract_prompt": extract_prompt,
                "extract_schema": extract_schema,
                "output_format": output,
            },
        )

    def _should_persist_session(
        self,
        profile: ScrapeProfile,
        user_override: Optional[bool],
    ) -> bool:
        """Determine if session should be persisted."""
        if user_override is not None:
            return user_override

        return any([
            profile.antibot in ["cloudflare", "cloudflare_uam", "datadome", "akamai", "perimeterx"],
            profile.needs_sticky,
            profile.requires_login,
        ])

    def _build_cache_key(
        self,
        url: str,
        extract_prompt: Optional[str],
        extract_schema: Optional[dict],
    ) -> str:
        """Build cache key from URL and extraction params."""
        import hashlib
        key_parts = [url]
        if extract_prompt:
            key_parts.append(f"prompt:{extract_prompt}")
        if extract_schema:
            key_parts.append(f"schema:{json.dumps(extract_schema, sort_keys=True)}")
        key_str = "|".join(key_parts)
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]

    def _schema_to_prompt(self, schema: dict) -> str:
        """Convert JSON schema to extraction prompt."""
        if not schema:
            return ""

        properties = schema.get("properties", {})
        required = schema.get("required", [])

        fields = []
        for name, spec in properties.items():
            field_type = spec.get("type", "string")
            description = spec.get("description", "")
            req = "(required)" if name in required else "(optional)"
            fields.append(f"- {name}: {field_type} {req} {description}")

        return "Extract the following fields as JSON:\n" + "\n".join(fields)

    async def extract_from_html(
        self,
        html: str,
        extract_prompt: str,
        extract_schema: Optional[dict] = None,
        url: str = "",
    ) -> ScrapeResult:
        """
        Extract data from pre-fetched HTML.

        Useful when you already have HTML content and just need extraction.
        """
        tier4 = self._get_tier(4)
        return await tier4.extract_from_html(
            html=html,
            extract_prompt=extract_prompt,
            schema=extract_schema,
            url=url,
        )

    async def probe(self, url: str) -> ScrapeProfile:
        """
        Probe URL to detect site characteristics.

        Returns profile with recommended tier, anti-bot detection, etc.
        """
        return await self.mode_detector.probe(url)

    async def scrape_batch(
        self,
        urls: list[str],
        max_concurrent: int = 5,
        **kwargs,
    ) -> list[ScrapeResult]:
        """
        Scrape multiple URLs concurrently.

        Uses isolated sessions for each URL to avoid cross-contamination.

        Args:
            urls: List of URLs to scrape
            max_concurrent: Maximum concurrent scrapes (default 5)
            **kwargs: Arguments passed to scrape() for each URL

        Returns:
            List of ScrapeResults in same order as input URLs
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results = [None] * len(urls)

        # Copy kwargs to avoid mutating shared dict across concurrent tasks
        batch_kwargs = {k: v for k, v in kwargs.items() if k != "session_id"}
        caller_session_id = kwargs.get("session_id")

        async def scrape_with_semaphore(index: int, url: str):
            async with semaphore:
                # Use isolated session for each URL
                session_id = caller_session_id
                if not session_id:
                    session_id = f"batch_{index}_{hash(url) % 10000:04d}"

                result = await self.scrape(
                    url=url,
                    session_id=session_id,
                    **batch_kwargs,
                )
                results[index] = result

        # Run all scrapes concurrently (limited by semaphore)
        tasks = [
            scrape_with_semaphore(i, url)
            for i, url in enumerate(urls)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Convert any exceptions to failed results
        for i, result in enumerate(results):
            if result is None or isinstance(result, Exception):
                results[i] = ScrapeResult(
                    success=False,
                    url=urls[i],
                    error=str(result) if isinstance(result, Exception) else "Unknown error",
                    error_type="BatchError",
                )

        return results

    async def close(self):
        """Cleanup resources."""
        # Close any open tiers
        for tier in self._tiers.values():
            if hasattr(tier, "close"):
                await tier.close()
