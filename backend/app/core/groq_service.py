import asyncio
import os
import json
import logging
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape

import httpx

# Try to import official groq SDK; if not available, fallback to HTTPX-based calls
try:
    import groq  # type: ignore
    _HAS_GROQ_SDK = True
except Exception:
    _HAS_GROQ_SDK = False

ENV_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv(dotenv_path=ENV_FILE, override=False)

VERIFY_SSL = os.getenv("DISABLE_SSL_VERIFICATION", "false").lower() not in ("1", "true", "yes")
MOCK_MODE = os.getenv("GROQ_MOCK_MODE", "false").lower() in ("1", "true", "yes")
DEFAULT_GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"
DEFAULT_OLLAMA_API_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_OLLAMA_MODEL = "llama3.2"

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

PROMPTS_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts")
ENV = Environment(
    loader=FileSystemLoader(PROMPTS_PATH),
    autoescape=select_autoescape(enabled_extensions=("j2",))
)


class GroqServiceError(Exception):
    pass


class GroqService:
    """Wrapper around Groq LLM access.

    - Reads configuration from environment by default (GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL)
    - Attempts to use the official SDK when available; otherwise falls back to HTTP requests.
    - Methods return structured JSON (dicts / lists) by parsing model output as JSON.

    Production-ready notes:
    - Timeouts and retries should be controlled by upstream caller or via HTTPX client options.
    - Keep prompts under version control and include prompt/mode metadata in run manifests.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        provider: Optional[str] = None,
    ):
        self.api_key = (api_key or os.getenv("GROQ_API_KEY") or "").strip()
        self.provider = (provider or os.getenv("AI_PROVIDER") or "groq").strip().lower()
        if self.provider == "ollama":
            self.api_url = (api_url or os.getenv("OLLAMA_API_URL") or DEFAULT_OLLAMA_API_URL).strip()
            self.model = (model or os.getenv("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL).strip()
        else:
            self.api_url = (api_url or os.getenv("GROQ_API_URL") or DEFAULT_GROQ_API_URL).strip()
            self.model = (model or os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL).strip()
        self.timeout = timeout or int(os.getenv("GROQ_TIMEOUT_SECONDS", "30"))
        self.mock_mode = MOCK_MODE

        if self.provider != "ollama" and not self.api_key:
            LOGGER.warning("GROQ_API_KEY not set; calls will fail until configured")

        # Initialize SDK client if available
        self._client = None
        if _HAS_GROQ_SDK:
            try:
                # NOTE: SDK initialization may differ; adapt when integrating actual SDK
                self._client = groq.Client(api_key=self.api_key)
                LOGGER.info("Using groq SDK client")
            except Exception as e:
                LOGGER.exception("Failed to initialize groq SDK client: %s", e)
                self._client = None

    def _mock_response_for_prompt(self, prompt: str) -> Dict[str, Any]:
        """Return a small, plausible mocked response depending on the rendered prompt text.

        This is only for local development when GROQ_MOCK_MODE=true. The responses are intentionally
        minimal but valid JSON structures that the rest of the pipeline can consume.
        """
        text = (prompt or "").lower()

        # Scenarios
        if "scenario" in text and "testcase" not in text and "selenium" not in text:
            scenarios = [
                {
                    "id": "s1",
                    "module": "Page",
                    "test_scenario_id": "TS_01",
                    "title": "Verify the page loads and primary content renders correctly.",
                    "description": "Verify the page loads and primary content renders correctly.",
                    "priority": "high",
                    "mapping": {"page": "load"},
                }
            ]
            if "form" in text or "input" in text:
                scenarios.extend([
                    {
                        "id": "s2",
                        "module": "Page",
                        "test_scenario_id": "TS_02",
                        "title": "Verify required form fields are present and visible.",
                        "description": "Verify required form fields are present and visible.",
                        "priority": "high",
                        "mapping": {"feature": "form-fields"},
                    },
                    {
                        "id": "s3",
                        "module": "Page",
                        "test_scenario_id": "TS_03",
                        "title": "Verify the form can be submitted successfully with valid values.",
                        "description": "Verify the form can be submitted successfully with valid values.",
                        "priority": "high",
                        "mapping": {"feature": "form-submit"},
                    },
                    {
                        "id": "s4",
                        "module": "Page",
                        "test_scenario_id": "TS_04",
                        "title": "Verify form validation errors appear for missing or invalid input.",
                        "description": "Verify form validation errors appear for missing or invalid input.",
                        "priority": "high",
                        "mapping": {"feature": "form-validation"},
                    },
                ])
            if "button" in text or "cta" in text:
                scenarios.append(
                    {
                        "id": "s5",
                        "module": "Page",
                        "test_scenario_id": "TS_05",
                        "title": "Verify CTA buttons are visible and trigger the expected action.",
                        "description": "Verify CTA buttons are visible and trigger the expected action.",
                        "priority": "medium",
                        "mapping": {"feature": "button-actions"},
                    }
                )
            if "link" in text:
                scenarios.append(
                    {
                        "id": "s6",
                        "module": "Page",
                        "test_scenario_id": "TS_06",
                        "title": "Verify navigation links route to the correct destinations.",
                        "description": "Verify navigation links route to the correct destinations.",
                        "priority": "medium",
                        "mapping": {"feature": "links"},
                    }
                )
            return {"scenarios": scenarios}

        # Selenium code bundle (prioritize selenium detection because some prompts include the word "testcase")
        if "selenium" in text or "page object" in text or "pytest" in text:
            return {
                "files": {
                    "tests/test_generated.py": "import pytest\n\n def test_placeholder():\n     assert True\n",
                },
                "metadata": {"framework": "pytest", "selenium": "python", "notes": "mocked"},
            }

        # Testcases
        if "testcase" in text or "test cases" in text:
            return {
                "testcases": [
                    {
                        "id": "t1",
                        "title": "Verify page title",
                        "description": "Check that the page title is present and correct",
                        "preconditions": [],
                        "steps": [
                            {"action": "navigate", "selector": "", "value": "{{url}}"},
                            {"action": "assert_title", "selector": "", "value": ""},
                        ],
                        "expected_result": {"title_present": True},
                    }
                ]
            }

        # Test data
        if "test data" in text or "testdata" in text:
            return {"username": "standard_user", "password": "secret_sauce", "product": "Sauce Labs Backpack"}

        # Demo insights
        if "defect_possibilities" in text or "demo" in text or "risk_areas" in text:
            return {
                "defect_possibilities": [
                    {"id": "d1", "description": "Login failures under load", "likelihood": "medium"}
                ],
                "risk_areas": ["authentication", "checkout flow"],
                "automation_coverage_percent": 45,
                "recommended_smoke_tests": ["login smoke", "add-to-cart smoke"],
            }

        # Fallback: return a minimal empty structure
        return {}

    async def _call_model(self, prompt: str) -> Dict[str, Any]:
        """Call the Groq model with the rendered prompt and return raw response.

        Tries SDK first, then HTTP fallback. Expects the model to return JSON or a textual JSON payload.
        """
        if self.mock_mode:
            LOGGER.info("Using mock Groq responses")
            return self._mock_response_for_prompt(prompt)

        if self.provider == "ollama":
            return await self._call_ollama(prompt)

        if _HAS_GROQ_SDK and self._client is not None:
            try:
                # Example SDK usage — adapt to real SDK API
                response = self._client.generate(model=self.model, prompt=prompt, timeout=self.timeout)
                # SDK may be sync; wrap in dict for uniformity
                raw = response if isinstance(response, dict) else {"output": str(response)}
                return raw
            except Exception as e:
                LOGGER.exception("Groq SDK call failed: %s", e)
                raise GroqServiceError("Groq SDK call failed")

        # HTTP fallback
        if not self.api_url:
            raise GroqServiceError("No GROQ_API_URL configured for HTTP fallback")
        if not self.api_key:
            raise GroqServiceError(
                "GROQ_API_KEY is not configured. Set GROQ_API_KEY in backend/.env "
                "or enable GROQ_MOCK_MODE=true for local development."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 2048,
        }

        # Some Groq endpoints still support the older /generate style payload; if the configured URL
        # does not look like the OpenAI-compatible chat endpoint, use the older schema instead.
        if "/chat/completions" not in self.api_url and "/v1/" not in self.api_url:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "temperature": 0.2,
                "max_tokens": 2048,
            }

        async with httpx.AsyncClient(timeout=self.timeout, verify=VERIFY_SSL) as client:
            last_error: Optional[Exception] = None
            for attempt in range(3):
                try:
                    resp = await client.post(self.api_url, json=payload, headers=headers)
                    resp.raise_for_status()
                    raw = resp.json()
                    return raw
                except httpx.HTTPStatusError as e:
                    last_error = e
                    if e.response is not None and e.response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                        wait_seconds = 2 ** attempt
                        LOGGER.warning("Groq API returned %s; retrying in %s seconds (attempt %s/3)", e.response.status_code, wait_seconds, attempt + 1)
                        await asyncio.sleep(wait_seconds)
                        continue
                    LOGGER.exception("HTTP call to Groq API failed: %s", e)
                    detail = e.response.text[:500].strip() if e.response is not None else str(e)
                    status = e.response.status_code if e.response is not None else "unknown"
                    if "internet security" in detail.lower() or "<html" in detail.lower():
                        detail = (
                            "A network security gateway blocked the Groq request. "
                            "Allow https://api.groq.com through the firewall/proxy, "
                            "or use GROQ_MOCK_MODE=true for local development."
                        )
                    raise GroqServiceError(
                        f"Groq API returned HTTP {status}: {detail}"
                    ) from e
                except httpx.HTTPError as e:
                    last_error = e
                    if attempt < 2:
                        wait_seconds = 2 ** attempt
                        LOGGER.warning("Transient HTTP error from Groq; retrying in %s seconds (attempt %s/3)", wait_seconds, attempt + 1)
                        await asyncio.sleep(wait_seconds)
                        continue
                    LOGGER.exception("HTTP call to Groq API failed: %s", e)
                    raise GroqServiceError(f"Groq HTTP request failed: {e}") from e

            if last_error is not None:
                raise GroqServiceError(f"Groq HTTP request failed: {last_error}") from last_error

            raise GroqServiceError("Groq HTTP request failed")

    async def _call_ollama(self, prompt: str) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.2},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            detail = exc.response.text[:500].strip() if exc.response is not None else str(exc)
            raise GroqServiceError(f"Ollama API returned HTTP {status}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise GroqServiceError(
                f"Cannot connect to Ollama at {self.api_url}. Start Ollama and run: ollama pull {self.model}"
            ) from exc

    def _parse_json_output(self, raw_text: str) -> Any:
        """Try to extract JSON from a model response string.

        The model may return code fences, or plain JSON. This helper tries to robustly parse JSON.
        """
        text = raw_text.strip()

        # Remove common code fences
        if text.startswith("```"):
            text = text.strip("`")
            if "\n" in text:
                first_newline = text.find("\n")
                if first_newline != -1:
                    text = text[first_newline + 1 :]
            text = text.strip()

        # Try direct parse
        try:
            return json.loads(text)
        except Exception:
            decoder = json.JSONDecoder()
            for idx, char in enumerate(text):
                if char in "[{":
                    try:
                        parsed, _ = decoder.raw_decode(text[idx:])
                        return parsed
                    except json.JSONDecodeError:
                        continue
            LOGGER.debug("Failed to parse JSON fragment from model output")
            raise GroqServiceError("Model returned non-JSON output")

    def _extract_text_from_response(self, raw: Any) -> Optional[str]:
        """Extract a textual content field from a Groq/OpenAI-style response payload."""
        if isinstance(raw, str):
            return raw

        if not isinstance(raw, dict):
            return None

        ollama_message = raw.get("message")
        if isinstance(ollama_message, dict) and isinstance(ollama_message.get("content"), str):
            return ollama_message["content"]

        # OpenAI/Groq chat-completions format
        choices = raw.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content
                    if isinstance(content, list):
                        parts = []
                        for item in content:
                            if isinstance(item, dict):
                                if isinstance(item.get("text"), str):
                                    parts.append(item["text"])
                                elif isinstance(item.get("content"), str):
                                    parts.append(item["content"])
                        if parts:
                            return "".join(parts)

                if isinstance(first.get("text"), str):
                    return first.get("text")

        # Legacy keys
        for key in ("output", "text", "result"):
            if key in raw:
                candidate = raw[key]
                if isinstance(candidate, str):
                    return candidate
                if isinstance(candidate, list) and candidate:
                    candidate = candidate[0]
                    if isinstance(candidate, str):
                        return candidate

        return None

    async def _render_and_call(self, template_name: str, context: Dict[str, Any], allow_raw_text: bool = False) -> Any:
        template = ENV.get_template(template_name)
        prompt_text = template.render(**context)
        raw = await self._call_model(prompt_text)

        # raw could be a dict from the Groq/OpenAI API with chat completion payloads.
        if isinstance(raw, dict):
            text = self._extract_text_from_response(raw)
            if text is not None:
                try:
                    return self._parse_json_output(text)
                except GroqServiceError:
                    if allow_raw_text:
                        return text
                    LOGGER.debug("Could not parse JSON from extracted model text; returning raw payload")
                    return raw

            # Fall back to raw dict if it is already structured JSON from a non-chat endpoint.
            if "choices" in raw and raw["choices"]:
                return raw

            return raw

        # If raw is a string, parse JSON
        if isinstance(raw, str):
            try:
                return self._parse_json_output(raw)
            except GroqServiceError:
                if allow_raw_text:
                    return raw
                raise

        return raw

    async def generate_scenarios(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate high-level test scenarios from page analysis.

        Returns a structured dict (scenarios list).
        """
        context = {"analysis": analysis, "url": analysis.get("url")}
        parsed = await self._render_and_call("generate_scenarios.j2", context)
        return parsed

    async def generate_testcases(self, scenarios: Dict[str, Any]) -> Dict[str, Any]:
        """Generate detailed test cases from scenarios.
        """
        context = {"scenarios": scenarios}
        parsed = await self._render_and_call("generate_testcases.j2", context)
        return parsed

    async def generate_selenium_code(
        self,
        test_case: Dict[str, Any],
        test_data: Dict[str, Any],
    ) -> str:
        """Generate raw executable pytest Selenium code from upstream outputs."""
        context = {"test_case": test_case, "test_data": test_data}
        generated = await self._render_and_call(
            "generate_selenium.j2",
            context,
            allow_raw_text=True,
        )
        if isinstance(generated, str):
            return generated.strip()
        raise GroqServiceError("Selenium generator returned a non-code response")

    async def generate_demo_insights(self, artifacts: Dict[str, Any]) -> Dict[str, Any]:
        """Generate demo-mode insights for well-known demo sites (e.g., saucedemo.com).

        Expected output JSON keys:
          - defect_possibilities: list of {id, description, likelihood}
          - risk_areas: list of strings or {area, reason}
          - automation_coverage_percent: number (0-100)
          - recommended_smoke_tests: list of scenario/testcase summaries

        Returns parsed JSON dict.
        """
        context = {"artifacts": artifacts}
        parsed = await self._render_and_call("generate_demo_insights.j2", context)
        return parsed
