"""Europe PMC literature provider adapter."""

from __future__ import annotations

from typing import Any

from packages.agent_contracts import PaperCandidateContract, SearchRequestContract

from .common import (
    ProviderSearchResult,
    build_url,
    clean_text,
    coerce_int,
    fetch_json,
    make_paper_id,
    normalize_doi,
    run_provider,
)


_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def search(request: SearchRequestContract) -> ProviderSearchResult:
    """Search Europe PMC and return normalized candidates plus a receipt."""
    return run_provider("europe_pmc", request, _search)


def _search(request: SearchRequestContract) -> list[PaperCandidateContract]:
    query = request.query
    if request.filters.year_min or request.filters.year_max:
        year_min = request.filters.year_min or 1800
        year_max = request.filters.year_max or 3000
        query = f"({query}) AND FIRST_PDATE:[{year_min}-01-01 TO {year_max}-12-31]"
    params: dict[str, Any] = {
        "query": query,
        "format": "json",
        "pageSize": min(request.filters.max_results, 1000),
        "resultType": "core",
    }
    payload = fetch_json(build_url(_BASE_URL, params))
    result_list = payload.get("resultList") if isinstance(payload.get("resultList"), dict) else {}
    results = result_list.get("result") if isinstance(result_list, dict) else []
    if not isinstance(results, list):
        return []
    return [_parse_result(item) for item in results if isinstance(item, dict)]


def _parse_result(result: dict[str, Any]) -> PaperCandidateContract:
    doi = normalize_doi(result.get("doi"))
    title = clean_text(result.get("title"))
    pmid = clean_text(result.get("pmid")) or None
    pmcid = clean_text(result.get("pmcid")) or None
    authors = _parse_authors(result.get("authorString"))
    year = coerce_int(result.get("pubYear"))
    journal = clean_text(result.get("journalTitle"))
    url = _build_url(result, doi=doi)
    raw_ids = {}
    if pmid:
        raw_ids["pmid"] = pmid
    if pmcid:
        raw_ids["pmcid"] = pmcid
    return PaperCandidateContract(
        paper_id=make_paper_id(provider="europe_pmc", doi=doi, title=title),
        title=title,
        authors=authors,
        year=year,
        venue=journal,
        doi=doi,
        pmid=pmid,
        pmcid=pmcid,
        url=url,
        open_access_url=_open_access_url(result),
        abstract=clean_text(result.get("abstractText")),
        provider_sources=["europe_pmc"],
        raw_provider_ids=raw_ids,
        citation_count=coerce_int(result.get("citedByCount")),
    )


def _parse_authors(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _build_url(result: dict[str, Any], *, doi: str | None) -> str:
    if doi:
        return f"https://doi.org/{doi}"
    pmcid = clean_text(result.get("pmcid"))
    if pmcid:
        return f"https://europepmc.org/article/PMC/{pmcid.removeprefix('PMC')}"
    pmid = clean_text(result.get("pmid"))
    if pmid:
        return f"https://europepmc.org/article/MED/{pmid}"
    return ""


def _open_access_url(result: dict[str, Any]) -> str:
    full_text_list = result.get("fullTextUrlList")
    if not isinstance(full_text_list, dict):
        return ""
    urls = full_text_list.get("fullTextUrl")
    if not isinstance(urls, list):
        return ""
    for item in urls:
        if isinstance(item, dict):
            url = clean_text(item.get("url"))
            if url:
                return url
    return ""
