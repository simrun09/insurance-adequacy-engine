from fastapi.testclient import TestClient

from engine.api import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Shared payloads
# ---------------------------------------------------------------------------

FULL_PROFILE = {
    "age": 35,
    "gender": "male",
    "city_tier": "tier_1",
    "annual_income": 1800000,
    "monthly_expenses": 40000,
    "monthly_insurance_budget": 5000,
    "tax_regime": "old",
    "spouse": {"age": 32, "annual_income": 0},
    "children": [
        {
            "age": 4,
            "education_cost_estimate": 2500000,
            "marriage_cost_estimate": 1500000,
        }
    ],
    "dependent_parents": [{"age": 64, "has_own_health_cover": False}],
    "loans": [
        {
            "loan_type": "home loan",
            "outstanding_balance": 6000000,
            "remaining_tenure_years": 20,
        }
    ],
    "future_expenses": [],
    "existing_policies": [
        {
            "policy_type": "term",
            "sum_assured": 10000000,
            "annual_premium": 12000,
            "start_year": 2021,
        },
        {
            "policy_type": "health",
            "sum_assured": 500000,
            "annual_premium": 15000,
            "start_year": 2022,
        },
    ],
    "investable_assets": 800000,
    "epf_ppf_balance": 1200000,
}

MINIMAL_PROFILE = {
    # Single person, no dependents, no loans, no existing policies
    "age": 28,
    "gender": "female",
    "city_tier": "tier_2",
    "annual_income": 600000,
    "monthly_expenses": 15000,
    "monthly_insurance_budget": 1500,
    "tax_regime": "new",
}


# ---------------------------------------------------------------------------
# 1. Health endpoint
# ---------------------------------------------------------------------------


def test_health_returns_200_and_status():
    # Verifies the liveness check is reachable and returns the expected shape.
    # Load balancers and deployment tools depend on this endpoint.
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


# ---------------------------------------------------------------------------
# 2. Full profile — all expected fields present in response
# ---------------------------------------------------------------------------


def test_assess_full_profile_returns_200_with_all_fields():
    # Verifies the complete pipeline runs end-to-end and the response
    # contains every top-level field defined in AssessmentResult.
    response = client.post("/assess", json=FULL_PROFILE)
    assert response.status_code == 200

    body = response.json()
    assert "life_cover_need" in body
    assert "health_cover_need" in body
    assert "accident_disability_need" in body
    assert "policy_audits" in body
    assert "action_plan" in body
    assert "explanation" in body
    assert "explanation_is_llm_generated" in body
    assert "disclaimer" in body

    # Disclaimer must always be present and non-empty (FR-5 / NFR-5)
    assert len(body["disclaimer"]) > 0

    # Two existing policies should produce two audit entries
    assert len(body["policy_audits"]) == 2


def test_assess_full_profile_numbers_are_sensible():
    # Verifies the engine produces non-trivial numbers for a realistic profile.
    # This is a sanity check, not an exact-value assertion — exact values are
    # covered in test_adequacy.py. Here we just confirm the API wires things up.
    response = client.post("/assess", json=FULL_PROFILE)
    body = response.json()

    life = body["life_cover_need"]
    # 35-year-old earning 18L with a non-earning spouse and 60L home loan
    # should have a gap (10 crore term exists, but recommended could exceed it)
    assert life["recommended_cover"] > 0
    assert life["existing_cover"] == 10_000_000

    health = body["health_cover_need"]
    # Tier-1 + spouse + child + parent → well above the 5L existing cover
    assert health["gap"] > 0


# ---------------------------------------------------------------------------
# 3. Minimal profile — single person, no optional fields
# ---------------------------------------------------------------------------


def test_assess_minimal_profile_returns_200():
    # Verifies the endpoint handles the simplest valid input correctly.
    # All optional fields (spouse, children, loans, policies) are omitted —
    # the engine must not crash when these lists are empty.
    response = client.post("/assess", json=MINIMAL_PROFILE)
    assert response.status_code == 200

    body = response.json()
    assert body["life_cover_need"]["existing_cover"] == 0
    assert body["health_cover_need"]["existing_cover"] == 0
    assert body["policy_audits"] == []


# ---------------------------------------------------------------------------
# 4. Invalid input — age below minimum
# ---------------------------------------------------------------------------


def test_assess_invalid_age_returns_422():
    # Verifies that Pydantic validation rejects out-of-range values before
    # the endpoint body executes. FastAPI handles this automatically via
    # the UserProfile schema (age field has ge=18).
    payload = {**MINIMAL_PROFILE, "age": 15}
    response = client.post("/assess", json=payload)
    assert response.status_code == 422

    # FastAPI returns field-level detail — confirm 'age' is mentioned
    errors = response.json()["detail"]
    assert any("age" in str(e).lower() for e in errors)


# ---------------------------------------------------------------------------
# 5. Missing required fields
# ---------------------------------------------------------------------------


def test_assess_missing_required_fields_returns_422():
    # Verifies that an empty body is rejected with a 422, not a 500.
    # FastAPI validates the request body against UserProfile before our
    # code runs, so missing required fields never reach service.assess().
    response = client.post("/assess", json={})
    assert response.status_code == 422
