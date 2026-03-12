"""Vision LLM extraction router for screenshot-based data extraction.

Uses vision-capable LLMs (Claude Haiku 4.5) to extract structured data
from webpage screenshots, bypassing DOM-based detection.
"""

import json
import base64
import httpx
from typing import Optional, Any
from core.config import get_config


VISION_SYSTEM_PROMPT = """You are a visual data extraction assistant specialized in extracting structured information from webpage screenshots.

Your task is to:
1. Analyze the screenshot carefully
2. Extract the requested information based on the user's prompt
3. Return ONLY valid JSON matching the requested format

Guidelines:
- Look for visible text, numbers, prices, dates, names, etc.
- Handle partial visibility - extract what you can see
- Use null for fields you cannot determine from the image
- Be precise with numbers and prices (include currency symbols)
- Handle multiple items by returning arrays when appropriate

IMPORTANT: Your entire response must be valid JSON. Do not include any text before or after the JSON."""


class VisionExtractionRouter:
    """Route vision extraction requests to capable LLMs."""

    def __init__(self):
        self.config = get_config()

    async def extract_from_image(
        self,
        image_base64: str,
        extraction_prompt: str,
        schema: Optional[dict] = None,
        model: str = "claude-haiku-4-5-20241022",
    ) -> dict:
        """
        Extract data from a screenshot using vision LLM.

        Args:
            image_base64: Base64-encoded PNG/JPEG screenshot
            extraction_prompt: Natural language description of what to extract
            schema: Optional JSON schema for structured output
            model: Model to use for extraction

        Returns:
            dict with 'success', 'data', 'model', 'error' keys
        """
        # Build the prompt
        user_prompt = self._build_extraction_prompt(extraction_prompt, schema)

        # Try anthropic-max router first (local)
        result = await self._try_anthropic_max(image_base64, user_prompt, model)
        if result.get("success"):
            return result

        # Fallback to z.ai if configured
        if self.config.zai_configured:
            result = await self._try_zai(image_base64, user_prompt)
            if result.get("success"):
                return result

        return {
            "success": False,
            "data": None,
            "model": None,
            "error": result.get("error", "All vision extraction methods failed"),
        }

    async def _try_anthropic_max(
        self,
        image_base64: str,
        user_prompt: str,
        model: str,
    ) -> dict:
        """Try extraction via anthropic-max router."""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # anthropic-max expects OpenAI-compatible format
                response = await client.post(
                    f"{self.config.anthropic_max_url}/v1/chat/completions",
                    json={
                        "model": model,
                        "max_tokens": 4096,
                        "messages": [
                            {
                                "role": "system",
                                "content": VISION_SYSTEM_PROMPT,
                            },
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": self._detect_media_type(image_base64),
                                            "data": image_base64,
                                        },
                                    },
                                    {
                                        "type": "text",
                                        "text": user_prompt,
                                    },
                                ],
                            },
                        ],
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    parsed = self._parse_json_response(content)
                    return {
                        "success": True,
                        "data": parsed,
                        "model": model,
                        "error": None,
                    }
                else:
                    return {
                        "success": False,
                        "data": None,
                        "model": model,
                        "error": f"anthropic-max returned {response.status_code}: {response.text[:200]}",
                    }

        except Exception as e:
            return {
                "success": False,
                "data": None,
                "model": model,
                "error": f"anthropic-max error: {str(e)}",
            }

    async def _try_zai(
        self,
        image_base64: str,
        user_prompt: str,
    ) -> dict:
        """Try extraction via z.ai API."""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.config.zai_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.config.zai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "claude-3-5-haiku-20241022",  # z.ai model name
                        "max_tokens": 4096,
                        "messages": [
                            {
                                "role": "system",
                                "content": VISION_SYSTEM_PROMPT,
                            },
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:{self._detect_media_type(image_base64)};base64,{image_base64}",
                                        },
                                    },
                                    {
                                        "type": "text",
                                        "text": user_prompt,
                                    },
                                ],
                            },
                        ],
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    parsed = self._parse_json_response(content)
                    return {
                        "success": True,
                        "data": parsed,
                        "model": "claude-3-5-haiku-20241022",
                        "error": None,
                    }
                else:
                    return {
                        "success": False,
                        "data": None,
                        "model": "claude-3-5-haiku-20241022",
                        "error": f"z.ai returned {response.status_code}: {response.text[:200]}",
                    }

        except Exception as e:
            return {
                "success": False,
                "data": None,
                "model": None,
                "error": f"z.ai error: {str(e)}",
            }

    def _build_extraction_prompt(
        self,
        extraction_prompt: str,
        schema: Optional[dict],
    ) -> str:
        """Build the extraction prompt with optional schema."""
        prompt_parts = [extraction_prompt]

        if schema:
            prompt_parts.append("\n\nReturn the data as JSON matching this schema:")
            prompt_parts.append(f"```json\n{json.dumps(schema, indent=2)}\n```")
        else:
            prompt_parts.append("\n\nReturn the extracted data as a JSON object.")

        return "\n".join(prompt_parts)

    def _parse_json_response(self, content: str) -> Any:
        """Parse JSON from LLM response, handling markdown code blocks."""
        content = content.strip()

        # Try direct JSON parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end > start:
                json_str = content[start:end].strip()
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

        # Try extracting from generic code block
        if "```" in content:
            start = content.find("```") + 3
            # Skip language identifier if present
            newline = content.find("\n", start)
            if newline > start:
                start = newline + 1
            end = content.find("```", start)
            if end > start:
                json_str = content[start:end].strip()
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

        # Return as-is if can't parse
        return {"raw_response": content}

    def _detect_media_type(self, base64_data: str) -> str:
        """Detect image media type from base64 data."""
        # Check for common image signatures
        try:
            header = base64.b64decode(base64_data[:20])
            if header.startswith(b'\x89PNG'):
                return "image/png"
            elif header.startswith(b'\xff\xd8\xff'):
                return "image/jpeg"
            elif header.startswith(b'GIF'):
                return "image/gif"
            elif header.startswith(b'RIFF') and b'WEBP' in header:
                return "image/webp"
        except Exception:
            pass

        # Default to PNG (most screenshots)
        return "image/png"
