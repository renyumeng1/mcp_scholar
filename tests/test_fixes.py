from mcp_scholar.enrichment import (
    choose_published_version,
    find_zotero_collection_key,
    parse_bibtex_entries,
    select_markdown_sections,
)
from mcp_scholar.scholar import (
    doi_to_url,
    infer_arxiv_year,
    normalize_doi,
    openalex_search_parts,
    titles_match,
    venue_and_tier,
    work_lookup_urls,
)
from mcp_scholar.venue_tiers import get_venue_tier


def test_doi_is_not_doubled():
    assert normalize_doi("https://doi.org/10.48550/arxiv.1706.03762") == "10.48550/arxiv.1706.03762"
    assert normalize_doi("https://doi.org/https://doi.org/10.1000/abc") == "10.1000/abc"
    assert doi_to_url("https://doi.org/10.1000/abc") == "https://doi.org/10.1000/abc"
    assert "doi.org/https://doi.org" not in doi_to_url("https://doi.org/10.1000/abc")


def test_year_filter_stays_with_the_title():
    parts = openalex_search_parts(
        "Attention is all you need",
        count=3,
        fuzzy_search=False,
        year_start=2017,
        year_end=2017,
    )
    assert parts["filter"].count("filter=") == 0
    assert "title.search:" in parts["filter"]
    assert "publication_year:2017-2017" in parts["filter"]
    assert parts["filter"].count(",") == 1


def test_arxiv_lookup_uses_doi_form():
    urls = work_lookup_urls("arXiv:1706.03762")
    assert urls == ["https://api.openalex.org/works/doi:10.48550/arxiv.1706.03762"]
    assert infer_arxiv_year("10.48550/arxiv.1706.03762") == 2017


def test_venue_comes_from_current_openalex_location():
    venue, tier = venue_and_tier(
        {
            "host_venue": None,
            "primary_location": {
                "source": {"display_name": "NeurIPS"},
                "raw_source_name": "Advances in Neural Information Processing Systems",
            },
        }
    )
    assert venue == "NeurIPS"
    assert tier == "CCF-A"
    assert get_venue_tier("ICASSP 2021") == "CCF-B"
    assert get_venue_tier("NAACL-HLT") == "CCF-A"


def test_title_match_rejects_longer_different_paper():
    assert titles_match("Attention is all you need", "Attention Is All You Need")
    assert not titles_match(
        "Attention is all you need",
        "Attention is all you need in speech separation",
    )


def test_bibtex_fields_and_published_choice():
    bib = """@article{vaswani2017attention,
  title={Attention is all you need},
  year={2017},
  doi={10.48550/arXiv.1706.03762}
}"""
    entries = parse_bibtex_entries(bib)
    assert entries[0]["title"] == "Attention is all you need"
    assert entries[0]["doi"] == "10.48550/arXiv.1706.03762"
    items = [
        {
            "title": ["Some other paper"],
            "DOI": "10.1000/unrelated",
            "type": "journal-article",
            "container-title": ["Nature"],
            "issued": {"date-parts": [[2017]]},
        },
        {
            "title": ["Attention Is All You Need"],
            "DOI": "10.65215/2q58a426",
            "type": "journal-article",
            "container-title": ["Preprint Mirror"],
            "issued": {"date-parts": [[2025]]},
        },
        {
            "title": ["Attention Is All You Need"],
            "DOI": "10.5555/3295222.3295349",
            "type": "proceedings-article",
            "container-title": ["NeurIPS"],
            "issued": {"date-parts": [[2017]]},
        },
    ]
    chosen = choose_published_version(
        items,
        "Attention is all you need",
        "10.48550/arxiv.1706.03762",
        expected_year=2017,
    )
    assert chosen["formal_doi"] == "10.5555/3295222.3295349"


def test_pdf_section_filter_and_zotero_collection():
    markdown = "# Abstract\nHello\n# Introduction\nWorld\n"
    assert select_markdown_sections(markdown, "abstract") == "# Abstract\nHello"
    assert "World" not in select_markdown_sections(markdown, "abstract")
    assert select_markdown_sections(markdown, "all") == markdown
    collections = [{"key": "ABC12345", "data": {"name": "Inbox", "key": "ABC12345"}}]
    assert find_zotero_collection_key(collections, "inbox") == "ABC12345"
    assert find_zotero_collection_key(collections, "Missing") is None
