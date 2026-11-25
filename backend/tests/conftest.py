import copy

import pytest

_VALID = {
    "metadata": {
        "schema_version": "1.0",
        "owner_name": "Test Engineer",
        "generated_at": "2026-11-01T10:00:00Z",
        "data_source": "GitHub PRs",
        "sanitised": True,
    },
    "professional_summary": {
        "summary": "Backend engineer.",
        "experience_level": "3 years",
        "primary_roles": ["Backend Engineer"],
        "primary_technologies": ["Python"],
    },
    "projects": [
        {
            "id": "proj-cache",
            "name": "Response caching",
            "summary": "Added caching to a slow endpoint.",
            "problem": "Endpoint was slow under load.",
            "my_contributions": ["Designed and implemented the cache layer."],
            "implementation": "Read-through cache with TTL invalidation.",
            "decisions": [
                {
                    "context": "Needed a cache store.",
                    "decision": "Use Redis.",
                    "reasoning": "Already in the stack.",
                    "pr_ids": ["pr-1"],
                }
            ],
            "metrics": [
                {
                    "name": "p95 latency",
                    "before": 800,
                    "after": 120,
                    "unit": "ms",
                    "evidence": "Load test results in PR description.",
                }
            ],
            "categories": ["Performance Optimisation"],
            "skills": [
                {"name": "Redis", "involvement": "implemented", "evidence": "Built cache layer."}
            ],
            "pr_ids": ["pr-1", "pr-2"],
            "complexity": "medium",
            "confidence": "high",
        }
    ],
    "pull_requests": [
        {
            "id": "pr-1",
            "project_id": "proj-cache",
            "title": "Add Redis cache",
            "summary": "Adds read-through cache.",
            "contribution": "Wrote the cache module.",
            "created_at": "2026-01-01",
            "merged_at": "2026-01-03",
            "status": "merged",
            "confidence": "high",
        },
        {
            "id": "pr-2",
            "project_id": "proj-cache",
            "title": "Cache invalidation",
            "summary": "Invalidates cache on writes.",
            "contribution": "Added invalidation hooks.",
            "created_at": "2026-01-05",
            "merged_at": "2026-01-06",
            "status": "merged",
            "confidence": "medium",
        },
    ],
    "skills": [{"name": "Redis", "category": "Databases", "aliases": ["redis-py"]}],
    "categories": [{"name": "Performance Optimisation"}],
}


@pytest.fixture
def valid_data() -> dict:
    """A small, fully valid experience file. Tests mutate their own copy."""
    return copy.deepcopy(_VALID)
