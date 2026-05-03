from duckduckgo_search import AsyncDDGS


async def search(query: str, max_results: int = 5) -> str:
    query = query.replace('"', '').replace("'", '')
    try:
        async with AsyncDDGS() as ddgs:
            results = await ddgs.atext(query, max_results=max_results)
    except Exception:
        return "Sin resultados."
    if not results:
        return "Sin resultados."
    return "\n".join(f"- {r['title']}: {r['body']}" for r in results)
