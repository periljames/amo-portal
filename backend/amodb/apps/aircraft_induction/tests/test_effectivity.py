from amodb.apps.aircraft_induction.effectivity import evaluate_effectivity, validate_expression


def test_effectivity_combines_variant_msn_part_and_modification():
    context = {
        "aircraft": {"variant_code": "DHC8-315", "msn": 487},
        "configuration": {"part_numbers": ["PW123-ABC", "970525"]},
        "modifications": ["MOD-8-1001"],
    }
    expression = {
        "all": [
            {"field": "aircraft.variant_code", "operator": "eq", "value": "DHC8-315"},
            {"field": "aircraft.msn", "operator": "between", "value": [300, 620]},
            {"field": "configuration.part_numbers", "operator": "contains", "value": "PW123-ABC"},
            {"not": {"field": "modifications", "operator": "contains", "value": "MOD-8-3021"}},
        ]
    }

    result = evaluate_effectivity(expression, context)

    assert result.applicable is True
    assert any("variant_code matched" in line for line in result.explanations)
    assert any("msn matched" in line for line in result.explanations)
    assert any("NOT:" in line for line in result.explanations)


def test_effectivity_explains_failed_serial_range():
    result = evaluate_effectivity(
        {"field": "aircraft.msn", "operator": "between", "value": [300, 620]},
        {"aircraft": {"msn": 812}},
    )

    assert result.applicable is False
    assert result.explanations == [
        "aircraft.msn did not match: actual=812, operator=between, expected=[300, 620]"
    ]


def test_invalid_effectivity_is_rejected_before_publish():
    errors = validate_expression({"all": []})
    assert errors == ["effectivity.all must be a non-empty list"]


def test_any_group_accepts_one_matching_configuration_option():
    result = evaluate_effectivity(
        {
            "any": [
                {"field": "configuration.part_numbers", "operator": "contains", "value": "PT6A-114A"},
                {"field": "configuration.part_numbers", "operator": "contains", "value": "PT6A-140"},
            ]
        },
        {"configuration": {"part_numbers": ["PT6A-140"]}},
    )
    assert result.applicable is True
