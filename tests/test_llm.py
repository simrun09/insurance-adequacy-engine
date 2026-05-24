"""
tests/test_llm.py — Tests for the LLM explanation layer (llm.py).

Strategy: mock the Anthropic client so tests never make real API calls.
We test:
  - generate_explanation returns (str, True) when the mock LLM succeeds
  - generate_explanation returns (str, False) on missing API key (fallback path)
  - generate_explanation returns (str, False) when LLM raises any exception
  - The template output is genuinely useful: covers all three insurance areas,
    includes the disclaimer, and handles edge cases (zero gaps, beyond-budget items,
    investment policy findings)
  - _build_prompt includes the numbers, role definition, and hard constraints
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from engine.llm import _build_prompt, _generate_template_explanation, generate_explanation
from engine.schemas import (
    AccidentDisabilityNeed,
    ActionItem,
    ActionPlan,
    Child,
    CityTier,
    EfficiencyFlag,
    Gender,
    HealthCoverNeed,
    LifeCoverNeed,
    PolicyAudit,
    PolicyType,
    Spouse,
    TaxRegime,
    UserProfile,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def profile():
    return UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=18_00_000,
        monthly_expenses=50_000,
        monthly_insurance_budget=10_000,
        tax_regime=TaxRegime.NEW,
        spouse=Spouse(age=32, annual_income=0),
        children=[Child(age=5)],
    )


@pytest.fixture
def life_need():
    return LifeCoverNeed(
        hlv_based_cover=2_00_00_000,
        nba_based_cover=1_50_00_000,
        recommended_cover=2_00_00_000,
        existing_cover=50_00_000,
        gap=1_50_00_000,
        heuristic_10x_cover=1_80_00_000,
    )


@pytest.fixture
def health_need():
    return HealthCoverNeed(
        recommended_cover=25_00_000,
        existing_cover=5_00_000,
        gap=20_00_000,
        city_tier_floor=25_00_000,
        family_size_adjustment=5_00_000,
        age_adjustment=0,
    )


@pytest.fixture
def accident_need():
    return AccidentDisabilityNeed(
        recommended_accident_cover=15_00_000,
        existing_accident_cover=0,
        accident_gap=15_00_000,
        recommended_disability_cover=9_00_000,
        existing_disability_cover=0,
        disability_gap=9_00_000,
        disability_via_rider_suggested=True,
    )


@pytest.fixture
def action_plan_within_budget():
    item = ActionItem(
        policy_type=PolicyType.TERM,
        recommended_cover=1_50_00_000,
        estimated_monthly_premium=125.0,
        cumulative_premium=125.0,
        remaining_budget=9_875.0,
        priority_rank=1,
    )
    return ActionPlan(
        items_within_budget=[item],
        items_beyond_budget=[],
        total_monthly_premium_required=125.0,
        monthly_shortfall=0.0,
    )


@pytest.fixture
def action_plan_with_beyond(action_plan_within_budget, health_need):
    beyond_item = ActionItem(
        policy_type=PolicyType.HEALTH,
        recommended_cover=20_00_000,
        estimated_monthly_premium=1_667.0,
        cumulative_premium=1_792.0,
        remaining_budget=-1_667.0,
        priority_rank=2,
    )
    return ActionPlan(
        items_within_budget=action_plan_within_budget.items_within_budget,
        items_beyond_budget=[beyond_item],
        total_monthly_premium_required=1_792.0,
        monthly_shortfall=1_667.0,
    )


# ---------------------------------------------------------------------------
# generate_explanation — LLM path (mocked)
# ---------------------------------------------------------------------------

def test_generate_explanation_returns_llm_text_when_api_key_present(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="LLM-generated explanation text.")]

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"}):
        with patch("anthropic.Anthropic") as mock_client_cls:
            mock_client_cls.return_value.messages.create.return_value = mock_message
            text, used_llm = generate_explanation(
                profile, life_need, health_need, accident_need, [], action_plan_within_budget
            )

    assert used_llm is True
    assert text == "LLM-generated explanation text."


# used_llm flag is True only on the LLM path — False on template path
def test_generate_explanation_used_llm_flag_is_false_on_template_path(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        text, used_llm = generate_explanation(
            profile, life_need, health_need, accident_need, [], action_plan_within_budget
        )
    assert used_llm is False
    assert isinstance(text, str)
    assert len(text) > 0


# ---------------------------------------------------------------------------
# generate_explanation — fallback paths
# ---------------------------------------------------------------------------

# No API key → template path, used_llm=False
def test_generate_explanation_falls_back_when_no_api_key(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    env_without_key = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    with patch.dict(os.environ, env_without_key, clear=True):
        text, used_llm = generate_explanation(
            profile, life_need, health_need, accident_need, [], action_plan_within_budget
        )
    assert used_llm is False
    assert isinstance(text, str)


# LLM raises an exception → template path, used_llm=False (never crashes)
def test_generate_explanation_falls_back_on_llm_exception(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"}):
        with patch("anthropic.Anthropic") as mock_client_cls:
            mock_client_cls.return_value.messages.create.side_effect = RuntimeError("network error")
            text, used_llm = generate_explanation(
                profile, life_need, health_need, accident_need, [], action_plan_within_budget
            )
    assert used_llm is False
    assert isinstance(text, str)


# LLM returns empty string → template path, used_llm=False
def test_generate_explanation_falls_back_when_llm_returns_empty_string(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="   ")]

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"}):
        with patch("anthropic.Anthropic") as mock_client_cls:
            mock_client_cls.return_value.messages.create.return_value = mock_message
            text, used_llm = generate_explanation(
                profile, life_need, health_need, accident_need, [], action_plan_within_budget
            )
    assert used_llm is False


# ---------------------------------------------------------------------------
# _generate_template_explanation — structure and content
# ---------------------------------------------------------------------------

def test_template_contains_all_three_coverage_sections(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    text = _generate_template_explanation(
        profile, life_need, health_need, accident_need, [], action_plan_within_budget
    )
    assert "LIFE COVER" in text
    assert "HEALTH COVER" in text
    assert "ACCIDENT COVER" in text


def test_template_ends_with_disclaimer(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    text = _generate_template_explanation(
        profile, life_need, health_need, accident_need, [], action_plan_within_budget
    )
    assert "educational purposes only" in text
    assert "SEBI-registered" in text or "IRDAI" in text


def test_template_mentions_gap_amounts(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    text = _generate_template_explanation(
        profile, life_need, health_need, accident_need, [], action_plan_within_budget
    )
    # ₹1.5 crore life gap should appear
    assert "1.5 crore" in text


def test_template_includes_action_plan_section(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    text = _generate_template_explanation(
        profile, life_need, health_need, accident_need, [], action_plan_within_budget
    )
    assert "ACTION PLAN" in text


# Zero gaps → "no action needed" language, no gap amounts
def test_template_handles_zero_gaps(profile, action_plan_within_budget):
    life_adequate = LifeCoverNeed(
        hlv_based_cover=2_00_00_000, nba_based_cover=1_50_00_000,
        recommended_cover=2_00_00_000, existing_cover=2_00_00_000,
        gap=0, heuristic_10x_cover=1_80_00_000,
    )
    health_adequate = HealthCoverNeed(
        recommended_cover=25_00_000, existing_cover=25_00_000,
        gap=0, city_tier_floor=25_00_000,
        family_size_adjustment=0, age_adjustment=0,
    )
    accident_adequate = AccidentDisabilityNeed(
        recommended_accident_cover=15_00_000, existing_accident_cover=15_00_000,
        accident_gap=0,
        recommended_disability_cover=9_00_000, existing_disability_cover=9_00_000,
        disability_gap=0, disability_via_rider_suggested=True,
    )
    empty_plan = ActionPlan(
        items_within_budget=[], items_beyond_budget=[],
        total_monthly_premium_required=0.0, monthly_shortfall=0.0,
    )
    text = _generate_template_explanation(
        profile, life_adequate, health_adequate, accident_adequate, [], empty_plan
    )
    assert "adequate" in text.lower() or "meets" in text.lower()
    assert "All your coverage gaps are already closed" in text


# Beyond-budget items appear with shortfall amount
def test_template_shows_beyond_budget_items_and_shortfall(
    profile, life_need, health_need, accident_need, action_plan_with_beyond
):
    text = _generate_template_explanation(
        profile, life_need, health_need, accident_need, [], action_plan_with_beyond
    )
    assert "beyond" in text.lower() or "larger budget" in text.lower()
    assert "shortfall" in text.lower() or "additional" in text.lower()


# Investment policy audit section appears when ULIP/endowment with efficiency flag present
def test_template_shows_policy_review_section_for_inefficient_ulip(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    inefficient_audit = PolicyAudit(
        policy_type=PolicyType.ULIP,
        sum_assured=10_00_000,
        is_adequate=False,
        adequacy_gap=1_90_00_000,
        efficiency_flag=EfficiencyFlag.INEFFICIENT,
        implied_irr=0.045,
        opportunity_cost=15_00_000,
        recommendation="Implied IRR of 4.5% is below 7% — lags a term + index fund alternative.",
    )
    text = _generate_template_explanation(
        profile, life_need, health_need, accident_need,
        [inefficient_audit], action_plan_within_budget
    )
    assert "EXISTING POLICY REVIEW" in text
    assert "4.5%" in text


# No investment policies → no policy review section
def test_template_omits_policy_review_when_no_investment_policies(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    term_audit = PolicyAudit(
        policy_type=PolicyType.TERM,
        sum_assured=50_00_000,
        is_adequate=False,
        adequacy_gap=1_50_00_000,
        efficiency_flag=None,
        implied_irr=None,
        opportunity_cost=None,
        recommendation="Coverage gap.",
    )
    text = _generate_template_explanation(
        profile, life_need, health_need, accident_need,
        [term_audit], action_plan_within_budget
    )
    assert "EXISTING POLICY REVIEW" not in text


# ---------------------------------------------------------------------------
# _build_prompt — content checks
# ---------------------------------------------------------------------------

def test_build_prompt_contains_user_situation_numbers(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    prompt = _build_prompt(
        profile, life_need, health_need, accident_need, [], action_plan_within_budget
    )
    assert "18" in prompt          # age
    assert "TIER-1" in prompt      # city tier
    assert "1.5 crore" in prompt   # life gap


def test_build_prompt_contains_role_definition(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    prompt = _build_prompt(
        profile, life_need, health_need, accident_need, [], action_plan_within_budget
    )
    assert "financial educator" in prompt.lower()


def test_build_prompt_contains_hard_constraints(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    prompt = _build_prompt(
        profile, life_need, health_need, accident_need, [], action_plan_within_budget
    )
    # Must tell LLM not to recommend specific products and not to contradict numbers
    assert "Never name specific" in prompt or "Never recommend" in prompt or "never" in prompt.lower()
    assert "300 words" in prompt


def test_build_prompt_includes_disclaimer_instruction(
    profile, life_need, health_need, accident_need, action_plan_within_budget
):
    prompt = _build_prompt(
        profile, life_need, health_need, accident_need, [], action_plan_within_budget
    )
    assert "disclaimer" in prompt.lower() or "educational purposes" in prompt.lower()
