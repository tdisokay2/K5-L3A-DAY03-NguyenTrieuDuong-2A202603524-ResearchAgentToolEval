---
name: hf_search
track: bonus
kind: live_api
provider: Hugging Face API
requires_env: []
inputs: [query, resource_type, limit]
outputs: [tool, query, resource_type, count, items]
side_effect: false
requires_confirmation: false
---
# hf_search

Searches Hugging Face Hub for model checkpoints and datasets via the public REST API.

- Endpoint: `https://huggingface.co/api/{resource_type}?search={query}&limit={limit}`
- Supports `models` and `datasets`.
- Returns repository id, web URL, likes, downloads, and pipeline tag.

