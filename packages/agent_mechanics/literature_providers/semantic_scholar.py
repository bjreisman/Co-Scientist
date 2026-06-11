"""Semantic Scholar literature provider adapter."""

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


_BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = (
    "paperId,title,abstract,year,venue,publicationVenue,publicationDate,url,"
    "openAccessPdf,authors,externalIds,citationCount,fieldsOfStudy,tldr"
)


def search(request: SearchRequestContract) -> ProviderSearchResult:
    """Search Semantic Scholar and return normalized candidates plus a receipt."""
    return run_provider("semantic_scholar", request, _search)


def _search(request: SearchRequestContract) -> list[PaperCandidateContract]:
    params: dict[str, Any] = {
        "query": request.query,
        "limit": min(request.filters.max_results, 100),
        "fields": _FIELDS,
    }
    if request.filters.year_min and request.filters.year_max:
        params["year"] = f"{request.filters.year_min}-{request.filters.year_max}"
    elif request.filters.year_min:
        params["year"] = f"{request.filters.year_min}-"
    elif request.filters.year_max:
        params["year"] = f"-{request.filters.year_max}"
    if request.filters.min_citations is not None:
        params["minCitationCount"] = request.filters.min_citations
    if request.filters.open_access_only:
        params["openAccessPdf"] = ""

    headers = {"Accept": "application/json", "User-Agent": "co-scientist-literature/1.0"}
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key
    payload = fetch_json(build_url(_BASE_URL, params), headers=headers)
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [_parse_paper(item) for item in data if isinstance(item, dict)]


def _parse_paper(paper: dict[str, Any]) -> PaperCandidateContract:
    external_ids = paper.get("externalIds") if isinstance(paper.get("externalIds"), dict) else {}
    doi = normalize_doi(external_ids.get("DOI"))
    arxiv_id = clean_text(external_ids.get("ArXiv")) or None
    title = clean_text(paper.get("title"))
    paper_id = clean_text(paper.get("paperId"))
    publication_venue = paper.get("publicationVenue") if isinstance(paper.get("publicationVenue"), dict) else {}
    venue = clean_text(publication_venue.get("name") if publication_venue else "") or clean_text(paper.get("venue"))
    open_access_pdf = paper.get("openAccessPdf") if isinstance(paper.get("openAccessPdf"), dict) else {}
    authors = []
    for author in paper.get("authors") or []:
        if isinstance(author, dict):
            name = clean_text(author.get("name"))
            if name:
                authors.append(name)
    raw_ids = {"semantic_scholar": paper_id} if paper_id else {}
    if doi:
        raw_ids["doi"] = doi
    if arxiv_id:
        raw_ids["arxiv"] = arxiv_id
    return PaperCandidateContract(
        paper_id=make_paper_id(provider="semantic_scholar", doi=doi, arxiv_id=arxiv_id, title=title),
        title=title,
        authors=authors,
        year=coerce_int(paper.get("year")),
        venue=venue,
        doi=doi,
        arxiv_id=arxiv_id,
        url=first_text(paper.get("url")),
        open_access_url=clean_text(open_access_pdf.get("url") if open_access_pdf else ""),
        abstract=clean_text(paper.get("abstract")),
        provider_sources=["semantic_scholar"],
        raw_provider_ids=raw_ids,
        citation_count=coerce_int(paper.get("citationCount")),
    )
