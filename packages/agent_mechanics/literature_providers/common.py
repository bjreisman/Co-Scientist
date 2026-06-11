"""Shared helpers for literature provider adapters."""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from packages.agent_contracts import (
    LiteratureProviderName,
    PaperCandidateContract,
    SearchProviderReceiptContract,
    SearchRequestContract,
)


_DEFAULT_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class ProviderSearchResult:
    """Normalized result for one provider attempt."""

    candidates: list[PaperCandidateContract]
    receipt: SearchProviderReceiptContract


class ProviderError(RuntimeError):
    """Base provider adapter error."""


class ProviderRateLimitError(ProviderError):
    """Provider returned a rate-limit response."""


class ProviderTimeoutError(ProviderError):
    """Provider request timed out."""


class ProviderInvalidResponseError(ProviderError):
    """Provider response could not be parsed into the expected shape."""


class ProviderMissingDependencyError(ProviderError):
    """Provider requires an unavailable local dependency."""


class ProviderMissingApiKeyError(ProviderError):
    """Provider requires an API key that is not configured."""


class ProviderDisabledError(ProviderError):
    """Provider is disabled by configuration."""


ProviderFetcher = Callable[[SearchRequestContract], list[PaperCandidateContract]]


def run_provider(
    provider: LiteratureProviderName,
    request: SearchRequestContract,
    fetcher: ProviderFetcher,
) -> ProviderSearchResult:
    """Run one provider adapter and convert failures into a receipt."""
    started_at = datetime.now(UTC)
    start_time = time.monotonic()
    candidates: list[PaperCandidateContract] = []
    status = "succeeded"
    error_type = ""
    error_message = ""
    rate_limit_observed = False
    try:
        candidates = fetcher(request)
    except ProviderDisabledError as exc:
        status = "skipped_disabled"
        error_type = exc.__class__.__name__
        error_message = str(exc)
    except ProviderMissingDependencyError as exc:
        status = "skipped_missing_dependency"
        error_type = exc.__class__.__name__
        error_message = str(exc)
    except ProviderMissingApiKeyError as exc:
        status = "skipped_missing_api_key"
        error_type = exc.__class__.__name__
        error_message = str(exc)
    except ProviderRateLimitError as exc:
        status = "failed_rate_limited"
        error_type = exc.__class__.__name__
        error_message = str(exc)
        rate_limit_observed = True
    except ProviderTimeoutError as exc:
        status = "failed_timeout"
        error_type = exc.__class__.__name__
        error_message = str(exc)
    except ProviderInvalidResponseError as exc:
        status = "failed_invalid_response"
        error_type = exc.__class__.__name__
        error_message = str(exc)
    except Exception as exc:
        status = "failed_provider_error"
        error_type = exc.__class__.__name__
        error_message = str(exc)

    finished_at = datetime.now(UTC)
    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    receipt = SearchProviderReceiptContract(
        provider=provider,
        status=status,
        request_hash=search_request_hash(request, provider),
        started_at=started_at,
        finished_at=finished_at,
        elapsed_ms=max(0, elapsed_ms),
        result_count=len(candidates),
        error_type=error_type,
        error_message=safe_error_message(error_message),
        retry_count=0,
        rate_limit_observed=rate_limit_observed,
    )
    return ProviderSearchResult(candidates=candidates, receipt=receipt)


def search_request_hash(request: SearchRequestContract, provider: str) -> str:
    """Return a stable hash for the provider-specific search request."""
    payload = request.model_dump(mode="json")
    payload["provider"] = provider
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_error_message(message: str, *, limit: int = 500) -> str:
    """Return a short error message without multiline noise."""
    return " ".join(message.split())[:limit]


def timeout_seconds() -> int:
    """Resolve the literature provider timeout from environment variables."""
    raw = os.environ.get("CO_SCIENTIST_LITERATURE_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS


def fetch_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    """Fetch one JSON endpoint with stdlib urllib."""
    text = fetch_text(url, headers=headers)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderInvalidResponseError("Provider returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise ProviderInvalidResponseError("Provider JSON response was not an object.")
    return payload


def fetch_text(url: str, headers: dict[str, str] | None = None) -> str:
    """Fetch one text endpoint with stdlib urllib."""
    require_http_url(url)
    request = urllib.request.Request(url, headers=headers or {})  # noqa: S310 - URL scheme is validated first.
    try:
        with urllib.request.urlopen(  # noqa: S310 - URL scheme is validated before opening the request.
            request,
            timeout=timeout_seconds(),
        ) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise ProviderRateLimitError("Provider returned HTTP 429 rate limit.") from exc
        raise ProviderError(f"Provider returned HTTP {exc.code}.") from exc
    except TimeoutError as exc:
        raise ProviderTimeoutError("Provider request timed out.") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError):
            raise ProviderTimeoutError("Provider request timed out.") from exc
        raise ProviderError(f"Provider network request failed: {exc}") from exc


def build_url(base_url: str, params: dict[str, Any]) -> str:
    """Build a URL with query parameters."""
    clean_params = {key: value for key, value in params.items() if value is not None and value != "" and value != []}
    return f"{base_url}?{urllib.parse.urlencode(clean_params, doseq=True)}"


def require_http_url(url: str) -> None:
    """Reject non-HTTP provider URLs before opening network requests."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ProviderError(f"Provider URL must use http or https, found `{parsed.scheme or 'empty'}`.")


def clean_text(value: Any) -> str:
    """Normalize provider text fields into compact single-line strings."""
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").split()).strip()


def first_text(value: Any) -> str:
    """Return the first text item from provider fields that may be scalar or list."""
    if isinstance(value, list):
        for item in value:
            text = clean_text(item)
            if text:
                return text
        return ""
    return clean_text(value)


def coerce_int(value: Any) -> int | None:
    """Coerce provider numeric fields to int when possible."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def make_paper_id(*, provider: str, doi: str | None = None, arxiv_id: str | None = None, title: str = "") -> str:
    """Create a stable provider-independent candidate identifier."""
    if doi:
        return f"doi:{doi.lower().removeprefix('https://doi.org/')}"
    if arxiv_id:
        return f"arxiv:{arxiv_id.lower()}"
    normalized_title = clean_text(title).lower()
    digest = hashlib.sha1(normalized_title.encode(), usedforsecurity=False).hexdigest()[:16]
    return f"title:{digest}" if normalized_title else f"{provider}:unknown"


def normalize_doi(value: Any) -> str | None:
    """Normalize a DOI-like provider field."""
    text = clean_text(value).lower()
    if not text:
        return None
    return text.removeprefix("https://doi.org/").removeprefix("http://doi.org/")


def year_from_date_parts(value: Any) -> int | None:
    """Extract a year from Crossref-style date-parts arrays."""
    if not isinstance(value, dict):
        return None
    date_parts = value.get("date-parts")
    if not isinstance(date_parts, list) or not date_parts:
        return None
    first = date_parts[0]
    if not isinstance(first, list) or not first:
        return None
    return coerce_int(first[0])
