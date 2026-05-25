"""
Tax-regime-aware premium adjustment for the Insurance Adequacy Engine.

Implements FR-5: old-regime users benefit from Section 80C/80D deductions
that reduce the effective cost of insurance premiums. New-regime users
(the default post FY2024-25) receive no such benefit.
"""

from dataclasses import dataclass

from . import config
from .schemas import TaxRegime, UserProfile


@dataclass
class TaxAdjustment:
    """Result of adjusting a nominal premium for the user's tax regime."""

    nominal_annual_premium: float
    effective_annual_premium: float  # after tax saving; equals nominal under new regime
    tax_saving: float  # rupee benefit from deductions; 0 under new regime
    marginal_tax_rate: float  # 0.0 under new regime; slab rate under old regime


def _marginal_rate_old_regime(annual_income: float) -> float:
    """
    Look up the marginal income tax rate under the old regime.

    Iterates config.OLD_REGIME_SLABS (ordered, with float('inf') ceiling)
    and returns the rate for the first slab ceiling the income falls below.
    Source: Income Tax Act, 1961 (Finance Act 2024 slabs).
    """
    for ceiling, rate in config.OLD_REGIME_SLABS:
        if annual_income <= ceiling:
            return rate
    return config.OLD_REGIME_SLABS[-1][1]  # fallback: top slab


def adjust_for_regime(profile: UserProfile, nominal_premium: float) -> TaxAdjustment:
    """
    Compute the effective cost of an insurance premium after tax regime adjustment.

    New regime: no deductions apply — effective premium equals nominal premium.
    Old regime: premium is partially offset by 80C/80D deductions at the user's
    marginal rate, so effective premium = nominal × (1 - marginal_rate).

    The tax saving is a rupee figure, not a recommendation — it helps users
    understand the real cost difference between regimes. (FR-5)
    """
    if profile.tax_regime == TaxRegime.NEW:
        return TaxAdjustment(
            nominal_annual_premium=nominal_premium,
            effective_annual_premium=nominal_premium,
            tax_saving=0.0,
            marginal_tax_rate=0.0,
        )

    rate = _marginal_rate_old_regime(profile.annual_income)
    effective = nominal_premium * (1 - rate)
    return TaxAdjustment(
        nominal_annual_premium=nominal_premium,
        effective_annual_premium=round(effective, 2),
        tax_saving=round(nominal_premium - effective, 2),
        marginal_tax_rate=rate,
    )
