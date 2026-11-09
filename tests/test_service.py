"""
Unit test suite for Command Parsing Service and Schema Validation.
Requires pytest and httpx/fastapi.
"""

import os
import json
import pytest
from fastapi.testclient import TestClient
from service.app import app, validate_schema

client = TestClient(app)

def test_healthz_endpoint():
    """Verify that /healthz returns HTTP 200 with status alive."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}

def test_schema_valid_output():
    """Verify that a well-formed 4-key JSON passes schema validation."""
    valid_json_str = json.dumps({
        "intent": "alarm_set",
        "date": "tomorrow",
        "time": "seven thirty am",
        "place": None
    })
    parsed = validate_schema(valid_json_str)
    assert parsed is not None
    assert parsed["intent"] == "alarm_set"
    assert parsed["date"] == "tomorrow"
    assert parsed["time"] == "seven thirty am"
    assert parsed["place"] is None

def test_schema_invalid_keys():
    """Verify that JSON with missing or extra keys fails schema validation."""
    # Extra key
    invalid_json_extra = json.dumps({
        "intent": "weather_query",
        "date": None,
        "time": None,
        "place": "london",
        "extra_field": "disallowed"
    })
    assert validate_schema(invalid_json_extra) is None

    # Missing key
    invalid_json_missing = json.dumps({
        "intent": "weather_query",
        "date": None,
        "place": "london"
    })
    assert validate_schema(invalid_json_missing) is None

def test_schema_invalid_intent():
    """Verify that an unrecognized intent fails schema validation."""
    invalid_intent_json = json.dumps({
        "intent": "play_music",
        "date": None,
        "time": None,
        "place": None
    })
    assert validate_schema(invalid_intent_json) is None

def test_fault_injection():
    """Verify that setting FAULT_INJECT=1 triggers HTTP 500 invalid_model_output."""
    os.environ["FAULT_INJECT"] = "1"
    response = client.post("/parse", json={"text": "what time is it in tokyo"})
    assert response.status_code == 500
    assert response.json() == {"error": "invalid_model_output"}
    os.environ["FAULT_INJECT"] = "0"
