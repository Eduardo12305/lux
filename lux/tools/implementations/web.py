# lux/tools/implementations/web.py
import re
import httpx
from lux.agent.state import AgentState, ToolResult
from lux.config import get_config
from lux.tools.base import Tool


class WebSearchTool(Tool):
    name = "web_search"
    description = "Busca na web via SearXNG local (ou DuckDuckGo fallback)"
    timeout_seconds = 15
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Termo de busca"},
            "limit": {"type": "integer", "description": "Max resultados", "default": 5},
        },
        "required": ["query"],
    }

    async def _search_searxng(self, query: str, limit: int) -> list[dict]:
        config = get_config()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{config.searxng_url}/search",
                params={"q": query, "format": "json", "categories": "general"},
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])[:limit]
            return [{"title": r.get("title", ""), "url": r.get("url", ""),
                     "snippet": r.get("content", "")[:300]} for r in results]

    async def _search_duckduckgo(self, query: str, limit: int) -> list[dict]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Lux/1.0"},
            )
            if resp.status_code != 200:
                return []
            html = resp.text
            results = []
            for match in re.finditer(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
                html, re.DOTALL,
            ):
                url = match.group(1)
                title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
                results.append({"title": title, "url": url, "snippet": snippet[:300]})
                if len(results) >= limit:
                    break
            return results

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self._async_execute(args))

    async def _async_execute(self, args: dict) -> ToolResult:
        query = args.get("query", "")
        limit = args.get("limit", 5)
        if not query.strip():
            return ToolResult.failure("Query vazia.")

        results = []
        try:
            results = await self._search_searxng(query, limit)
        except Exception:
            pass

        if not results:
            try:
                results = await self._search_duckduckgo(query, limit)
            except Exception:
                pass

        if not results:
            return ToolResult.ok(
                "Nenhum resultado encontrado. "
                "Verifique se o SearXNG esta rodando (docker-compose up -d searxng)."
            )

        lines = [f"Resultados para '{query}':"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   {r['url']}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet'][:200]}")
        return ToolResult.ok("\n".join(lines))


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Extrai o conteudo textual de uma URL"
    timeout_seconds = 20
    parameters_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL a buscar"},
        },
        "required": ["url"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self._async_execute(args))

    async def _async_execute(self, args: dict) -> ToolResult:
        url = args.get("url", "")
        if not url.startswith("http"):
            return ToolResult.failure("URL invalida. Use https://...")

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "Lux/1.0"},
                    follow_redirects=True,
                )
                resp.raise_for_status()
                html = resp.text[:100_000]

            text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            text = text[:8000]

            return ToolResult.ok(
                f"Conteudo de {url}:\n\n{text}\n\n(truncado em 8000 caracteres)"
            )
        except httpx.HTTPStatusError as e:
            return ToolResult.failure(f"HTTP {e.response.status_code}")
        except Exception as e:
            return ToolResult.failure(f"Falha ao buscar URL: {e}")
