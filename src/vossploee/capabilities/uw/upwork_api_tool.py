from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from os import getenv
from urllib.error import HTTPError
from urllib.request import Request, urlopen

_UPWORK_GRAPHQL = "https://api.upwork.com/graphql"


def _to_iso_cutoff(minutes: int) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=max(1, int(minutes)))


def _search_sync(
    *,
    query: str,
    minutes: int,
    limit: int,
) -> str:
    token = (getenv("VOSSPLOEE_UPWORK_API_KEY", "") or "").strip()
    if not token:
        return json.dumps(
            {
                "error": "missing_api_key",
                "message": "Set VOSSPLOEE_UPWORK_API_KEY in environment.",
            }
        )
    q = (query or "").strip()
    if not q:
        return json.dumps({"error": "empty_query", "message": "query must be non-empty"})

    graphql = """
    query SearchJobs($query: String!, $limit: Int!) {
      marketplaceJobPostingsSearch(
        paging: { offset: 0, count: $limit }
        sortAttributes: [{ field: RECENCY, sortOrder: DESCENDING }]
        searchExpression_eq: $query
      ) {
        totalCount
        edges {
          node {
            id
            title
            description
            url
            publishedDateTime
            fixedPriceAmount { amount currencyCode }
            hourlyBudgetMin
            hourlyBudgetMax
            client { location { country } }
          }
        }
      }
    }
    """
    payload = json.dumps({"query": graphql, "variables": {"query": q, "limit": max(1, min(limit, 50))}}).encode("utf-8")
    req = Request(
        _UPWORK_GRAPHQL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "vossploee-uw/0.1",
        },
    )
    try:
        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return json.dumps({"error": f"http_{exc.code}", "message": detail[:1500]})
    except OSError as exc:
        return json.dumps({"error": "network_error", "message": str(exc)})

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return json.dumps({"error": "invalid_json", "message": raw[:1500]})

    edges = (
        parsed.get("data", {})
        .get("marketplaceJobPostingsSearch", {})
        .get("edges", [])
    )
    cutoff = _to_iso_cutoff(minutes)
    jobs: list[dict[str, object]] = []
    for edge in edges:
        node = (edge or {}).get("node") or {}
        published = str(node.get("publishedDateTime") or "")
        try:
            published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except ValueError:
            published_dt = None
        if published_dt and published_dt.tzinfo and published_dt.astimezone(UTC) < cutoff:
            continue
        jobs.append(
            {
                "id": node.get("id"),
                "title": node.get("title"),
                "description": node.get("description"),
                "url": node.get("url"),
                "posted_at": published,
                "hourly_rate": {
                    "min": node.get("hourlyBudgetMin"),
                    "max": node.get("hourlyBudgetMax"),
                },
                "client_country": ((node.get("client") or {}).get("location") or {}).get("country"),
            }
        )
    return json.dumps(
        {
            "query": q,
            "minutes": minutes,
            "total_returned": len(jobs),
            "returned_jobs": jobs[: max(1, min(limit, 50))],
        }
    )


async def search_recent_upwork_jobs(query: str, minutes: int = 240, limit: int = 20) -> str:
    return await asyncio.to_thread(_search_sync, query=query, minutes=minutes, limit=limit)
