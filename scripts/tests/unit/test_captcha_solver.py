"""Unit tests for CaptchaSolver (module-level, no network calls)."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from captcha.solver import CaptchaSolver, EXTRACT_SITEKEY_JS, INJECT_TOKEN_JS


class TestCaptchaSolverConfig:
    """Tests for CaptchaSolver configuration."""

    def test_no_keys_not_configured(self):
        """Solver with no keys is not configured."""
        solver = CaptchaSolver(capsolver_key="", twocaptcha_key="")
        assert solver.configured is False

    def test_capsolver_key_configured(self):
        """Solver with capsolver key is configured."""
        solver = CaptchaSolver(capsolver_key="test-key")
        assert solver.configured is True

    def test_twocaptcha_key_configured(self):
        """Solver with 2captcha key is configured."""
        solver = CaptchaSolver(twocaptcha_key="test-key")
        assert solver.configured is True

    def test_both_keys_configured(self):
        """Solver with both keys is configured."""
        solver = CaptchaSolver(capsolver_key="k1", twocaptcha_key="k2")
        assert solver.configured is True


class TestSitekeyExtractionJS:
    """Tests for EXTRACT_SITEKEY_JS validity."""

    def test_js_is_iife(self):
        """Extraction JS is a self-executing function."""
        assert EXTRACT_SITEKEY_JS.strip().startswith("(")
        assert EXTRACT_SITEKEY_JS.strip().endswith(")")

    def test_returns_result_object(self):
        """JS creates result object with expected fields."""
        assert "result.type" in EXTRACT_SITEKEY_JS
        assert "result.sitekey" in EXTRACT_SITEKEY_JS
        assert "result.action" in EXTRACT_SITEKEY_JS


class TestTokenInjectionJS:
    """Tests for INJECT_TOKEN_JS templates."""

    def test_all_captcha_types_have_injectors(self):
        """All supported CAPTCHA types have injection JS."""
        expected_types = ["recaptcha_v2", "recaptcha_v3", "hcaptcha", "turnstile"]
        for ct in expected_types:
            assert ct in INJECT_TOKEN_JS, f"Missing injector for {ct}"

    def test_injectors_are_arrow_functions(self):
        """Token injection JS accepts token as parameter."""
        for ct, js in INJECT_TOKEN_JS.items():
            assert "(token)" in js, f"{ct} injector doesn't accept token param"

    def test_no_string_interpolation_in_templates(self):
        """Templates don't interpolate token as string literal (security)."""
        for ct, js in INJECT_TOKEN_JS.items():
            # The JS should use the `token` parameter, not an f-string
            assert "'{token}'" not in js, f"{ct} has unsafe string interpolation"
            assert "f'" not in js, f"{ct} has f-string"
