"""arXiv literature provider adapter."""

from __future__ import annotations

from typing import Any

from defusedxml import ElementTree as ET

from packages.agent_contracts import PaperCandidateContract, SearchRequestContract

from .common import (
    ProviderInvalidResponseError,
    ProviderSearchResult,
    build_url,
    clean_text,
    fetch_text,
    make_paper_id,
    run_provider,
)


_BASE_URL = "https://export.arxiv.org/api/query"
_ATOM_NS = "http://www.w3.org/2005/Atom"


def search(request: SearchRequestContract) -> ProviderSearchResult:
    """Search arXiv and return normalized candidates plus a receipt."""
    return run_provider("arxiv", request, _search)


def _search(request: SearchRequestContract) -> list[PaperCandidateContract]:
    params: dict[str, Any] = {
        "search_query": request.query,
        "start": 0,
        "max_results": min(request.filters.max_results, 100),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    text = fetch_text(build_url(_BASE_URL, params), headers={"User-Agent": "co-scientist-literature/1.0"})
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ProviderInvalidResponseError("arXiv returned invalid Atom XML.") from exc
    entries = root.findall(f"{{{_ATOM_NS}}}entry")
    candidates = [_parse_entry(entry) for entry in entries]
    return _filter_by_year(candidates, request)


def _parse_entry(entry: ET.Element) -> PaperCandidateContract:
    raw_id = clean_text(entry.findtext(f"{{{_ATOM_NS}}}id", ""))
    arxiv_id = _normalize_arxiv_id(raw_id)
    title = clean_text(entry.findtext(f"{{{_ATOM_NS}}}title", ""))
    abstract = clean_text(entry.findtext(f"{{{_ATOM_NS}}}summary", ""))
    published = clean_text(entry.findtext(f"{{{_ATOM_NS}}}published", ""))
    year = _year_from_date(published)
    authors = [
        clean_text(author.findtext(f"{{{_ATOM_NS}}}name", "")) for author in entry.findall(f"{{{_ATOM_NS}}}author")
    ]
    authors = [author for author in authors if author]
    return PaperCandidateContract(
        paper_id=make_paper_id(provider="arxiv", arxiv_id=arxiv_id, title=title),
        title=title,
        authors=authors,
        year=year,
        venue="arXiv",
        arxiv_id=arxiv_id,
        url=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else raw_id,
        open_access_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else "",
        abstract=abstract,
        provider_sources=["arxiv"],
        raw_provider_ids={"arxiv": arxiv_id} if arxiv_id else {},
    )


def _normalize_arxiv_id(value: str) -> str | None:
    if not value:
        return None
    if "/abs/" in value:
        value = value.rsplit("/abs/", 1)[-1]
    if value.startswith("id:"):
        value = value[3:]
    if "v" in value.split(".")[-1]:
        value = value.rsplit("v", 1)[0]
    return value


def _year_from_date(value: str) -> int | None:
    if len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


def _filter_by_year(
    candidates: list[PaperCandidateContract],
    request: SearchRequestContract,
) -> list[PaperCandidateContract]:
    year_min = request.filters.year_min
    year_max = request.filters.year_max
    if year_min is None and year_max is None:
        return candidates
    filtered = []
    for candidate in candidates:
        if candidate.year is None:
            filtered.append(candidate)
            continue
        if year_min is not None and candidate.year < year_min:
            continue
        if year_max is not None and candidate.year > year_max:
            continue
        filtered.append(candidate)
    return filtered
