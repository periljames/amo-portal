from io import BytesIO

from openpyxl import Workbook

from amodb.apps.aircraft_architecture.content_packs import ingestion


def q400_sheet_names() -> list[str]:
    return [
        "Section 1",
        "Section 2",
        "Section 3",
        "Supplement 1",
        "Appendix A",
        "Appendix E",
        "Appendix F",
        "Appendix I",
        "Appendix J",
        "Appendix N",
        "Appendix P",
        "Appendix Q",
        "Appendix R",
        "Appendix T",
        "Appendix U",
    ]


def test_q400_profile_requires_core_sections_and_supporting_tables():
    profile, confidence, pack, warnings = ingestion.detect_profile(q400_sheet_names())
    assert profile == "DHC8_400_MPD_V1"
    assert confidence == "HIGH"
    assert pack == "DHC8_400_MPD_SOURCE_INTAKE"
    assert warnings == []


def test_unknown_workbook_is_preview_only():
    profile, confidence, pack, warnings = ingestion.detect_profile(["Status", "Hours"])
    assert profile == "UNMAPPED"
    assert confidence == "LOW"
    assert pack is None
    assert "must not materialize" in warnings[0]


def test_xlsx_preview_inventory_includes_hidden_sheets_without_executing_content():
    workbook = Workbook()
    first = workbook.active
    first.title = "Section 1"
    first.append(["MPD TASK", "INTERVAL"])
    first.append(["212500-201-A-00", "8000 FH"])
    for name in q400_sheet_names()[1:]:
        sheet = workbook.create_sheet(name)
        sheet.append([name, "controlled source"])
    workbook["Appendix U"].sheet_state = "hidden"
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()

    result = ingestion.preview_oem_workbook(filename="MPD.xlsx", content=buffer.getvalue())

    assert result.detected_profile == "DHC8_400_MPD_V1"
    assert result.recommended_pack_code == "DHC8_400_MPD_SOURCE_INTAKE"
    assert len(result.checksum_sha256) == 64
    assert any(sheet.name == "Appendix U" and sheet.state == "HIDDEN" for sheet in result.sheets)
    assert any("Hidden workbook sheets" in warning for warning in result.warnings)
    assert result.source_manifest["materialization_allowed"] is True


def test_preview_renders_floating_cells_as_non_authoritative_strings():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Status"
    sheet.append(["Hours", 1250.25])
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()

    result = ingestion.preview_oem_workbook(filename="source.xlsx", content=buffer.getvalue())

    assert result.sheets[0].sample_rows[0][1] == "1250.25"
