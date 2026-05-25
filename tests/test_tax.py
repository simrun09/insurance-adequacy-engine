import pytest

from engine.schemas import CityTier, Gender, TaxRegime, UserProfile
from engine.tax import TaxAdjustment, _marginal_rate_old_regime, adjust_for_regime


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------


def make_profile(annual_income: float, regime: TaxRegime) -> UserProfile:
    return UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=annual_income,
        monthly_expenses=30_000,
        monthly_insurance_budget=10_000,
        tax_regime=regime,
    )


# ---------------------------------------------------------------------------
# _marginal_rate_old_regime — slab boundary tests
# ---------------------------------------------------------------------------


# Income at exactly the 2.5L ceiling falls in the 0% slab
def test_marginal_rate_at_250000_is_zero():
    assert _marginal_rate_old_regime(250_000) == 0.0


# Income just above 2.5L falls in the 5% slab
def test_marginal_rate_just_above_250000_is_five_percent():
    assert _marginal_rate_old_regime(250_001) == pytest.approx(0.05)


# Income at exactly 5L ceiling falls in the 5% slab
def test_marginal_rate_at_500000_is_five_percent():
    assert _marginal_rate_old_regime(500_000) == pytest.approx(0.05)


# Income just above 5L falls in the 20% slab
def test_marginal_rate_just_above_500000_is_twenty_percent():
    assert _marginal_rate_old_regime(500_001) == pytest.approx(0.20)


# Income at exactly 10L ceiling falls in the 20% slab
def test_marginal_rate_at_1000000_is_twenty_percent():
    assert _marginal_rate_old_regime(1_000_000) == pytest.approx(0.20)


# Income above 10L falls in the 30% top slab
def test_marginal_rate_above_1000000_is_thirty_percent():
    assert _marginal_rate_old_regime(1_000_001) == pytest.approx(0.30)


# Very high income (senior executive) still lands in top slab
def test_marginal_rate_high_income_is_thirty_percent():
    assert _marginal_rate_old_regime(10_000_000) == pytest.approx(0.30)


# Zero income falls in nil slab
def test_marginal_rate_zero_income_is_zero():
    assert _marginal_rate_old_regime(0) == 0.0


# ---------------------------------------------------------------------------
# adjust_for_regime — new regime
# ---------------------------------------------------------------------------


# New-regime user: effective premium equals nominal, no tax saving
def test_new_regime_effective_equals_nominal():
    profile = make_profile(1_200_000, TaxRegime.NEW)
    result = adjust_for_regime(profile, 12_000)
    assert result.effective_annual_premium == 12_000
    assert result.tax_saving == 0.0
    assert result.marginal_tax_rate == 0.0


# New-regime result is a TaxAdjustment dataclass
def test_new_regime_returns_tax_adjustment_instance():
    profile = make_profile(1_200_000, TaxRegime.NEW)
    result = adjust_for_regime(profile, 12_000)
    assert isinstance(result, TaxAdjustment)


# New-regime: nominal is preserved in the output
def test_new_regime_nominal_preserved():
    profile = make_profile(800_000, TaxRegime.NEW)
    result = adjust_for_regime(profile, 8_000)
    assert result.nominal_annual_premium == 8_000


# New regime: zero premium → all fields are zero
def test_new_regime_zero_premium():
    profile = make_profile(1_200_000, TaxRegime.NEW)
    result = adjust_for_regime(profile, 0)
    assert result.effective_annual_premium == 0.0
    assert result.tax_saving == 0.0


# ---------------------------------------------------------------------------
# adjust_for_regime — old regime, nil slab (income ≤ 2.5L)
# ---------------------------------------------------------------------------


# Old regime, income ≤ 2.5L → 0% rate → no tax benefit even with deductions
def test_old_regime_nil_slab_no_saving():
    profile = make_profile(200_000, TaxRegime.OLD)
    result = adjust_for_regime(profile, 10_000)
    assert result.marginal_tax_rate == 0.0
    assert result.tax_saving == 0.0
    assert result.effective_annual_premium == 10_000


# ---------------------------------------------------------------------------
# adjust_for_regime — old regime, 5% slab
# ---------------------------------------------------------------------------


# Old regime, income in 5% slab → effective = nominal × 0.95
def test_old_regime_five_percent_slab_effective_premium():
    profile = make_profile(400_000, TaxRegime.OLD)
    result = adjust_for_regime(profile, 10_000)
    assert result.marginal_tax_rate == pytest.approx(0.05)
    assert result.effective_annual_premium == pytest.approx(9_500)
    assert result.tax_saving == pytest.approx(500)


# ---------------------------------------------------------------------------
# adjust_for_regime — old regime, 20% slab
# ---------------------------------------------------------------------------


# Old regime, 8L income → 20% slab → effective = nominal × 0.80
def test_old_regime_twenty_percent_slab_effective_premium():
    profile = make_profile(800_000, TaxRegime.OLD)
    result = adjust_for_regime(profile, 12_000)
    assert result.marginal_tax_rate == pytest.approx(0.20)
    assert result.effective_annual_premium == pytest.approx(9_600)
    assert result.tax_saving == pytest.approx(2_400)


# ---------------------------------------------------------------------------
# adjust_for_regime — old regime, 30% slab
# ---------------------------------------------------------------------------


# Old regime, 15L income → 30% slab → effective = nominal × 0.70
def test_old_regime_thirty_percent_slab_effective_premium():
    profile = make_profile(1_500_000, TaxRegime.OLD)
    result = adjust_for_regime(profile, 12_000)
    assert result.marginal_tax_rate == pytest.approx(0.30)
    assert result.effective_annual_premium == pytest.approx(8_400)
    assert result.tax_saving == pytest.approx(3_600)


# ---------------------------------------------------------------------------
# adjust_for_regime — consistency and invariants
# ---------------------------------------------------------------------------


# effective + tax_saving must always equal nominal (no money created or lost)
def test_effective_plus_saving_equals_nominal_old_regime():
    profile = make_profile(1_200_000, TaxRegime.OLD)
    result = adjust_for_regime(profile, 15_000)
    assert result.effective_annual_premium + result.tax_saving == pytest.approx(
        result.nominal_annual_premium
    )


# Same invariant holds for new regime
def test_effective_plus_saving_equals_nominal_new_regime():
    profile = make_profile(1_200_000, TaxRegime.NEW)
    result = adjust_for_regime(profile, 15_000)
    assert result.effective_annual_premium + result.tax_saving == pytest.approx(
        result.nominal_annual_premium
    )


# Old-regime user always pays less (or equal) than new-regime user for same premium
def test_old_regime_effective_lte_new_regime_effective():
    premium = 20_000
    old = adjust_for_regime(make_profile(1_200_000, TaxRegime.OLD), premium)
    new = adjust_for_regime(make_profile(1_200_000, TaxRegime.NEW), premium)
    assert old.effective_annual_premium <= new.effective_annual_premium


# Higher income in old regime means higher tax rate means more saving (monotonicity)
def test_old_regime_higher_income_more_saving():
    low = adjust_for_regime(make_profile(400_000, TaxRegime.OLD), 12_000)  # 5% slab
    high = adjust_for_regime(make_profile(1_500_000, TaxRegime.OLD), 12_000)  # 30% slab
    assert high.tax_saving > low.tax_saving
