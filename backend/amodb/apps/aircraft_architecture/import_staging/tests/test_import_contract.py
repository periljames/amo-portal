from decimal import Decimal

import pytest

from amodb.apps.aircraft_architecture.import_staging import services


def test_header_fingerprint_is_normalized_and_order_independent():
    left = services.header_fingerprint(["Serial Number", "Current FH", "Current-FC"])
    right = services.header_fingerprint(["current_fc", "serial_number", " current fh "])
    assert left == right


def test_normalized_header_collision_is_rejected():
    with pytest.raises(ValueError, match="collide"):
        services.normalize_headers(["Part Number", "part-number"])


def test_fixed_precision_parser_rejects_binary_float():
    assert services.parse_decimal("1234.50") == Decimal("1234.50")
    assert services.parse_decimal(12) == Decimal("12")
    with pytest.raises(ValueError, match="floating-point"):
        services.parse_decimal(12.5)


def test_heterogeneous_datasets_share_one_batch_manifest():
    datasets = [
        services.DatasetInput("AIRCRAFT_MASTER", "EXCEL", "aircraft.xlsx", "a" * 64, ("Registration", "Serial")),
        services.DatasetInput("COMPONENT", "WINAIR", "components.csv", "b" * 64, ("Part Number", "Serial Number")),
    ]
    manifest = services.build_batch_manifest("WINAIR", datasets)
    assert [row["dataset_kind"] for row in manifest["datasets"]] == ["AIRCRAFT_MASTER", "COMPONENT"]
    assert len(services.batch_manifest_hash("WINAIR", datasets)) == 64


def test_default_adapter_registry_covers_required_sources():
    registry = services.default_adapter_registry()
    assert registry.codes == tuple(sorted(services.REQUIRED_ADAPTERS))
    assert registry.resolve("spec2300")({"x": 1})["adapter"] == "SPEC2300"


def test_manifest_is_deterministic_and_rejects_duplicate_content():
    a = services.DatasetInput("COMPONENT", "CSV", "b.csv", "b" * 64, ("PN", "SN"))
    b = services.DatasetInput("AIRCRAFT_MASTER", "CSV", "a.csv", "a" * 64, ("Registration",))
    assert services.batch_manifest_hash("CSV", [a, b]) == services.batch_manifest_hash("csv", [b, a])
    with pytest.raises(ValueError, match="duplicate"):
        services.build_batch_manifest("CSV", [a, a])
