import asyncio

from ddgs import DDGS


async def search(query: str, max_results: int = 5) -> str:
    query = query.replace('"', '').replace("'", '')
    try:
        results = await asyncio.to_thread(lambda: DDGS().text(query, max_results=max_results))
    except Exception:
        return "Sin resultados."
    if not results:
        return "Sin resultados."
    return "\n".join(f"- {r['title']}: {r['body']}" for r in results)
