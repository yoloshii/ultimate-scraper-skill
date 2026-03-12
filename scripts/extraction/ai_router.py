"""AI extraction router with 3-tier LLM fallback."""

import time
import json
import re
from typing import Optional, Any
from core.config import get_config


# System prompt optimized for extraction
EXTRACTION_SYSTEM_PROMPT = """You are a data extraction assistant. Always respond in English.
Extract the requested data in the exact JSON format specified.
If a field cannot be found, use null.
Do not add explanations or markdown formatting.
Respond only with valid JSON."""


class AIExtractionRouter:
    """
    Route AI extraction: Local LLM → z.ai GLM-4.5-Air → Haiku.

    Three-tier routing:
    1. Local LLM (any OpenAI-compatible API)
    2. z.ai GLM-4.5-Air (rate limited fallback)
    3. Claude Haiku (final fallback)
    """

    def __init__(self):
        self.config = get_config()

        # Rate limit tracking for z.ai
        self.zai_rate_limited = False
        self.zai_rate_limit_reset: Optional[float] = None

        # Local model availability
        self._local_available: Optional[bool] = None

    async def extract(
        self,
        content: str,
        extraction_prompt: str,
        schema: Optional[dict] = None,
        prefer_local: bool = True,
    ) -> dict:
        """
        Extract data with three-tier fallback: Local → z.ai → Haiku.

        Args:
            content: HTML/text content to extract from
            extraction_prompt: Natural language extraction instruction
            schema: Optional JSON schema for structured output
            prefer_local: Whether to prefer local model (default True)

        Returns:
            Dict with extracted data or error info
        """
        # Build the full prompt
        full_prompt = self._build_prompt(extraction_prompt, schema)

        # Tier 0: Try local GLM-4.7-Flash first (preferred)
        if prefer_local and self._is_local_available():
            try:
                result = await self._extract_local(content, full_prompt)
                if result.get("success"):
                    return result
            except Exception as e:
                pass  # Fall through to z.ai

        # Tier 1: Try z.ai GLM-4.5-Air (unless rate limited)
        if self.config.zai_configured and not self._is_zai_rate_limited():
            try:
                result = await self._extract_with_zai(content, full_prompt)
                if result.get("success"):
                    return result
                if result.get("error_type") == "RateLimited":
                    self._mark_zai_rate_limited(result.get("reset_time", time.time() + 300))
            except Exception as e:
                pass  # Fall through to Haiku

        # Tier 2: Fallback to Haiku
        try:
            return await self._extract_with_haiku(content, full_prompt)
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def _extract_local(self, content: str, prompt: str) -> dict:
        """Extract using local LLM (any OpenAI-compatible API)."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.config.local_llm_url,
                    json={
                        "model": "local",
                        "messages": [
                            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                            {"role": "user", "content": f"{prompt}\n\nContent:\n{content}"},
                        ],
                        "temperature": 0.1,
                    },
                    timeout=120,
                )
                response.raise_for_status()
                result_text = response.json()["choices"][0]["message"]["content"]

                return {
                    "success": True,
                    "data": self._parse_json_response(result_text),
                    "model": "local-glm-4.7-flash",
                    "tier": "local",
                }

        except httpx.ConnectError:
            self._local_available = False
            raise
        except Exception as e:
            raise

    async def _extract_with_zai(self, content: str, prompt: str) -> dict:
        """Extract using GLM-4.5-Air via z.ai Coding Plan API."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.config.zai_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.config.zai_api_key}"},
                    json={
                        "model": "glm-4.5-air",
                        "messages": [
                            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                            {"role": "user", "content": f"{prompt}\n\nContent:\n{content}"},
                        ],
                        "temperature": 0.1,
                    },
                    timeout=self.config.zai_timeout_ms / 1000,
                )

                if response.status_code == 429:
                    # Parse reset time from headers if available
                    reset_time = time.time() + 300  # Default 5 min
                    return {
                        "success": False,
                        "error": "Rate limited",
                        "error_type": "RateLimited",
                        "reset_time": reset_time,
                    }

                response.raise_for_status()
                result_text = response.json()["choices"][0]["message"]["content"]

                return {
                    "success": True,
                    "data": self._parse_json_response(result_text),
                    "model": "glm-4.5-air",
                    "tier": "zai",
                }

        except Exception as e:
            raise

    async def _extract_with_haiku(self, content: str, prompt: str) -> dict:
        """Extract using Claude Haiku via Anthropic API."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.config.anthropic_max_url}/v1/messages",
                    json={
                        "model": "claude-haiku-4-5",
                        "max_tokens": 4096,
                        "system": EXTRACTION_SYSTEM_PROMPT,
                        "messages": [
                            {"role": "user", "content": f"{prompt}\n\nContent:\n{content}"},
                        ],
                    },
                    timeout=60,
                )
                response.raise_for_status()
                result_text = response.json()["content"][0]["text"]

                return {
                    "success": True,
                    "data": self._parse_json_response(result_text),
                    "model": "claude-haiku-4-5",
                    "tier": "haiku",
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    def _build_prompt(self, extraction_prompt: str, schema: Optional[dict]) -> str:
        """Build the full extraction prompt."""
        if schema:
            schema_str = json.dumps(schema, indent=2)
            return f"""{extraction_prompt}

Return the data as JSON matching this schema:
```json
{schema_str}
```"""
        return extraction_prompt

    def _parse_json_response(self, text: str) -> Any:
        """Parse JSON from LLM response, handling markdown code blocks."""
        text = text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```)
            lines = lines[1:]
            # Remove last line (```)
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        # Try to parse as JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in response
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

            # Try to find JSON array
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

            # Return raw text if JSON parsing fails
            return {"raw_response": text}

    def _is_local_available(self) -> bool:
        """Check if local model server is available."""
        if not self.config.local_llm_configured:
            return False

        if self._local_available is not None:
            return self._local_available

        # Quick health check
        try:
            import httpx
            base_url = self.config.local_llm_url.rsplit("/", 2)[0]
            resp = httpx.get(f"{base_url}/health", timeout=2)
            self._local_available = resp.status_code == 200
        except Exception:
            self._local_available = False

        return self._local_available

    def _is_zai_rate_limited(self) -> bool:
        """Check if z.ai is currently rate limited."""
        if not self.zai_rate_limited:
            return False
        if self.zai_rate_limit_reset and time.time() > self.zai_rate_limit_reset:
            self.zai_rate_limited = False
            return False
        return True

    def _mark_zai_rate_limited(self, reset_time: float) -> None:
        """Mark z.ai as rate limited."""
        self.zai_rate_limited = True
        self.zai_rate_limit_reset = reset_time

    async def get_status(self) -> dict:
        """Get status of all LLM tiers."""
        status = {
            "local": {
                "configured": self.config.local_llm_configured,
                "available": self._is_local_available() if self.config.local_llm_configured else False,
                "url": self.config.local_llm_url,
            },
            "zai": {
                "configured": self.config.zai_configured,
                "rate_limited": self._is_zai_rate_limited(),
                "reset_time": self.zai_rate_limit_reset,
            },
            "haiku": {
                "configured": True,  # Always available via Anthropic API
                "url": self.config.anthropic_max_url,
            },
        }
        return status
