"""Provider-independent generation schema; FindingValidator independently enforces B09 candidate rules."""


def finding_schema(max_findings: int, evidence_per_finding: int) -> dict:
    evidence = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "path": {"type": "string", "minLength": 1, "maxLength": 512},
            "start_line": {"type": "integer", "minimum": 1},
            "end_line": {"type": "integer", "minimum": 1},
        },
        "required": ["path", "start_line", "end_line"],
    }
    properties = {
        "category": {"type": "string", "enum": ["architecture", "maintainability",
                                                   "reliability", "security", "testing"]},
        "severity": {"type": "string", "enum": ["info", "low", "medium", "high", "critical"]},
        "title": {"type": "string", "minLength": 1, "maxLength": 160},
        "explanation": {"type": "string", "minLength": 1, "maxLength": 4000},
        "recommendation": {"type": "string", "minLength": 1, "maxLength": 2000},
        "evidence": {"type": "array", "minItems": 1,
                     "maxItems": evidence_per_finding, "items": evidence},
    }
    without_confidence = {"type": "object", "additionalProperties": False,
                          "properties": properties, "required": list(properties)}
    with_properties = {**properties, "confidence": {"type": "number", "minimum": 0, "maximum": 1}}
    with_confidence = {"type": "object", "additionalProperties": False,
                       "properties": with_properties, "required": list(with_properties)}
    # Strict providers require every property of each object to be required.
    # Nested alternatives preserve optional confidence WITHOUT introducing null.
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "integer", "enum": [1]},
            "findings": {"type": "array", "maxItems": max_findings,
                         "items": {"anyOf": [without_confidence, with_confidence]}},
        },
        "required": ["schema_version", "findings"],
    }
