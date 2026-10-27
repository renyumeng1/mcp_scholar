import pytest
from mcp_scholar.server import is_valid_paper_id, sanitize_for_log

def test_valid_doi():
    assert is_valid_paper_id("10.1000/j.jss.2021.10.002") is True

def test_valid_openalex():
    assert is_valid_paper_id("W123456789") is True
    assert is_valid_paper_id("123456789") is True

def test_valid_arxiv():
    assert is_valid_paper_id("arxiv:2301.12345") is True
    assert is_valid_paper_id("arXiv:2301.12345") is True

def test_invalid_ids():
    assert is_valid_paper_id("<b>tofu-poc</b>{{7*7}}") is False
    assert is_valid_paper_id("") is False
    assert is_valid_paper_id("invalid") is False
    assert is_valid_paper_id("a" * 201) is False

def test_sanitize_for_log():
    assert sanitize_for_log("normal") == "normal"
    assert sanitize_for_log("with\nnewline") == "withnewline"
    assert len(sanitize_for_log("a" * 150)) == 100
