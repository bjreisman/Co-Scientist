from __future__ import annotations

from packages.agent_contracts import SearchRequestContract
from packages.agent_mechanics.literature_providers import arxiv, crossref, europe_pmc, openalex, semantic_scholar
from packages.agent_mechanics.literature_providers.common import ProviderRateLimitError


def _request() -> SearchRequestContract:
    return SearchRequestContract(
        query_id="q-001",
        query="ammonia synthesis catalyst",
        filters={"max_results": 3},
    )


def test_openalex_provider_parses_normalized_candidate(monkeypatch) -> None:
    def fake_fetch_json(url: str, headers=None):
        assert "api.openalex.org/works" in url
        return {
            "results": [
                {
                    "id": "https://openalex.org/W123",
                    "doi": "https://doi.org/10.1000/example",
                    "display_name": "Catalyst active sites",
                    "publication_year": 2024,
                    "authorships": [{"author": {"display_name": "A. Researcher"}}],
                    "primary_location": {"source": {"display_name": "Nature Catalysis"}},
                    "open_access": {"oa_url": "https://example.org/paper.pdf"},
                    "abstract_inverted_index": {"A": [0], "test": [1]},
                    "cited_by_count": 12,
                    "relevance_score": 9.5,
                }
            ]
        }

    monkeypatch.setattr(openalex, "fetch_json", fake_fetch_json)

    result = openalex.search(_request())

    assert result.receipt.status == "succeeded"
    assert result.receipt.result_count == 1
    assert result.candidates[0].paper_id == "doi:10.1000/example"
    assert result.candidates[0].abstract == "A test"
    assert result.candidates[0].provider_sources == ["openalex"]


def test_crossref_provider_parses_metadata_and_strips_abstract_tags(monkeypatch) -> None:
    def fake_fetch_json(url: str, headers=None):
        assert "api.crossref.org/works" in url
        return {
            "message": {
                "items": [
                    {
                        "DOI": "10.1000/crossref",
                        "title": ["Crossref catalyst paper"],
                        "author": [{"given": "Ada", "family": "Lovelace"}],
                        "issued": {"date-parts": [[2023, 1, 1]]},
                        "container-title": ["Journal of Catalysis"],
                        "abstract": "<jats:p>Structured abstract.</jats:p>",
                        "URL": "https://doi.org/10.1000/crossref",
                    }
                ]
            }
        }

    monkeypatch.setattr(crossref, "fetch_json", fake_fetch_json)

    result = crossref.search(_request())

    assert result.receipt.status == "succeeded"
    assert result.candidates[0].authors == ["Ada Lovelace"]
    assert result.candidates[0].abstract == "Structured abstract."
    assert result.candidates[0].venue == "Journal of Catalysis"


def test_europe_pmc_provider_parses_biomedical_metadata(monkeypatch) -> None:
    def fake_fetch_json(url: str, headers=None):
        assert "europepmc" in url
        return {
            "resultList": {
                "result": [
                    {
                        "title": "PMC catalyst paper",
                        "authorString": "First A, Second B",
                        "pubYear": "2022",
                        "journalTitle": "Chemistry Journal",
                        "doi": "10.1000/pmc",
                        "pmid": "12345",
                        "pmcid": "PMC12345",
                        "abstractText": "PMC abstract.",
                        "fullTextUrlList": {"fullTextUrl": [{"url": "https://example.org/full"}]},
                        "citedByCount": "7",
                    }
                ]
            }
        }

    monkeypatch.setattr(europe_pmc, "fetch_json", fake_fetch_json)

    result = europe_pmc.search(_request())

    assert result.receipt.status == "succeeded"
    assert result.candidates[0].pmid == "12345"
    assert result.candidates[0].pmcid == "PMC12345"
    assert result.candidates[0].open_access_url == "https://example.org/full"


def test_semantic_scholar_provider_records_rate_limit_receipt(monkeypatch) -> None:
    def fake_fetch_json(url: str, headers=None):
        raise ProviderRateLimitError("Provider returned HTTP 429 rate limit.")

    monkeypatch.setattr(semantic_scholar, "fetch_json", fake_fetch_json)

    result = semantic_scholar.search(_request())

    assert result.receipt.status == "failed_rate_limited"
    assert result.receipt.rate_limit_observed is True
    assert result.candidates == []


def test_arxiv_provider_parses_atom_results(monkeypatch) -> None:
    atom = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>https://arxiv.org/abs/2401.12345v1</id>
    <title>arXiv catalyst paper</title>
    <summary>arXiv abstract.</summary>
    <published>2024-01-01T00:00:00Z</published>
    <author><name>Example Author</name></author>
  </entry>
</feed>
"""

    def fake_fetch_text(url: str, headers=None):
        assert "export.arxiv.org/api/query" in url
        return atom

    monkeypatch.setattr(arxiv, "fetch_text", fake_fetch_text)

    result = arxiv.search(_request())

    assert result.receipt.status == "succeeded"
    assert result.candidates[0].arxiv_id == "2401.12345"
    assert result.candidates[0].url == "https://arxiv.org/abs/2401.12345"
    assert result.candidates[0].open_access_url == "https://arxiv.org/pdf/2401.12345.pdf"
