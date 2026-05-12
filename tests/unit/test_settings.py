# Author: Bradley R. Kinnard
"""unit tests for ironroot.settings."""

from __future__ import annotations

import pytest

from ironroot.settings import INSECURE_DEFAULT_PASSWORDS, Settings


class TestInsecurePasswordGuard:
    """Phase 0.9: refuse insecure DB passwords in non-debug mode."""

    @pytest.mark.parametrize("bad_password", sorted(INSECURE_DEFAULT_PASSWORDS))
    def test_non_debug_rejects_known_insecure_passwords(self, bad_password: str) -> None:
        with pytest.raises(ValueError, match="IRONROOT_DB_PASSWORD"):
            Settings(debug=False, db_password=bad_password, _env_file=None)  # type: ignore[call-arg]

    def test_debug_accepts_insecure_password(self) -> None:
        s = Settings(debug=True, db_password="changeme", _env_file=None)  # type: ignore[call-arg]
        assert s.db_password == "changeme"

    def test_non_debug_accepts_real_password(self) -> None:
        s = Settings(
            debug=False,
            db_password="s3cret-not-default",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert s.db_password == "s3cret-not-default"


class TestCorsAllowedOrigins:
    """Phase 0.9: CORS rules differ by mode and never use the forbidden combo."""

    def test_debug_returns_explicit_localhost_set(self) -> None:
        s = Settings(debug=True, db_password="changeme", _env_file=None)  # type: ignore[call-arg]
        origins = s.cors_allowed_origins
        assert all(
            o.startswith("http://localhost") or o.startswith("http://127.0.0.1") for o in origins
        )
        assert "*" not in origins
        assert len(origins) > 0

    def test_non_debug_uses_settings_allowlist(self) -> None:
        s = Settings(
            debug=False,
            db_password="s3cret",
            cors_origins=["https://app.example.com", "https://admin.example.com"],
            _env_file=None,  # type: ignore[call-arg]
        )
        assert s.cors_allowed_origins == [
            "https://app.example.com",
            "https://admin.example.com",
        ]

    def test_non_debug_empty_allowlist_denies_all(self) -> None:
        s = Settings(debug=False, db_password="s3cret", _env_file=None)  # type: ignore[call-arg]
        assert s.cors_allowed_origins == []

    def test_cors_origins_accepts_comma_separated_string(self) -> None:
        # Pydantic-settings reads env vars as strings; we want
        # "a,b" -> ["a", "b"] for the operator's convenience.
        s = Settings(
            debug=False,
            db_password="s3cret",
            cors_origins="https://a.example,https://b.example",  # type: ignore[arg-type]
            _env_file=None,  # type: ignore[call-arg]
        )
        assert s.cors_allowed_origins == ["https://a.example", "https://b.example"]
