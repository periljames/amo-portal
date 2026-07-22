from __future__ import annotations

from importlib import import_module

from sqlalchemy.orm import configure_mappers


def test_core_application_mappers_configure_without_ambiguous_relationships():
    for module_name in (
        "amodb.apps.accounts.models",
        "amodb.apps.foundations.models",
        "amodb.apps.training.models",
        "amodb.apps.work.models",
        "amodb.apps.realtime.models",
        "amodb.apps.rostering.models",
        "amodb.apps.workforce.models",
    ):
        import_module(module_name)

    configure_mappers()
