<div align="center">

# 🎓 MCP Scholar

**An Academic Research & Literature Analysis Server Built on the Model Context Protocol (MCP)**  
**基于模型上下文协议（MCP）的学术文献检索与分析服务**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![MCP SDK](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)
[![Package Manager](https://img.shields.io/badge/uv-managed-purple.svg)](https://github.com/astral-sh/uv)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[English](#english) | [简体中文](#简体中文)

</div>

---

<a name="english"></a>

## 🌍 English

### Overview

**MCP Scholar** (`mcp-scholar`) is a lightweight, extensible Model Context Protocol (MCP) server designed for academic researchers and AI agents. It empowers MCP-compatible clients—such as **Claude Desktop**, **Claude Code**, **Cursor**, and **Cherry Studio**—to search academic literature across multiple sources (OpenAlex primary, Semantic Scholar when OpenAlex is thin), inspect paper details and references, analyze researcher profiles, and verify citations directly within conversational or agentic workflows.

### ✨ Key Features (v0.4.1)

- 🔎 **Unified Multi-Source Search**: Single `search_papers` tool with strategy control (`exact` / `adaptive` / `hybrid`). OpenAlex as the primary source, with Semantic Scholar used when OpenAlex returns too few results.
- 📄 **Deep Paper Inspection**: Retrieve comprehensive metadata, full abstracts, and reference lists.
- 👨‍🔬 **Scholar Profile Analytics**: Parse author profiles for high-impact publications.
- ✅ **BibTeX Verification**: Cross-check and enrich BibTeX entries against Crossref/OpenAlex.
- 🔌 **MCP Tool Annotations**: Read-only tools marked with `readOnlyHint` / `idempotentHint` for safer auto-approval in clients.
- ⚡ **Zero-friction Execution**: `uvx mcp-scholar` ready.

### 🛠️ Available Tools

| Tool Name | Description | Key Parameters |
| :--- | :--- | :--- |
| `search_papers` | Unified literature search (replaces old scholar_search + adaptive_search) | `keywords`, `count`, `strategy` (`exact`\|`adaptive`\|`hybrid`), `sort_by`, `year_start`, `year_end` |
| `paper_detail` | Fetch detailed metadata and full abstract | `paper_id` |
| `paper_references` | Extract references / citing papers | `paper_id`, `count` |
| `profile_papers` | Analyze author profile and top papers | `profile_url` / `user_id`, `count` |
| `verify_bibtex` | Verify and enrich BibTeX entries | `bibtex` |
| `health_check` | Check server and upstream availability | None |

Legacy tools (`scholar_search`, `adaptive_search`, `summarize_papers`) remain available for compatibility but are deprecated in favor of the unified tools + host-model prompts.

### 🚀 Installation & Quick Start

```bash
uvx mcp-scholar
```

Or from source:

```bash
git clone https://github.com/renyumeng1/mcp_scholar.git
cd mcp_scholar
uv sync
uv run mcp-scholar
```

### ⚙️ Client Configuration

```json
{
  "mcpServers": {
    "mcp-scholar": {
      "command": "uvx",
      "args": ["mcp-scholar"]
    }
  }
}
```

### 🗺️ Roadmap (beyond v0.3.0)

- Full multi-source federation (Semantic Scholar, Crossref, arXiv, DBLP)
- Preprint ↔ published deduplication
- OA PDF section-aware parsing (Methodology / Experiments)
- Citation intent analysis & bridge papers
- Zotero integration
- Local SQLite cache with TTL

---

<a name="简体中文"></a>

## 🇨🇳 简体中文

### 项目简介

**MCP Scholar**（`mcp-scholar`）是基于 **模型上下文协议（MCP）** 的学术文献检索与分析服务端。它可无缝接入 Claude Desktop、Claude Code、Cursor、Cherry Studio 等客户端，支持多源学术检索、论文详情与引文溯源、学者主页分析以及 BibTeX 真实性核查。

### ✨ 核心特性 (v0.4.1)

- 🔎 **统一多源检索**：`search_papers` 工具支持 `exact` / `adaptive` / `hybrid` 策略。OpenAlex 为主力来源；结果太少时再用 Semantic Scholar 补齐。
- 📄 **单篇详情与引文**：完整元数据、摘要与参考文献。
- 👨‍🔬 **学者主页分析**：提取高被引代表作。
- ✅ **BibTeX 核查**：通过 Crossref/OpenAlex 核验并补全文献信息。
- 🔌 **MCP 工具注解**：只读工具带有 `readOnlyHint` 等标准注解，客户端可更安全地自动放行。
- ⚡ **一键启动**：`uvx mcp-scholar`。

### 🛠️ 工具列表

| 工具名称 | 功能说明 | 核心参数 |
| :--- | :--- | :--- |
| `search_papers` | 统一学术检索（替代旧的 scholar_search + adaptive_search） | `keywords`, `count`, `strategy`, `sort_by`, `year_start`, `year_end` |
| `paper_detail` | 获取单篇论文详细信息 | `paper_id` |
| `paper_references` | 获取引用/参考文献 | `paper_id`, `count` |
| `profile_papers` | 分析学者主页高引论文 | `profile_url`, `count` |
| `verify_bibtex` | 核验并补全 BibTeX | `bibtex` |
| `health_check` | 健康检查 | 无 |

旧工具仍保留以兼容，但推荐使用新统一工具 + 宿主模型提示词完成总结。

### 🚀 安装

```bash
uvx mcp-scholar
```

### 🗺️ 演进路线图

- 完整多源联邦（Semantic Scholar、Crossref、arXiv、DBLP）
- 预印本与正式版自动对齐
- OA PDF 分章节解析
- 引用意图分析
- Zotero 联动
- 本地 SQLite 缓存

---

### 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。
