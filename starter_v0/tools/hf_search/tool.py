from __future__ import annotations

import os
from typing import Any

import requests

from tools._shared import TIMEOUT, err


def search_huggingface(
    query: str = "",
    resource_type: str = "models",
    limit: int = 5,
) -> dict[str, Any]:
    """Tìm kiếm models hoặc datasets trên Hugging Face Hub."""
    try:
        query = (query or "").strip()
        if not query:
            raise ValueError("Query cannot be empty")

        resource = resource_type if resource_type in ("models", "datasets") else "models"
        limit_val = max(1, min(int(limit or 5), 20))

        url = f"https://huggingface.co/api/{resource}"
        params = {"search": query, "limit": limit_val}
        headers = {"User-Agent": "AI20k-Day03-Research-Agent/1.0"}

        hf_token = os.getenv("HF_TOKEN")
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"

        response = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()

        items = []
        for entry in data:
            item_id = entry.get("id") or entry.get("_id", "")
            items.append({
                "id": item_id,
                "url": f"https://huggingface.co/{item_id}",
                "likes": entry.get("likes", 0),
                "downloads": entry.get("downloads", 0),
                "pipeline_tag": entry.get("pipeline_tag", "unknown"),
            })

        return {
            "tool": "hf_search",
            "query": query,
            "resource_type": resource,
            "count": len(items),
            "items": items,
        }
    except Exception as exc:
        return err("hf_search", exc)

