"""OpenAlex literature provider adapter."""

from __future__ import annotations

import os
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
)


_BASE_URL = "https://api.openalex.org/works"


def search(request: SearchRequestContract) -> ProviderSearchResult:
    """Search OpenAlex works and return normalized candidates plus a receipt."""
    return run_provider("openalex", request, _search)


def _search(request: SearchRequestContract) -> list[PaperCandidateContract]:
    filters: list[str] = []
    if request.filters.year_min and request.filters.year_max:
        filters.append(f"publication_year:{request.filters.year_min}-{request.filters.year_max}")
    elif request.filters.year_min:
        filters.append(f"from_publication_date:{request.filters.year_min}-01-01")
    elif request.filters.year_max:
        filters.append(f"to_publication_date:{request.filters.year_max}-12-31")
    if request.filters.open_access_only:
        filters.append("is_oa:true")
    if request.filters.min_citations is not None:
        filters.append(f"cited_by_count:>{request.filters.min_citations}")

    params: dict[str, Any] = {
        "search": request.query,
        "per-page": min(request.filters.max_results, 200),
        "sort": "relevance_score:desc",
    }
    if filters:
        params["filter"] = ",".join(filters)
    email = os.environ.get("OPENALEX_EMAIL", "").strip()
    if email:
        params["mailto"] = email
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    if api_key:
        params["api_key"] = api_key

    payload = fetch_json(build_url(_BASE_URL, params))
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    return [_parse_work(work) for work in results if isinstance(work, dict)]


def _parse_work(work: dict[str, Any]) -> PaperCandidateContract:
    doi = normalize_doi(work.get("doi"))
    title = clean_text(work.get("display_name") or work.get("title"))
    openalex_id = clean_text(work.get("id")).split("/")[-1]
    authors = []
    for authorship in work.get("authorships") or []:
        if isinstance(authorship, dict):
            author = authorship.get("author") or {}
            if isinstance(author, dict):
                name = clean_text(author.get("display_name"))
                if name:
                    authors.append(name)
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") if isinstance(primary_location, dict) else {}
    venue = clean_text(source.get("display_name") if isinstance(source, dict) else "")
    open_access = work.get("open_access") or {}
    open_access_url = clean_text(open_access.get("oa_url") if isinstance(open_access, dict) else "")
    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
    ids = work.get("ids") if isinstance(work.get("ids"), dict) else {}
    arxiv_id = _extract_arxiv_id(ids)
    return PaperCandidateContract(
        paper_id=make_paper_id(provider="openalex", doi=doi, arxiv_id=arxiv_id, title=title),
        title=title,
        authors=authors,
        year=coerce_int(work.get("publication_year")),
        venue=venue,
        doi=doi,
        arxiv_id=arxiv_id,
        url=first_text(work.get("id")),
        open_access_url=open_access_url,
        abstract=abstract,
        provider_sources=["openalex"],
        raw_provider_ids={"openalex": openalex_id} if openalex_id else {},
        citation_count=coerce_int(work.get("cited_by_count")),
        relevance_score=float(work.get("relevance_score") or 0.0),
    )


def _reconstruct_abstract(inverted_index: Any) -> str:
    if not isinstance(inverted_index, dict):
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if isinstance(positions, list):
            for position in positions:
                index = coerce_int(position)
                if index is not None:
                    words.append((index, str(word)))
    return " ".join(word for _, word in sorted(words, key=lambda item: item[0]))


def _extract_arxiv_id(ids: dict[str, Any]) -> str | None:
    for key in ("arxiv", "arxiv_id"):
        value = clean_text(ids.get(key))
        if value:
            return value.rsplit("/", 1)[-1]
    return None
