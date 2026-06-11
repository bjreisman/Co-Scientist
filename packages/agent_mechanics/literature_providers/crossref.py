"""Crossref literature provider adapter."""

from __future__ import annotations

import re
from typing import Any

from packages.agent_contracts import PaperCandidateContract, SearchRequestContract

from .common import (
    ProviderSearchResult,
    build_url,
    clean_text,
    coerce_int,
    fetch_json,
    first_text,
    make_paper_id,
    normalize_doi,
    run_provider,
    year_from_date_parts,
)


_BASE_URL = "https://api.crossref.org/works"
_TAG_RE = re.compile(r"<[^>]+>")


def search(request: SearchRequestContract) -> ProviderSearchResult:
    """Search Crossref works and return normalized candidates plus a receipt."""
    return run_provider("crossref", request, _search)


def _search(request: SearchRequestContract) -> list[PaperCandidateContract]:
    filters: list[str] = []
    if request.filters.year_min:
        filters.append(f"from-pub-date:{request.filters.year_min}-01-01")
    if request.filters.year_max:
        filters.append(f"until-pub-date:{request.filters.year_max}-12-31")
    params: dict[str, Any] = {
        "query": request.query,
        "rows": min(request.filters.max_results, 100),
    }
    if filters:
        params["filter"] = ",".join(filters)
    payload = fetch_json(build_url(_BASE_URL, params))
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    items = message.get("items") if isinstance(message, dict) else []
    if not isinstance(items, list):
        return []
    return [_parse_work(item) for item in items if isinstance(item, dict)]


def _parse_work(work: dict[str, Any]) -> PaperCandidateContract:
    doi = normalize_doi(work.get("DOI"))
    title = first_text(work.get("title"))
    authors = _parse_authors(work.get("author"))
    year = (
        year_from_date_parts(work.get("published-print"))
        or year_from_date_parts(work.get("published-online"))
        or year_from_date_parts(work.get("issued"))
    )
    venue = first_text(work.get("container-title"))
    abstract = _strip_tags(first_text(work.get("abstract")))
    url = first_text(work.get("URL"))
    citation_count = coerce_int(work.get("is-referenced-by-count"))
    return PaperCandidateContract(
        paper_id=make_paper_id(provider="crossref", doi=doi, title=title),
        title=title,
        authors=authors,
        year=year,
        venue=venue,
        doi=doi,
        url=url,
        abstract=abstract,
        provider_sources=["crossref"],
        raw_provider_ids={"crossref": doi} if doi else {},
        citation_count=citation_count,
    )


def _parse_authors(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    authors: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        given = clean_text(item.get("given"))
        family = clean_text(item.get("family"))
        name = clean_text(f"{given} {family}") if given or family else clean_text(item.get("name"))
        if name:
            authors.append(name)
    return authors


def _strip_tags(value: str) -> str:
    return clean_text(_TAG_RE.sub(" ", value))
