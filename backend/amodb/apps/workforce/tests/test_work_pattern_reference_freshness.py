from __future__ import annotations

import inspect

from amodb.apps.workforce import hr_router, router


def test_work_pattern_lists_are_never_served_from_an_intermediary_cache() -> None:
    for endpoint in (router.list_work_patterns, hr_router.hr_work_patterns):
        source = inspect.getsource(endpoint)
        assert '"Cache-Control"] = "private, no-store, max-age=0"' in source
        assert '"Pragma"] = "no-cache"' in source
