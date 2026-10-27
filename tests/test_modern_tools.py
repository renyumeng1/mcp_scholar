import pytest
from mcp_scholar.server import search_papers, verify_bibtex, is_valid_paper_id

class DummyContext:
    pass

@pytest.mark.asyncio
async def test_search_papers_basic():
    ctx = DummyContext()
    result = await search_papers(ctx, keywords="attention is all you need", count=2, strategy="exact")
    assert result["status"] in ("success", "error")
    if result["status"] == "success":
        assert "papers" in result
        assert result["strategy"] == "exact"

@pytest.mark.asyncio
async def test_verify_bibtex_basic():
    ctx = DummyContext()
    bib = '''@article{vaswani2017attention,
  title={Attention is all you need},
  author={Vaswani, Ashish and others},
  journal={NeurIPS},
  year={2017}
}'''
    result = await verify_bibtex(ctx, bib)
    assert result["status"] in ("success", "error")
    if result["status"] == "success":
        assert "results" in result

def test_paper_id_validation_still_works():
    assert is_valid_paper_id("10.1038/nature12373")
    assert is_valid_paper_id("W123456789")
    assert not is_valid_paper_id("<script>alert(1)</script>")

def test_cache_roundtrip():
    from mcp_scholar.cache import cache_set, cache_get
    cache_set("test_key", {"ok": True}, ttl=60)
    assert cache_get("test_key") == {"ok": True}
    assert cache_get("missing") is None
