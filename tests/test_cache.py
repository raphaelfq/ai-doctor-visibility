"""Tests for the cache module."""

import os

from ai_visibility.cache import cache_key, get_cached, set_cached


class TestCacheKey:
    def test_basic(self):
        assert cache_key("Dermatologia", "São Paulo") == "dermatologia:são paulo"

    def test_with_neighborhood(self):
        key = cache_key("Dermatologia", "São Paulo", "Moema")
        assert key == "dermatologia:são paulo:moema"

    def test_strips_whitespace(self):
        key = cache_key("  Dermatologia  ", " São Paulo ")
        assert key == "dermatologia:são paulo"

    def test_case_insensitive(self):
        assert cache_key("DERMATOLOGIA", "SÃO PAULO") == cache_key(
            "dermatologia", "são paulo"
        )


class TestCacheRoundTrip:
    def test_set_and_get(self):
        test_key = "_test_roundtrip"
        test_value = [{"id": "p1", "text": "test prompt"}]
        set_cached(test_key, test_value)
        result = get_cached(test_key)
        assert result == test_value

    def test_missing_key_returns_none(self):
        assert get_cached("_nonexistent_key_12345") is None
