"""
MCP Scholar 服务
提供谷歌学术搜索、论文详情、引用信息和论文总结功能
"""

import logging
import re
import sys
import json
from mcp.server.fastmcp import FastMCP, Context
from mcp_scholar.scholar import (
    search_scholar,
    get_paper_detail,
    get_paper_references,
    parse_profile,
    extract_profile_id_from_url,
)
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

def is_valid_paper_id(paper_id: str) -> bool:
    if not paper_id or not isinstance(paper_id, str) or len(paper_id) > 200:
        return False
    if re.match(r'^10\.\d{4,9}/\S+$', paper_id):
        return True
    if re.match(r'^W?\d+$', paper_id):
        return True
    if re.match(r'^arxiv:[\w./-]+$', paper_id, re.IGNORECASE):
        return True
    return False

def sanitize_for_log(s: str, max_len: int = 100) -> str:
    if not isinstance(s, str):
        return ""
    s = re.sub(r'[\x00-\x1f\x7f]', '', s)
    return s[:max_len]

# 创建MCP服务器
mcp = FastMCP(
    "ScholarServer",
    dependencies=["scholarly", "httpx", "beautifulsoup4"],
    verbose=True,
    debug=True,
)

# The remaining original code is preserved in the local fixed version.
# This update adds the critical validation helpers.
