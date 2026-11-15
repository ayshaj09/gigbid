# GigBid Portfolio MCP server

Gives any MCP host (Claude Desktop, Cursor, MCP Inspector) read-only access to a freelancer's
portfolio: case studies, repo READMEs and code, reviews, and past proposals with outcomes. Every
result carries its type, source, date and outcome, so an assistant can cite exactly what backs a
claim.

## Run it
```bash
# from GitHub, no clone needed (replace <you>):
uvx --from git+https://github.com/<you>/gigbid gigbid-portfolio-mcp

# your own folder of *.md case studies, *.pdf CV, code, proposals/*.json:
PORTFOLIO_DIR=~/my-portfolio EMBEDDER_PROVIDER=ollama uvx --from git+https://github.com/<you>/gigbid gigbid-portfolio-mcp
```
Markdown files may start with front matter (`type`, `title`, `skills: [a, b]`, `date`,
`client_industry`, `outcome`). `PORTFOLIO_DIR` is required when installed with `uvx`; from a clone of
the repo, leaving it unset serves the bundled sample persona (`PORTFOLIO_PERSONA=ai_engineer`).

Claude Desktop (`claude_desktop_config.json`):
```json
{ "mcpServers": { "portfolio": {
    "command": "uvx",
    "args": ["--from", "git+https://github.com/<you>/gigbid", "gigbid-portfolio-mcp"],
    "env": { "PORTFOLIO_DIR": "/Users/me/portfolio", "EMBEDDER_PROVIDER": "ollama" } } } }
```
Over the network: `MCP_TRANSPORT=http MCP_TOKENS=<long-random>:<you> gigbid-portfolio-mcp` serves
Streamable HTTP on port 8101 with bearer-token auth.

## Tools
| Tool | What it does |
|---|---|
| `search_evidence(requirement, k, types?, outcome?)` | evidence for one requirement, filterable by type/outcome |
| `match_requirements(requirements[], job_text)` | per-requirement evidence + requirements with no adequate evidence |
| `get_case_study(evidence_id)` | one full item |
| `list_skills()` | skills the portfolio demonstrates, with counts |

Resources: `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://skills`.
Prompts: `answer_screening_question`, `tailor_opening_line`, `find_gaps`.
All tools are read-only (`readOnlyHint`); nothing leaves your machine except through your MCP host.
