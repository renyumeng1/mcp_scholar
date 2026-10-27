"""Preprint-to-published alignment and BibTeX enrichment helpers."""
import logging
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger(__name__)


async def align_preprint_to_published(paper: Dict[str, Any]) -> Dict[str, Any]:
    """Try to find the formal published version of a preprint (arXiv etc.)."""
    title = paper.get("title", "")
    arxiv_id = None
    if "arxiv" in (paper.get("url") or "").lower() or paper.get("paper_id", "").startswith("arxiv:"):
        arxiv_id = paper.get("paper_id")

    # Simple Crossref title search for formal version
    if title:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.crossref.org/works",
                    params={"query.bibliographic": title, "rows": 1},
                )
                if resp.status_code == 200:
                    items = resp.json().get("message", {}).get("items", [])
                    if items:
                        item = items[0]
                        formal = {
                            "formal_title": item.get("title", [""])[0],
                            "formal_doi": item.get("DOI"),
                            "formal_venue": (item.get("container-title") or [""])[0],
                            "formal_year": item.get("published-print", {}).get("date-parts", [[None]])[0][0],
                        }
                        paper["published_version"] = formal
                        paper["is_preprint"] = True
        except Exception as e:
            logger.debug("Crossref alignment failed: %s", e)
    return paper


def upgrade_bibtex_entry(bibtex: str, formal_info: Optional[Dict] = None) -> str:
    """Basic BibTeX upgrade placeholder: mark if formal version found."""
    if formal_info and formal_info.get("formal_doi"):
        return bibtex + f"\n% Upgraded: formal DOI {formal_info['formal_doi']}"
    return bibtex
