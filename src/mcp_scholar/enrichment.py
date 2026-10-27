"""Preprint alignment, BibTeX parsing, and OA PDF section extraction."""
import logging
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from mcp_scholar.scholar import doi_to_url, infer_arxiv_year, normalize_doi, titles_match

logger = logging.getLogger(__name__)

PUBLISHED_TYPES = {"journal-article", "proceedings-article", "book-chapter"}


def _crossref_year(item: Dict[str, Any]) -> Optional[int]:
    for key in ("published-print", "published-online", "published", "issued"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                continue
    return None


def is_preprint(paper: Dict[str, Any]) -> bool:
    """A record is a preprint when the requested id or its DOI/venue says so."""
    requested = (paper.get("requested_id") or "").lower()
    doi = (normalize_doi(paper.get("doi")) or "").lower()
    venue = (paper.get("venue") or "").lower()
    url = (paper.get("url") or "").lower()
    return (
        requested.startswith("arxiv:")
        or doi.startswith("10.48550/")
        or "arxiv" in venue
        or "arxiv.org" in url
    )


def choose_published_version(
    items: List[Dict[str, Any]],
    title: str,
    current_doi: Optional[str] = None,
    expected_year: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Pick a formal Crossref record only when the title and year actually agree."""
    current = (normalize_doi(current_doi) or "").lower()
    for item in items:
        item_title = (item.get("title") or [""])[0]
        if not titles_match(title, item_title):
            continue
        if (item.get("type") or "") not in PUBLISHED_TYPES:
            continue
        formal_doi = normalize_doi(item.get("DOI"))
        if not formal_doi or formal_doi.lower() == current or formal_doi.lower().startswith("10.48550/"):
            continue
        venue = (item.get("container-title") or [""])[0]
        if not venue:
            continue
        year = _crossref_year(item)
        if expected_year and year and abs(int(year) - int(expected_year)) > 2:
            continue
        return {
            "formal_title": item_title,
            "formal_doi": formal_doi,
            "formal_doi_url": doi_to_url(formal_doi),
            "formal_venue": venue,
            "formal_year": year,
            "formal_type": item.get("type"),
        }
    return None


async def align_preprint_to_published(paper: Dict[str, Any]) -> Dict[str, Any]:
    """Attach a published version only for preprints with a confident Crossref match."""
    aligned = dict(paper)
    aligned["is_preprint"] = is_preprint(aligned)
    title = aligned.get("title") or ""
    if not aligned["is_preprint"] or not title:
        return aligned
    expected_year = infer_arxiv_year(aligned.get("requested_id") or "")
    if expected_year is None:
        raw_year = aligned.get("year")
        if isinstance(raw_year, int):
            expected_year = raw_year
        elif isinstance(raw_year, str) and raw_year.isdigit():
            expected_year = int(raw_year)
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(
                "https://api.crossref.org/works",
                params={"query.bibliographic": title, "rows": 8},
            )
        if response.status_code != 200:
            return aligned
        items = response.json().get("message", {}).get("items", [])
        chosen = choose_published_version(
            items,
            title,
            aligned.get("doi"),
            expected_year,
        )
        if chosen:
            aligned["published_version"] = chosen
    except Exception as exc:
        logger.debug("Crossref alignment failed: %s", exc)
    return aligned


def _bib_field(entry: str, name: str) -> str:
    match = re.search(rf"(?im)^[ \t]*{name}\s*=\s*", entry)
    if not match:
        match = re.search(rf"(?i){name}\s*=\s*", entry)
    if not match:
        return ""
    rest = entry[match.end():].lstrip()
    if rest.startswith("{"):
        depth = 0
        for index, char in enumerate(rest):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return rest[1:index].strip()
        return ""
    if rest.startswith('"'):
        end = rest.find('"', 1)
        return rest[1:end].strip() if end > 1 else ""
    token = re.match(r"([^,\n]+)", rest)
    return token.group(1).strip() if token else ""


def parse_bibtex_entries(bibtex: str) -> List[Dict[str, Any]]:
    """Split a BibTeX string into title / DOI / year fields."""
    entries = []
    for chunk in re.split(r"(?=@[A-Za-z]+\s*\{)", bibtex or ""):
        chunk = chunk.strip()
        if not chunk.startswith("@"):
            continue
        entries.append(
            {
                "title": re.sub(r"\s+", " ", _bib_field(chunk, "title")),
                "doi": normalize_doi(_bib_field(chunk, "doi")),
                "year": _bib_field(chunk, "year").strip(),
                "raw": chunk,
            }
        )
    return entries


def upgrade_bibtex_entry(bibtex: str, formal_info: Optional[Dict] = None) -> str:
    """Annotate a BibTeX entry when a different formal DOI was found."""
    formal_doi = normalize_doi((formal_info or {}).get("formal_doi"))
    if not formal_doi:
        return bibtex
    return bibtex.rstrip() + f"\n% Upgraded: formal DOI {formal_doi}\n"


def select_markdown_sections(markdown: str, sections: str = "all") -> str:
    """Keep markdown sections whose headings match the requested names."""
    if not markdown:
        return ""
    if not sections or sections.strip().lower() == "all":
        return markdown
    wanted = [part.strip().lower() for part in sections.split(",") if part.strip()]
    if not wanted:
        return markdown
    chunks = re.split(r"\n(?=#+\s)", "\n" + markdown)
    kept = []
    for chunk in chunks:
        heading_match = re.match(r"\n?#+\s+(.+)", chunk.strip())
        heading = heading_match.group(1).strip().lower() if heading_match else ""
        if heading and any(name in heading for name in wanted):
            kept.append(chunk.strip())
    return "\n\n".join(kept)


def markdown_headings(markdown: str) -> List[str]:
    return [match.strip() for match in re.findall(r"^#+\s+(.+)$", markdown or "", flags=re.M)]


async def extract_pdf_sections(pdf_url: str, sections: str = "all") -> Dict[str, Any]:
    """Download an OA PDF and return the requested markdown sections."""
    try:
        import pymupdf4llm
    except ImportError:
        return {
            "status": "dependency_missing",
            "message": "Install pymupdf4llm for full PDF parsing",
        }
    if not pdf_url:
        return {"status": "no_pdf", "message": "No open-access PDF found"}
    temp_path = None
    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            response = await client.get(pdf_url)
        if response.status_code != 200 or not response.content.startswith(b"%PDF"):
            return {"status": "no_pdf", "message": "Open-access file is not a PDF"}
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as handle:
            temp_path = Path(handle.name)
        temp_path.write_bytes(response.content)
        markdown = pymupdf4llm.to_markdown(str(temp_path))
        selected = select_markdown_sections(markdown, sections)
        if sections.strip().lower() != "all" and not selected:
            return {
                "status": "sections_not_found",
                "message": "Requested sections were not found",
                "headings": markdown_headings(markdown)[:30],
            }
        return {
            "status": "success",
            "markdown": selected[:8000],
            "truncated": len(selected) > 8000,
            "sections": sections,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def find_zotero_collection_key(collections: List[Dict[str, Any]], name: str) -> Optional[str]:
    """Match a Zotero collection by its display name."""
    wanted = (name or "").strip().lower()
    if not wanted:
        return None
    for collection in collections or []:
        data = collection.get("data") or collection
        if (data.get("name") or "").strip().lower() == wanted:
            return data.get("key") or collection.get("key")
    return None