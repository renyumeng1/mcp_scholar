"""
OpenAlex 搜索和解析功能
使用 OpenAlex API 获取学术论文信息
"""

import re
import httpx
import asyncio
import os
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus
from dotenv import load_dotenv
from pathlib import Path


# 获取配置文件路径
def get_env_file():
    """获取.env文件路径"""
    # 首先检查当前工作目录
    if os.path.exists(".env"):
        return ".env"

    # 检查项目根目录
    root_dir = Path(__file__).parent.parent.parent
    env_path = root_dir / ".env"
    if env_path.exists():
        return str(env_path)

    return None


# 配置默认值
DEFAULT_EMAIL = "your-email@example.com"

# 加载环境变量
env_file = get_env_file()
if env_file:
    load_dotenv(env_file)
else:
    print("警告: 未找到.env文件,使用默认配置")

# OpenAlex API 基本URL
OPENALEX_API = "https://api.openalex.org"

# 从环境变量读取email,如果没有则使用默认值
EMAIL = os.environ.get("OPENALEX_EMAIL", DEFAULT_EMAIL)


async def enrich_abstract(paper: Dict[str, Any]) -> Dict[str, Any]:
    """
    尝试丰富论文摘要信息

    Args:
        paper: 包含基本信息的论文字典

    Returns:
        Dict: 添加了完整摘要的论文信息
    """
    # 由于我们直接从OpenAlex获取数据，此函数不再需要额外丰富摘要
    # 但保留函数以保持API兼容性

    paper["abstract_source"] = "OpenAlex"
    paper["abstract_quality"] = "标准"

    # 如果摘要不完整或为空，可以尝试通过DOI获取更多信息
    if paper.get("doi") and (
        not paper.get("abstract") or len(paper.get("abstract", "")) < 100
    ):
        try:
            # 构建API请求URL
            email_param = f"?mailto={EMAIL}" if EMAIL else ""

            async with httpx.AsyncClient(timeout=10.0) as client:
                # 通过DOI查询
                response = await client.get(
                    f"{OPENALEX_API}/works/doi:{paper['doi']}{email_param}"
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("abstract_inverted_index"):
                        # OpenAlex的摘要是倒排索引格式，需要转换为普通文本
                        abstract = convert_inverted_index_to_text(
                            data.get("abstract_inverted_index", {})
                        )
                        if abstract and len(abstract) > len(paper.get("abstract", "")):
                            paper["abstract"] = abstract
                            paper["abstract_quality"] = "增强"
        except Exception as e:
            print(f"通过DOI丰富摘要时出错: {str(e)}")

    return paper


def convert_inverted_index_to_text(inverted_index: Dict[str, List[int]]) -> str:
    """
    将OpenAlex的倒排索引摘要转换为普通文本

    Args:
        inverted_index: OpenAlex的倒排索引格式摘要

    Returns:
        str: 普通文本摘要
    """
    if not inverted_index:
        return ""

    # 创建一个足够大的数组来存放所有单词
    max_position = 0
    for positions in inverted_index.values():
        if positions:
            max_position = max(max_position, max(positions))

    words = [""] * (max_position + 1)

    # 将每个单词放在其位置上
    for word, positions in inverted_index.items():
        for position in positions:
            words[position] = word

    # 连接所有单词形成文本
    return " ".join(words)


async def search_scholar(
    query: str,
    count: int = 5,
    fuzzy_search: bool = False,
    sort_by: str = "relevance",
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    使用OpenAlex API搜索学术论文

    Args:
        query: 搜索关键词
        count: 返回结果数量
        fuzzy_search: 是否启用模糊搜索，当为True时使用更宽松的搜索策略
        sort_by: 排序方式，可选值:
            - "relevance": 按相关性排序（默认）
            - "citations": 按引用量排序
            - "date": 按发表日期排序（新到旧）
            - "title": 按标题字母顺序排序
        year_start: 开始年份，可选
        year_end: 结束年份，可选

    Returns:
        List[Dict]: 论文信息列表
    """
    results = []
    try:
        # 构建搜索查询
        encoded_query = quote_plus(query)

        # 设置电子邮件参数（礼貌请求）
        email_param = f"&mailto={EMAIL}" if EMAIL else ""

        # Build year filter components
        year_filters = []
        if year_start is not None:
            year_filters.append(f"publication_year:>{year_start-1}")
        if year_end is not None:
            year_filters.append(f"publication_year:<{year_end+1}")

        # 搜索参数设置
        if fuzzy_search:
            # 模糊搜索：使用标题、摘要或关键词匹配
            search_url = f"{OPENALEX_API}/works?search={encoded_query}{email_param}&per_page={count*2}"
            # Year filters go in a separate filter= param (no existing filter)
            if year_filters:
                search_url += f"&filter={','.join(year_filters)}"
        else:
            # 精确搜索：在标题中搜索
            # Combine title search and year filters into a single filter= param
            all_filters = [f"title.search:{encoded_query}"] + year_filters
            search_url = f"{OPENALEX_API}/works?filter={','.join(all_filters)}{email_param}&per_page={count*2}"

        # 添加排序方式
        if sort_by == "citations":
            search_url += "&sort=cited_by_count:desc"
        elif sort_by == "date":
            search_url += "&sort=publication_date:desc"
        elif sort_by == "title":
            search_url += "&sort=title:asc"
        # 相关性(relevance)是默认排序，不需要额外参数

        # 准备API请求
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(search_url)

            if response.status_code == 200:
                data = response.json()
                papers = data.get("results", [])

                for paper_data in papers:
                    # 提取论文信息
                    paper = {
                        "title": paper_data.get("title", "未知标题"),
                        "abstract": "",  # 默认为空，稍后处理
                        "citations": paper_data.get("cited_by_count", 0),
                        "year": paper_data.get("publication_year", "未知年份"),
                        "venue": "",  # 需要从期刊/会议信息中提取
                        "paper_id": paper_data.get("id", "").replace(
                            "https://openalex.org/", ""
                        ),
                        "url": paper_data.get("id", ""),
                    }

                    # 处理摘要（OpenAlex 摘要是倒排索引格式）
                    if paper_data.get("abstract_inverted_index"):
                        paper["abstract"] = convert_inverted_index_to_text(
                            paper_data.get("abstract_inverted_index", {})
                        )

                    # 处理作者信息
                    authors = paper_data.get("authorships", [])
                    author_names = []
                    for author in authors:
                        if author.get("author", {}).get("display_name"):
                            author_names.append(author["author"]["display_name"])
                    paper["authors"] = ", ".join(author_names)

                    # 处理期刊/会议信息
                    if paper_data.get("host_venue", {}).get("display_name"):
                        paper["venue"] = paper_data["host_venue"]["display_name"]

                    # 处理DOI信息
                    if paper_data.get("doi"):
                        doi_value = paper_data["doi"]
                        # OpenAlex returns DOI as full URL (e.g. "https://doi.org/10.1234/...")
                        # Strip the prefix to get the bare DOI identifier
                        if doi_value.startswith("https://doi.org/"):
                            doi_value = doi_value[len("https://doi.org/") :]
                        paper["doi"] = doi_value
                        paper["doi_url"] = f"https://doi.org/{doi_value}"

                    # 丰富摘要信息
                    paper = await enrich_abstract(paper)

                    results.append(paper)

                # 只返回需要的数量
                return results[:count]
            else:
                print(f"OpenAlex API搜索错误: {response.status_code} - {response.text}")
                return []

    except Exception as e:
        print(f"搜索OpenAlex时出错: {str(e)}")
        return []


async def get_paper_detail(paper_id: str) -> Optional[Dict[str, Any]]:
    """
    通过OpenAlex API获取论文详情

    Args:
        paper_id: 论文ID，可以是OpenAlex ID、DOI或ArXiv ID

    Returns:
        Dict: 论文详细信息
    """
    try:
        # 设置电子邮件参数（礼貌请求）
        email_param = f"?mailto={EMAIL}" if EMAIL else ""

        # 确定使用什么ID类型
        if paper_id.startswith("10."):  # 看起来是DOI
            api_url = f"{OPENALEX_API}/works/doi:{paper_id}{email_param}"
        elif paper_id.startswith("W"):  # OpenAlex ID
            api_url = f"{OPENALEX_API}/works/{paper_id}{email_param}"
        elif paper_id.lower().startswith("arxiv:"):  # arXiv ID
            api_url = f"{OPENALEX_API}/works/arxiv:{paper_id.replace('arxiv:', '')}{email_param}"
        else:  # 尝试作为OpenAlex ID (不带前缀的)
            api_url = f"{OPENALEX_API}/works/W{paper_id}{email_param}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(api_url)

            if response.status_code == 200:
                data = response.json()

                # 提取论文详细信息
                result = {
                    "title": data.get("title", "未知标题"),
                    "abstract": "",  # 默认为空，稍后处理
                    "citations": data.get("cited_by_count", 0),
                    "year": data.get("publication_year", "未知年份"),
                    "venue": "",  # 需要从期刊/会议信息中提取
                    "paper_id": data.get("id", "").replace("https://openalex.org/", ""),
                    "url": data.get("id", ""),
                }

                # 处理摘要（OpenAlex 摘要是倒排索引格式）
                if data.get("abstract_inverted_index"):
                    result["abstract"] = convert_inverted_index_to_text(
                        data.get("abstract_inverted_index", {})
                    )

                # 处理作者信息
                authors = data.get("authorships", [])
                author_names = []
                for author in authors:
                    if author.get("author", {}).get("display_name"):
                        author_names.append(author["author"]["display_name"])
                result["authors"] = ", ".join(author_names)

                # 处理期刊/会议信息
                if data.get("host_venue", {}).get("display_name"):
                    result["venue"] = data["host_venue"]["display_name"]

                # 处理DOI信息
                if data.get("doi"):
                    doi_value = data["doi"]
                    # OpenAlex returns DOI as full URL (e.g. "https://doi.org/10.1234/...")
                    # Strip the prefix to get the bare DOI identifier
                    if doi_value.startswith("https://doi.org/"):
                        doi_value = doi_value[len("https://doi.org/") :]
                    result["doi"] = doi_value
                    result["doi_url"] = f"https://doi.org/{doi_value}"

                # 添加PDF链接（如果有）
                if data.get("open_access", {}).get("oa_url"):
                    result["pdf_url"] = data["open_access"]["oa_url"]

                # 添加关键概念
                if data.get("concepts"):
                    concepts = []
                    for concept in data["concepts"]:
                        if (
                            concept.get("display_name")
                            and concept.get("score", 0) > 0.5
                        ):  # 只添加相关性高的概念
                            concepts.append(concept["display_name"])
                    if concepts:
                        result["concepts"] = ", ".join(concepts)

                return result
            else:
                print(f"获取论文详情错误: {response.status_code} - {response.text}")
                return None

    except Exception as e:
        print(f"获取论文详情时出错: {str(e)}")
        return None


async def get_paper_references(
    paper_id: str, count: int = 5, sort_by: str = "relevance"
) -> List[Dict[str, Any]]:
    """
    通过OpenAlex API获取引用指定论文的文献

    Args:
        paper_id: 论文ID，可以是OpenAlex ID、DOI或ArXiv ID
        count: 返回结果数量
        sort_by: 排序方式，可选值:
            - "relevance": 按相关性排序（默认）
            - "citations": 按引用量排序
            - "date": 按发表日期排序（新到旧）
            - "title": 按标题字母顺序排序

    Returns:
        List[Dict]: 引用论文信息列表
    """
    results = []
    try:
        # 设置电子邮件参数（礼貌请求）
        email_param = f"&mailto={EMAIL}" if EMAIL else ""

        # 确定API ID
        openalex_id = paper_id

        # 如果是DOI或arXiv ID，需要先获取OpenAlex ID
        if paper_id.startswith("10.") or paper_id.lower().startswith("arxiv:"):
            id_type = "doi" if paper_id.startswith("10.") else "arxiv"
            id_value = (
                paper_id
                if paper_id.startswith("10.")
                else paper_id.replace("arxiv:", "")
            )

            # 查询以获取OpenAlex ID
            async with httpx.AsyncClient(timeout=10.0) as client:
                id_response = await client.get(
                    f"{OPENALEX_API}/works/{id_type}:{id_value}?mailto={EMAIL if EMAIL else ''}"
                )

                if id_response.status_code == 200:
                    id_data = id_response.json()
                    openalex_id = id_data.get("id", "").replace(
                        "https://openalex.org/", ""
                    )
                else:
                    print(f"获取OpenAlex ID错误: {id_response.status_code}")
                    return []

        # 去掉可能的前缀
        if openalex_id.startswith("W"):
            openalex_id = openalex_id[1:]

        # 构建引用查询
        citations_url = f"{OPENALEX_API}/works?filter=cites:W{openalex_id}{email_param}&per_page={count}"

        # 添加排序方式
        if sort_by == "citations":
            citations_url += "&sort=cited_by_count:desc"
        elif sort_by == "date":
            citations_url += "&sort=publication_date:desc"
        elif sort_by == "title":
            citations_url += "&sort=title:asc"
        # 相关性(relevance)是默认排序，不需要额外参数

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(citations_url)

            if response.status_code == 200:
                data = response.json()
                citation_papers = data.get("results", [])

                for paper_data in citation_papers:
                    # 提取论文信息
                    paper = {
                        "title": paper_data.get("title", "未知标题"),
                        "abstract": "",  # 默认为空，稍后处理
                        "citations": paper_data.get("cited_by_count", 0),
                        "year": paper_data.get("publication_year", "未知年份"),
                        "venue": "",  # 需要从期刊/会议信息中提取
                        "paper_id": paper_data.get("id", "").replace(
                            "https://openalex.org/", ""
                        ),
                        "url": paper_data.get("id", ""),
                    }

                    # 处理摘要（OpenAlex 摘要是倒排索引格式）
                    if paper_data.get("abstract_inverted_index"):
                        paper["abstract"] = convert_inverted_index_to_text(
                            paper_data.get("abstract_inverted_index", {})
                        )

                    # 处理作者信息
                    authors = paper_data.get("authorships", [])
                    author_names = []
                    for author in authors:
                        if author.get("author", {}).get("display_name"):
                            author_names.append(author["author"]["display_name"])
                    paper["authors"] = ", ".join(author_names)

                    # 处理期刊/会议信息
                    if paper_data.get("host_venue", {}).get("display_name"):
                        paper["venue"] = paper_data["host_venue"]["display_name"]

                    # 处理DOI信息
                    if paper_data.get("doi"):
                        doi_value = paper_data["doi"]
                        # OpenAlex returns DOI as full URL (e.g. "https://doi.org/10.1234/...")
                        # Strip the prefix to get the bare DOI identifier
                        if doi_value.startswith("https://doi.org/"):
                            doi_value = doi_value[len("https://doi.org/") :]
                        paper["doi"] = doi_value
                        paper["doi_url"] = f"https://doi.org/{doi_value}"

                    results.append(paper)

                return results
            else:
                print(f"获取论文引用错误: {response.status_code} - {response.text}")
                return []

    except Exception as e:
        print(f"获取论文引用时出错: {str(e)}")
        return []


async def convert_google_scholar_to_openalex(google_id: str) -> str:
    """
    尝试将谷歌学术ID转换为OpenAlex学者ID

    Args:
        google_id: 谷歌学术ID

    Returns:
        str: OpenAlex学者ID，如果无法转换则返回空字符串
    """
    try:
        # 尝试从谷歌学术页面获取学者姓名
        scholar_url = f"https://scholar.google.com/citations?user={google_id}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            # 获取谷歌学术页面
            response = await client.get(scholar_url, follow_redirects=True)

            if response.status_code == 200:
                # 使用简单的正则表达式从HTML中提取学者姓名
                html = response.text
                name_match = re.search(r'<div id="gsc_prf_in">(.*?)</div>', html)

                if name_match:
                    scholar_name = name_match.group(1).strip()
                    print(f"从谷歌学术获取到学者姓名: {scholar_name}")

                    # 使用姓名在OpenAlex中搜索作者
                    email_param = f"&mailto={EMAIL}" if EMAIL else ""
                    search_url = f"{OPENALEX_API}/authors?search={quote_plus(scholar_name)}{email_param}&per_page=5"

                    search_response = await client.get(search_url)

                    if search_response.status_code == 200:
                        data = search_response.json()
                        results = data.get("results", [])

                        if results:
                            # 选择第一个结果作为匹配项
                            return (
                                results[0]
                                .get("id", "")
                                .replace("https://openalex.org/", "")
                            )

        print(f"无法将谷歌学术ID {google_id} 转换为OpenAlex ID")
        return ""  # 如果无法转换，返回空字符串

    except Exception as e:
        print(f"转换谷歌学术ID时出错: {str(e)}")
        return ""


def extract_profile_id_from_url(url: str) -> str:
    """
    从OpenAlex个人主页URL中提取学者ID

    Args:
        url: OpenAlex个人主页URL或谷歌学术URL

    Returns:
        str: 学者ID
    """
    # 处理OpenAlex URL
    if "openalex.org/authors/" in url:
        # 格式: https://openalex.org/authors/A[ID]
        parts = url.split("/authors/")
        if len(parts) > 1:
            author_id = parts[1].strip()
            return author_id  # 返回带A前缀的ID

    # 处理ORCID URL
    elif "orcid.org/" in url:
        # 格式: https://orcid.org/[ORCID]
        parts = url.split("orcid.org/")
        if len(parts) > 1:
            orcid = parts[1].strip()
            if orcid:
                # 这里需要查询OpenAlex来获取对应的ID
                print(f"发现ORCID: {orcid}，需要查询OpenAlex获取作者ID")
                return f"orcid:{orcid}"  # 返回ORCID格式的ID

    # 处理谷歌学术URL (需要额外查询)
    elif "scholar.google.com" in url:
        match = re.search(r"user=([^&]+)", url)
        if match:
            google_id = match.group(1)
            return f"google:{google_id}"  # 返回谷歌学术格式的ID，稍后会自动转换

    print(f"警告: 无法从URL提取OpenAlex学者ID: {url}")
    return ""


async def parse_profile(
    profile_id: str, top_n: int = 5, sort_by: str = "relevance"
) -> List[Dict[str, Any]]:
    """
    通过OpenAlex API解析学者档案和论文

    Args:
        profile_id: 学者ID
        top_n: 返回结果数量
        sort_by: 排序方式，可选值:
            - "relevance": 按相关性排序（默认）
            - "citations": 按引用量排序
            - "date": 按发表日期排序（新到旧）
            - "title": 按标题字母顺序排序

    Returns:
        List[Dict]: 论文信息列表
    """
    try:
        # 设置电子邮件参数（礼貌请求）
        mailto_value = f"mailto={EMAIL}" if EMAIL else ""

        # 处理谷歌学术ID
        if profile_id.startswith("google:"):
            google_id = profile_id.replace("google:", "")
            openalex_id = await convert_google_scholar_to_openalex(google_id)
            if not openalex_id:
                return []
        else:
            # 确定API ID
            openalex_id = profile_id

        # 如果不是标准的OpenAlex作者ID格式，添加前缀
        if not openalex_id.startswith("A"):
            openalex_id = f"A{openalex_id}"

        # 获取作者信息
        async with httpx.AsyncClient(timeout=15.0) as client:
            author_email = f"?{mailto_value}" if mailto_value else ""
            author_url = f"{OPENALEX_API}/authors/{openalex_id}{author_email}"
            author_response = await client.get(author_url)

            if author_response.status_code != 200:
                print(f"未找到ID为{profile_id}的学者: {author_response.status_code}")
                return []

            author_data = author_response.json()

            # 获取作者论文
            papers_email = f"&{mailto_value}" if mailto_value else ""
            papers_url = f"{OPENALEX_API}/works?filter=author.id:{author_data['id']}{papers_email}&per_page={top_n*2}"

            # 添加排序方式
            if sort_by == "citations":
                papers_url += "&sort=cited_by_count:desc"
            elif sort_by == "date":
                papers_url += "&sort=publication_date:desc"
            elif sort_by == "title":
                papers_url += "&sort=title:asc"
            # 相关性(relevance)是默认排序，不需要额外参数

            papers_response = await client.get(papers_url)

            if papers_response.status_code != 200:
                print(f"获取学者论文错误: {papers_response.status_code}")
                return []

            papers_data = papers_response.json()
            papers = papers_data.get("results", [])
            result_papers = []

            for paper_data in papers:
                # 提取论文信息
                paper = {
                    "title": paper_data.get("title", "未知标题"),
                    "abstract": "",  # 默认为空，稍后处理
                    "citations": paper_data.get("cited_by_count", 0),
                    "year": paper_data.get("publication_year", "未知年份"),
                    "venue": "",  # 需要从期刊/会议信息中提取
                    "paper_id": paper_data.get("id", "").replace(
                        "https://openalex.org/", ""
                    ),
                    "url": paper_data.get("id", ""),
                }

                # 处理摘要（OpenAlex 摘要是倒排索引格式）
                if paper_data.get("abstract_inverted_index"):
                    paper["abstract"] = convert_inverted_index_to_text(
                        paper_data.get("abstract_inverted_index", {})
                    )

                # 处理作者信息
                authors = paper_data.get("authorships", [])
                author_names = []
                for author in authors:
                    if author.get("author", {}).get("display_name"):
                        author_names.append(author["author"]["display_name"])
                paper["authors"] = ", ".join(author_names)

                # 处理期刊/会议信息
                if paper_data.get("host_venue", {}).get("display_name"):
                    paper["venue"] = paper_data["host_venue"]["display_name"]

                # 处理DOI信息
                if paper_data.get("doi"):
                    doi_value = paper_data["doi"]
                    # OpenAlex returns DOI as full URL (e.g. "https://doi.org/10.1234/...")
                    # Strip the prefix to get the bare DOI identifier
                    if doi_value.startswith("https://doi.org/"):
                        doi_value = doi_value[len("https://doi.org/") :]
                    paper["doi"] = doi_value
                    paper["doi_url"] = f"https://doi.org/{doi_value}"

                result_papers.append(paper)

            return result_papers[:top_n]

    except Exception as e:
        print(f"解析学者档案时出错: {str(e)}")
        return []
