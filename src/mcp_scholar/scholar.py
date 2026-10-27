"""OpenAlex search, paper lookup, and author profiles."""

import html
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

from mcp_scholar.cache import cache_get, cache_set
from mcp_scholar.venue_tiers import get_venue_tier, match_venue

logger = logging.getLogger(__name__)

OPENALEX_API = "https://api.openalex.org"
DEFAULT_EMAIL = "your-email@example.com"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"


class AuthorNotFound(LookupError):
    """Raised when a scholar profile cannot be resolved."""


def get_env_file() -> Optional[str]:
    """Locate the project .env without depending on the process cwd."""
    if os.path.exists(".env"):
        return ".env"
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        return str(env_path)
    return None


env_file = get_env_file()
if env_file:
    load_dotenv(env_file)
else:
    logger.warning("\u8b66\u544a: \u672a\u627e\u5230.env\u6587\u4ef6,\u4f7f\u7528\u9ed8\u8ba4\u914d\u7f6e")

EMAIL = os.environ.get("OPENALEX_EMAIL", DEFAULT_EMAIL)


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    """Return a bare DOI, without a resolver prefix."""
    if not doi or not isinstance(doi, str):
        return None
    value = doi.strip()
    previous = None
    while previous != value:
        previous = value
        value = re.sub(
            r"^(https?://(dx\.)?doi\.org/|doi:)",
            "",
            value,
            count=1,
            flags=re.IGNORECASE,
        ).strip()
    return value.strip(" .") or None


def doi_to_url(doi: Optional[str]) -> str:
    bare = normalize_doi(doi)
    return f"https://doi.org/{bare}" if bare else ""


def normalize_title(title: str) -> str:
    text = (title or "").lower().replace("&amp;", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def titles_match(left: str, right: str) -> bool:
    """True when two titles are the same work, not merely sharing a few words."""
    a, b = normalize_title(left), normalize_title(right)
    if not a or not b:
        return False
    if a == b:
        return True
    ta, tb = set(a.split()), set(b.split())
    if min(len(ta), len(tb)) < 3:
        return False
    overlap = len(ta & tb) / max(len(ta), len(tb))
    return overlap >= 0.8


def infer_arxiv_year(paper_id: str) -> Optional[int]:
    match = re.search(
        r"(?:arxiv:|arxiv\.)(\d{2})(\d{2})",
        paper_id or "",
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    year = int(match.group(1))
    return 2000 + year if year < 90 else 1900 + year


def year_filter(year_start: Optional[int], year_end: Optional[int]) -> str:
    if year_start and year_end:
        return f"publication_year:{int(year_start)}-{int(year_end)}"
    if year_start:
        return f"publication_year:>{int(year_start) - 1}"
    if year_end:
        return f"publication_year:<{int(year_end) + 1}"
    return ""


def openalex_search_parts(
    query: str,
    count: int = 5,
    fuzzy_search: bool = False,
    sort_by: str = "relevance",
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
) -> Dict[str, str]:
    """Query parts for an OpenAlex search. Title and year share one filter."""
    parts: Dict[str, str] = {"per_page": str(max(int(count), 1) * 2)}
    filters: List[str] = []
    if fuzzy_search:
        parts["search"] = query
    else:
        filters.append("title.search:" + quote((query or "").replace(",", " "), safe=""))
    ranged = year_filter(year_start, year_end)
    if ranged:
        filters.append(ranged)
    if filters:
        parts["filter"] = ",".join(filters)
    if sort_by == "citations":
        parts["sort"] = "cited_by_count:desc"
    elif sort_by == "date":
        parts["sort"] = "publication_date:desc"
    elif sort_by == "title":
        parts["sort"] = "display_name:asc"
    return parts


def build_openalex_search_url(
    query: str,
    count: int = 5,
    fuzzy_search: bool = False,
    sort_by: str = "relevance",
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
) -> str:
    parts = openalex_search_parts(query, count, fuzzy_search, sort_by, year_start, year_end)
    encoded = []
    for key in ("search", "filter", "sort", "per_page"):
        if key not in parts:
            continue
        value = parts[key] if key != "search" else quote(parts[key])
        encoded.append(f"{key}={value}")
    if EMAIL:
        encoded.append("mailto=" + quote(EMAIL))
    return f"{OPENALEX_API}/works?" + "&".join(encoded)


def work_lookup_urls(paper_id: str) -> List[str]:
    """Candidate OpenAlex work URLs for a DOI, OpenAlex id, or arXiv id."""
    paper_id = (paper_id or "").strip()
    if paper_id.lower().startswith("arxiv:"):
        arxiv_id = paper_id.split(":", 1)[1].strip().lower()
        return [f"{OPENALEX_API}/works/doi:10.48550/arxiv.{arxiv_id}"]
    bare_doi = normalize_doi(paper_id)
    if bare_doi and bare_doi.startswith("10."):
        return [f"{OPENALEX_API}/works/doi:{quote(bare_doi, safe='/')}"]
    short = paper_id.rstrip("/").rsplit("/", 1)[-1]
    if re.fullmatch(r"W\d+", short):
        return [f"{OPENALEX_API}/works/{short}"]
    if re.fullmatch(r"\d+", short):
        return [f"{OPENALEX_API}/works/W{short}"]
    return []


def _venue_candidates(data: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    host = data.get("host_venue") or {}
    if isinstance(host, dict) and host.get("display_name"):
        candidates.append(host["display_name"])
    locations = []
    if isinstance(data.get("primary_location"), dict):
        locations.append(data["primary_location"])
    locations.extend(data.get("locations") or [])
    for location in locations:
        if not isinstance(location, dict):
            continue
        source = location.get("source") or {}
        if isinstance(source, dict) and source.get("display_name"):
            candidates.append(source["display_name"])
        if location.get("raw_source_name"):
            candidates.append(location["raw_source_name"])
    unique: List[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def venue_and_tier(data: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Pick the venue string with the most specific CCF match."""
    candidates = _venue_candidates(data)
    display = candidates[0] if candidates else ""
    best_tier = None
    best_len = -1
    for candidate in candidates:
        tier, key_len = match_venue(candidate)
        if tier and key_len > best_len:
            display = candidate
            best_tier = tier
            best_len = key_len
    return display, best_tier


def convert_inverted_index_to_text(inverted_index: Dict[str, List[int]]) -> str:
    """Convert an OpenAlex inverted abstract into plain text."""
    if not inverted_index:
        return ""
    max_position = 0
    for positions in inverted_index.values():
        if positions:
            max_position = max(max_position, max(positions))
    words = [""] * (max_position + 1)
    for word, positions in inverted_index.items():
        for position in positions:
            if 0 <= position < len(words):
                words[position] = word
    return " ".join(word for word in words if word).strip()


def work_to_paper(data: Dict[str, Any], source: str = "OpenAlex") -> Dict[str, Any]:
    """Map an OpenAlex work payload to the public paper shape."""
    doi = normalize_doi(data.get("doi"))
    venue, tier = venue_and_tier(data)
    authors = []
    for authorship in data.get("authorships") or []:
        name = (authorship.get("author") or {}).get("display_name")
        if name:
            authors.append(name)
    abstract = ""
    if data.get("abstract_inverted_index"):
        abstract = convert_inverted_index_to_text(data["abstract_inverted_index"])
    openalex_id = (data.get("id") or "").rstrip("/").rsplit("/", 1)[-1]
    paper: Dict[str, Any] = {
        "title": data.get("title") or "\u672a\u77e5\u6807\u9898",
        "authors": ", ".join(authors),
        "abstract": abstract,
        "citations": data.get("cited_by_count", 0),
        "year": data.get("publication_year") or "\u672a\u77e5\u5e74\u4efd",
        "venue": venue,
        "venue_tier": tier,
        "paper_id": openalex_id,
        "url": data.get("id") or "",
        "doi": doi or "",
        "doi_url": doi_to_url(doi),
        "source": source,
    }
    location = data.get("primary_location") or {}
    pdf_url = ""
    if isinstance(location, dict):
        pdf_url = location.get("pdf_url") or ""
    if not pdf_url:
        pdf_url = (data.get("open_access") or {}).get("oa_url") or ""
    if pdf_url:
        paper["pdf_url"] = pdf_url
    concepts = []
    for concept in data.get("concepts") or []:
        if concept.get("display_name") and concept.get("score", 0) > 0.5:
            concepts.append(concept["display_name"])
    if not concepts:
        for topic in (data.get("topics") or [])[:8]:
            if topic.get("display_name"):
                concepts.append(topic["display_name"])
    if concepts:
        paper["concepts"] = ", ".join(concepts)
    return paper


def deduplicate_papers(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop repeated works, matching bare DOIs and normalized titles."""
    seen_doi = set()
    seen_title = set()
    unique = []
    for paper in papers:
        doi = (normalize_doi(paper.get("doi")) or "").lower()
        title = normalize_title(paper.get("title") or "")
        if doi and doi in seen_doi:
            continue
        if title and title in seen_title:
            continue
        if doi:
            seen_doi.add(doi)
        if title:
            seen_title.add(title)
        unique.append(paper)
    return unique


def _mailto_params() -> Dict[str, str]:
    return {"mailto": EMAIL} if EMAIL else {}


async def enrich_abstract(paper: Dict[str, Any]) -> Dict[str, Any]:
    """Fill a short abstract from the work DOI."""
    paper["abstract_source"] = paper.get("abstract_source") or paper.get("source") or "OpenAlex"
    paper["abstract_quality"] = "\u6807\u51c6" if paper.get("abstract") else "\u7a7a"
    bare = normalize_doi(paper.get("doi"))
    if not bare or len(paper.get("abstract") or "") >= 100:
        return paper
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(
                f"{OPENALEX_API}/works/doi:{quote(bare, safe='/')}",
                params=_mailto_params(),
            )
        if response.status_code == 200:
            abstract = convert_inverted_index_to_text(
                response.json().get("abstract_inverted_index") or {}
            )
            if abstract and len(abstract) > len(paper.get("abstract") or ""):
                paper["abstract"] = abstract
                paper["abstract_quality"] = "\u589e\u5f3a"
    except Exception as exc:
        logger.error("\u901a\u8fc7DOI\u4e30\u5bcc\u6458\u8981\u65f6\u51fa\u9519: %s", exc)
    return paper


async def fetch_openalex_work(paper_id: str) -> Optional[Dict[str, Any]]:
    """Resolve a DOI, OpenAlex id, or arXiv id to a work payload."""
    urls = work_lookup_urls(paper_id)
    if not urls:
        return None
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        for url in urls:
            try:
                response = await client.get(url, params=_mailto_params())
            except httpx.HTTPError as exc:
                logger.warning("OpenAlex lookup failed: %s", exc)
                continue
            if response.status_code == 200:
                return response.json()
            logger.info("OpenAlex lookup missed (%s)", response.status_code)
    return None


async def _original_openalex_search(
    query: str,
    count: int = 5,
    fuzzy_search: bool = False,
    sort_by: str = "relevance",
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
) -> List[Dict[str, Any]]:
    cache_key = f"openalex:v2:{query}:{count}:{fuzzy_search}:{sort_by}:{year_start}:{year_end}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    results: List[Dict[str, Any]] = []
    try:
        search_url = build_openalex_search_url(
            query, count, fuzzy_search, sort_by, year_start, year_end
        )
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(search_url)
        if response.status_code != 200:
            logger.error("OpenAlex API\u641c\u7d22\u9519\u8bef: %s", response.status_code)
            return []
        for paper_data in response.json().get("results") or []:
            results.append(await enrich_abstract(work_to_paper(paper_data)))
            if len(results) >= count:
                break
        if results:
            cache_set(cache_key, results)
        return results
    except Exception as exc:
        logger.error("\u641c\u7d22OpenAlex\u65f6\u51fa\u9519: %s", exc)
        return []


async def _search_openalex(
    query: str,
    count: int,
    fuzzy_search: bool,
    sort_by: str,
    year_start: Optional[int],
    year_end: Optional[int],
) -> List[Dict[str, Any]]:
    return await _original_openalex_search(
        query, count, fuzzy_search, sort_by, year_start, year_end
    )


async def _search_semantic_scholar(query: str, count: int = 5) -> List[Dict[str, Any]]:
    """Fallback search. Keep a DOI or arXiv id so later detail lookups still work."""
    results: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            response = await client.get(
                SEMANTIC_SCHOLAR_API,
                params={
                    "query": query,
                    "limit": max(int(count), 1),
                    "fields": "title,authors,abstract,year,citationCount,externalIds,url,venue",
                },
            )
        if response.status_code == 429:
            logger.warning("Semantic Scholar rate limited; fallback skipped")
            return []
        if response.status_code != 200:
            logger.warning("Semantic Scholar fallback failed: %s", response.status_code)
            return []
        for item in response.json().get("data") or []:
            external = item.get("externalIds") or {}
            doi = normalize_doi(external.get("DOI"))
            arxiv_id = external.get("ArXiv")
            if doi:
                paper_id = doi
            elif arxiv_id:
                paper_id = f"arxiv:{arxiv_id}"
            else:
                paper_id = ""
            venue = item.get("venue") or ""
            authors = ", ".join(
                author.get("name", "")
                for author in item.get("authors") or []
                if author.get("name")
            )
            results.append(
                {
                    "title": item.get("title") or "",
                    "authors": authors,
                    "abstract": item.get("abstract") or "",
                    "citations": item.get("citationCount") or 0,
                    "year": item.get("year") or "\u672a\u77e5\u5e74\u4efd",
                    "venue": venue,
                    "venue_tier": get_venue_tier(venue),
                    "paper_id": paper_id,
                    "semantic_scholar_id": item.get("paperId") or "",
                    "url": item.get("url") or "",
                    "doi": doi or "",
                    "doi_url": doi_to_url(doi),
                    "source": "Semantic Scholar",
                    "abstract_source": "Semantic Scholar",
                }
            )
    except Exception as exc:
        logger.warning("Semantic Scholar fallback failed: %s", exc)
    return results


async def search_scholar(
    query: str,
    count: int = 5,
    fuzzy_search: bool = False,
    sort_by: str = "relevance",
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Search OpenAlex first and fill gaps from Semantic Scholar."""
    cache_key = f"search:v2:{query}:{count}:{fuzzy_search}:{sort_by}:{year_start}:{year_end}"
    cached = cache_get(cache_key)
    if cached is not None:
        logger.info("Cache hit for search: %s", (query or "")[:50])
        return cached

    results = await _original_openalex_search(
        query, count, fuzzy_search, sort_by, year_start, year_end
    )
    if len(results) < max(1, count // 2):
        logger.info("OpenAlex returned %s results, trying Semantic Scholar", len(results))
        results = deduplicate_papers(results + await _search_semantic_scholar(query, count))

    for paper in results:
        paper.setdefault("source", "OpenAlex")
        if not paper.get("venue_tier"):
            paper["venue_tier"] = get_venue_tier(paper.get("venue") or "")
    results = deduplicate_papers(results)[:count]
    if results:
        cache_set(cache_key, results)
    return results


async def get_paper_detail(paper_id: str) -> Optional[Dict[str, Any]]:
    """Fetch one work by OpenAlex id, DOI, or arXiv id."""
    try:
        data = await fetch_openalex_work(paper_id)
        if not data:
            return None
        paper = work_to_paper(data)
        paper["abstract_source"] = "OpenAlex"
        paper["abstract_quality"] = "\u6807\u51c6" if paper.get("abstract") else "\u7a7a"
        paper["requested_id"] = paper_id
        return paper
    except Exception as exc:
        logger.error("\u83b7\u53d6\u8bba\u6587\u8be6\u60c5\u65f6\u51fa\u9519: %s", exc)
        return None


async def get_paper_references(
    paper_id: str, count: int = 5, sort_by: str = "relevance"
) -> List[Dict[str, Any]]:
    """Return papers that cite the given work."""
    try:
        if re.fullmatch(r"W\d+", paper_id or ""):
            openalex_id = paper_id
        else:
            work = await fetch_openalex_work(paper_id)
            if not work:
                return []
            openalex_id = (work.get("id") or "").rstrip("/").rsplit("/", 1)[-1]
        if not re.fullmatch(r"W\d+", openalex_id or ""):
            return []
        parts = [f"filter=cites:{openalex_id}", f"per_page={max(int(count), 1)}"]
        if sort_by == "citations":
            parts.append("sort=cited_by_count:desc")
        elif sort_by == "date":
            parts.append("sort=publication_date:desc")
        elif sort_by == "title":
            parts.append("sort=display_name:asc")
        if EMAIL:
            parts.append("mailto=" + quote(EMAIL))
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(f"{OPENALEX_API}/works?" + "&".join(parts))
        if response.status_code != 200:
            logger.error("\u83b7\u53d6\u8bba\u6587\u5f15\u7528\u9519\u8bef: %s", response.status_code)
            return []
        return [work_to_paper(item) for item in (response.json().get("results") or [])[:count]]
    except Exception as exc:
        logger.error("\u83b7\u53d6\u8bba\u6587\u5f15\u7528\u65f6\u51fa\u9519: %s", exc)
        return []


async def convert_google_scholar_to_openalex(google_id: str) -> str:
    """Map a Google Scholar user id to an OpenAlex author id. Empty string on failure."""
    if not google_id:
        return ""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=headers) as client:
            response = await client.get(
                "https://scholar.google.com/citations",
                params={"user": google_id},
            )
            if response.status_code != 200:
                logger.warning("\u8c37\u6b4c\u5b66\u672f\u4e3b\u9875\u65e0\u6cd5\u8bbf\u95ee: %s", response.status_code)
                return ""
            name_match = re.search(
                r'id="gsc_prf_in"[^>]*>(.*?)</div>',
                response.text,
                re.IGNORECASE | re.DOTALL,
            )
            if not name_match:
                logger.warning("\u65e0\u6cd5\u4ece\u8c37\u6b4c\u5b66\u672f\u9875\u9762\u63d0\u53d6\u5b66\u8005\u59d3\u540d")
                return ""
            scholar_name = html.unescape(re.sub(r"<[^>]+>", "", name_match.group(1))).strip()
            if not scholar_name:
                return ""
            search_response = await client.get(
                f"{OPENALEX_API}/authors",
                params={"search": scholar_name, "per_page": 5, **_mailto_params()},
            )
            if search_response.status_code != 200:
                return ""
            authors = search_response.json().get("results") or []
            if not authors:
                return ""
            return (authors[0].get("id") or "").rstrip("/").rsplit("/", 1)[-1]
    except Exception as exc:
        logger.error("\u8f6c\u6362\u8c37\u6b4c\u5b66\u672fID\u65f6\u51fa\u9519: %s", exc)
        return ""


def extract_profile_id_from_url(url: str) -> str:
    """Extract an author key from an OpenAlex, ORCID, or Google Scholar URL."""
    if not url:
        return ""
    if "openalex.org/authors/" in url:
        return url.split("/authors/", 1)[1].split("?", 1)[0].strip("/")
    if "orcid.org/" in url:
        orcid = url.split("orcid.org/", 1)[1].split("?", 1)[0].strip("/")
        return f"orcid:{orcid}" if orcid else ""
    if "scholar.google." in url:
        match = re.search(r"user=([^&]+)", url)
        if match:
            return f"google:{match.group(1)}"
    logger.warning("\u65e0\u6cd5\u4eceURL\u63d0\u53d6\u5b66\u8005ID")
    return ""


async def _resolve_author(client: httpx.AsyncClient, profile_id: str) -> Dict[str, Any]:
    profile_id = (profile_id or "").strip()
    if profile_id.startswith("google:"):
        mapped = await convert_google_scholar_to_openalex(profile_id.split(":", 1)[1])
        if not mapped:
            raise AuthorNotFound("\u65e0\u6cd5\u4ece\u8c37\u6b4c\u5b66\u672f\u4e3b\u9875\u5339\u914d\u5230\u5b66\u8005")
        profile_id = mapped
    if profile_id.startswith("orcid:"):
        orcid = profile_id.split(":", 1)[1].strip().strip("/")
        url = f"{OPENALEX_API}/authors/orcid:{quote(orcid, safe='-')}"
    else:
        short = profile_id.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
        if re.fullmatch(r"\d+", short):
            short = f"A{short}"
        if not re.fullmatch(r"A\d+", short):
            raise AuthorNotFound("\u65e0\u6cd5\u8bc6\u522b\u5b66\u8005ID")
        url = f"{OPENALEX_API}/authors/{short}"
    response = await client.get(url, params=_mailto_params())
    if response.status_code != 200:
        raise AuthorNotFound("\u672a\u627e\u5230\u8be5\u5b66\u8005")
    return response.json()


async def parse_profile(
    profile_id: str,
    top_n: int = 5,
    sort_by: str = "relevance",
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return papers for an OpenAlex, ORCID, or Google Scholar author."""
    if not profile_id:
        raise AuthorNotFound("\u65e0\u6cd5\u8bc6\u522b\u5b66\u8005\u4e3b\u9875")
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            author = await _resolve_author(client, profile_id)
            short_id = (author.get("id") or "").rstrip("/").rsplit("/", 1)[-1]
            if not re.fullmatch(r"A\d+", short_id):
                raise AuthorNotFound("\u672a\u627e\u5230\u8be5\u5b66\u8005")
            filters = [f"author.id:{short_id}"]
            ranged = year_filter(min_year, max_year)
            if ranged:
                filters.append(ranged)
            parts = [
                "filter=" + ",".join(filters),
                f"per_page={min(max(int(top_n), 1) * 2, 50)}",
            ]
            if sort_by == "citations":
                parts.append("sort=cited_by_count:desc")
            elif sort_by == "date":
                parts.append("sort=publication_date:desc")
            elif sort_by == "title":
                parts.append("sort=display_name:asc")
            if EMAIL:
                parts.append("mailto=" + quote(EMAIL))
            response = await client.get(f"{OPENALEX_API}/works?" + "&".join(parts))
            if response.status_code != 200:
                logger.error("\u83b7\u53d6\u5b66\u8005\u8bba\u6587\u9519\u8bef: %s", response.status_code)
                return []
            papers = []
            for paper_data in response.json().get("results") or []:
                papers.append(work_to_paper(paper_data))
                if len(papers) >= top_n:
                    break
            return papers
    except AuthorNotFound:
        raise
    except Exception as exc:
        logger.error("\u89e3\u6790\u5b66\u8005\u6863\u6848\u65f6\u51fa\u9519: %s", exc)
        return []