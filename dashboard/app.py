"""
dashboard/app.py — Streamlit dashboard for the Insurance Adequacy Engine.

Approach C: smart defaults with progressive disclosure via expanders.
Calls the FastAPI backend (POST /assess) over HTTP — does NOT import engine
modules directly. This proves the layered architecture is working correctly.
"""

import requests
import streamlit as st

API_URL = "http://localhost:8000/assess"

st.set_page_config(
    page_title="Insurance Adequacy Engine",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Mapping tables (module level so the API-call block can access them) ───────

_GENDER_MAP = {"Male": "male", "Female": "female", "Other": "other"}

_CITY_MAP = {
    "Metro (Delhi, Mumbai, Bengaluru, Chennai, Kolkata, Hyderabad)": "tier_1",
    "Tier 2 city": "tier_2",
    "Tier 3 city / Town": "tier_3",
}

_TAX_MAP = {
    "New  (default since FY 2024-25 — no 80C/80D benefit)": "new",
    "Old  (with 80C / 80D deductions)": "old",
}

_POLICY_OPTIONS = [
    "Term Life",
    "Health / Mediclaim",
    "Personal Accident",
    "Disability",
    "Endowment / Money-back",
    "ULIP",
]
_POLICY_API_KEY = {
    "Term Life": "term",
    "Health / Mediclaim": "health",
    "Personal Accident": "accident",
    "Disability": "disability",
    "Endowment / Money-back": "endowment",
    "ULIP": "ulip",
}
_POLICY_DISPLAY = {
    "term": "Term Life",
    "health": "Health / Mediclaim",
    "accident": "Personal Accident",
    "disability": "Disability",
    "endowment": "Endowment",
    "ulip": "ULIP",
}
_PLAN_DISPLAY = {
    "term": "Term Life Insurance",
    "health": "Health / Mediclaim Policy",
    "accident": "Personal Accident Cover",
    "disability": "Disability Cover (rider on term policy)",
    "endowment": "Endowment Policy",
    "ulip": "ULIP",
}
_EFF_ICON = {"efficient": "✅", "mixed": "⚠️", "inefficient": "❌"}


# ── Helpers ───────────────────────────────────────────────────────────────────


def fmt_inr(amount: float) -> str:
    """Format a rupee amount in Indian notation (lakhs / crores)."""
    if amount >= 1_00_00_000:
        return f"₹{amount / 1_00_00_000:.1f} Cr"
    if amount >= 1_00_000:
        return f"₹{amount / 1_00_000:.1f} L"
    if amount > 0:
        return f"₹{int(amount):,}"
    return "₹0"


def _init_session() -> None:
    defaults: dict = {
        "children": [],
        "parents": [],
        "loans": [],
        "policies": [],
        "result": None,
        "error": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_session()

# ── Page header ───────────────────────────────────────────────────────────────

st.title("🛡️ Insurance Adequacy Engine")
st.caption(
    "Find your coverage gaps, audit your existing policies, and get a "
    "budget-constrained action plan — explained in plain English."
)

# ── Sidebar: input form ───────────────────────────────────────────────────────

with st.sidebar:
    st.header("Your Profile")
    st.caption("Fill in your details, then click Analyze.")

    # Core fields — always visible
    age = st.number_input("Age", min_value=18, max_value=80, value=32, step=1)

    gender = st.selectbox("Gender", ["Male", "Female", "Other"])

    city_tier = st.selectbox(
        "Your city",
        list(_CITY_MAP.keys()),
    )

    annual_income = st.number_input(
        "Annual income (₹)",
        min_value=0,
        value=1_500_000,
        step=50_000,
        help="Your gross annual income before tax",
    )

    monthly_expenses = st.number_input(
        "Monthly personal expenses (₹)",
        min_value=0,
        value=45_000,
        step=1_000,
        help="Your own living costs — not including dependents",
    )

    monthly_budget = st.number_input(
        "Monthly insurance budget (₹)",
        min_value=0,
        value=5_000,
        step=500,
        help="The most you can spend on premiums every month",
    )

    tax_regime = st.selectbox(
        "Tax regime",
        list(_TAX_MAP.keys()),
        help=(
            "New regime (default since FY 2024-25): no 80C/80D deductions — "
            "premiums don't reduce your tax bill. "
            "Old regime: life and health premiums can cut your taxable income."
        ),
    )

    st.divider()

    # ── Expander: spouse ──────────────────────────────────────────────────────
    # Variables must be initialized before the expander in case it's collapsed.
    has_spouse = False
    spouse_age: int | None = None
    spouse_income: float | None = None

    with st.expander("Add spouse / partner details"):
        has_spouse = st.checkbox("I have a spouse or partner", key="has_spouse_chk")
        if has_spouse:
            c1, c2 = st.columns(2)
            with c1:
                spouse_age = st.number_input(
                    "Spouse's age", min_value=18, max_value=80, value=29, key="sp_age"
                )
            with c2:
                spouse_income = st.number_input(
                    "Spouse's annual income (₹)",
                    min_value=0,
                    value=0,
                    step=50_000,
                    key="sp_inc",
                    help="Enter 0 if not earning",
                )

    # ── Expander: children ────────────────────────────────────────────────────
    with st.expander(f"Add children  ·  {len(st.session_state.children)} added"):
        if st.button("＋ Add a child", key="add_child_btn"):
            st.session_state.children.append({"age": 5, "edu": 0, "marriage": 0})
            st.rerun()

        to_remove: int | None = None
        for i, child in enumerate(st.session_state.children):
            st.markdown(f"**Child {i + 1}**")
            c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
            with c1:
                child["age"] = st.number_input(
                    "Age",
                    min_value=0,
                    max_value=25,
                    value=child["age"],
                    key=f"ch_age_{i}",
                )
            with c2:
                child["edu"] = st.number_input(
                    "Education fund target (₹)",
                    min_value=0,
                    value=child["edu"],
                    step=1_00_000,
                    key=f"ch_edu_{i}",
                    help="Estimated cost of college / higher education",
                )
            with c3:
                child["marriage"] = st.number_input(
                    "Marriage estimate (₹)",
                    min_value=0,
                    value=child["marriage"],
                    step=1_00_000,
                    key=f"ch_mar_{i}",
                )
            with c4:
                st.write("")
                st.write("")
                if st.button("✕", key=f"rm_ch_{i}", help="Remove"):
                    to_remove = i
        if to_remove is not None:
            st.session_state.children.pop(to_remove)
            st.rerun()

    # ── Expander: dependent parents ───────────────────────────────────────────
    with st.expander(
        f"Add dependent parents  ·  {len(st.session_state.parents)} added"
    ):
        if st.button("＋ Add a parent", key="add_parent_btn"):
            st.session_state.parents.append({"age": 62, "own_cover": False})
            st.rerun()

        to_remove = None
        for i, parent in enumerate(st.session_state.parents):
            st.markdown(f"**Parent {i + 1}**")
            c1, c2, c3 = st.columns([2, 3, 1])
            with c1:
                parent["age"] = st.number_input(
                    "Age",
                    min_value=40,
                    max_value=100,
                    value=parent["age"],
                    key=f"par_age_{i}",
                )
            with c2:
                parent["own_cover"] = st.checkbox(
                    "Has their own health policy",
                    value=parent["own_cover"],
                    key=f"par_cov_{i}",
                    help="If yes, we exclude them from your health gap calculation",
                )
            with c3:
                st.write("")
                st.write("")
                if st.button("✕", key=f"rm_par_{i}", help="Remove"):
                    to_remove = i
        if to_remove is not None:
            st.session_state.parents.pop(to_remove)
            st.rerun()

    # ── Expander: loans ───────────────────────────────────────────────────────
    with st.expander(f"Add loans  ·  {len(st.session_state.loans)} added"):
        if st.button("＋ Add a loan", key="add_loan_btn"):
            st.session_state.loans.append(
                {"type": "Home Loan", "balance": 0, "tenure": 10}
            )
            st.rerun()

        to_remove = None
        for i, loan in enumerate(st.session_state.loans):
            st.markdown(f"**Loan {i + 1}**")
            loan["type"] = st.text_input(
                "Loan type",
                value=loan["type"],
                key=f"ln_type_{i}",
                placeholder="Home Loan / Car Loan / Personal Loan",
            )
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                loan["balance"] = st.number_input(
                    "Outstanding balance (₹)",
                    min_value=0,
                    value=loan["balance"],
                    step=1_00_000,
                    key=f"ln_bal_{i}",
                )
            with c2:
                loan["tenure"] = st.number_input(
                    "Years remaining",
                    min_value=0,
                    max_value=30,
                    value=loan["tenure"],
                    key=f"ln_ten_{i}",
                )
            with c3:
                st.write("")
                st.write("")
                if st.button("✕", key=f"rm_ln_{i}", help="Remove"):
                    to_remove = i
        if to_remove is not None:
            st.session_state.loans.pop(to_remove)
            st.rerun()

    # ── Expander: existing policies ───────────────────────────────────────────
    with st.expander(
        f"Add existing policies  ·  {len(st.session_state.policies)} added"
    ):
        if st.button("＋ Add a policy", key="add_pol_btn"):
            st.session_state.policies.append(
                {
                    "label": "Term Life",
                    "sum_assured": 0,
                    "premium": 0,
                    "start_year": 2020,
                    "maturity_year": 2040,
                    "maturity_value": 0,
                }
            )
            st.rerun()

        to_remove = None
        for i, pol in enumerate(st.session_state.policies):
            st.markdown(f"**Policy {i + 1}**")
            idx = _POLICY_OPTIONS.index(pol.get("label", "Term Life"))
            pol["label"] = st.selectbox(
                "Policy type", _POLICY_OPTIONS, index=idx, key=f"pol_lbl_{i}"
            )
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                pol["sum_assured"] = st.number_input(
                    "Sum assured (₹)",
                    min_value=0,
                    value=pol["sum_assured"],
                    step=1_00_000,
                    key=f"pol_sa_{i}",
                )
            with c2:
                pol["premium"] = st.number_input(
                    "Annual premium (₹)",
                    min_value=0,
                    value=pol["premium"],
                    step=1_000,
                    key=f"pol_prem_{i}",
                )
            with c3:
                st.write("")
                st.write("")
                if st.button("✕", key=f"rm_pol_{i}", help="Remove"):
                    to_remove = i

            pol["start_year"] = st.number_input(
                "Year you bought it",
                min_value=1980,
                max_value=2025,
                value=pol["start_year"],
                key=f"pol_yr_{i}",
            )

            if pol["label"] in ("Endowment / Money-back", "ULIP"):
                st.caption(
                    "We'll check whether this investment-linked policy is earning "
                    "enough compared to buying plain term cover and investing the "
                    "difference in an index fund."
                )
                c1, c2 = st.columns(2)
                with c1:
                    pol["maturity_year"] = st.number_input(
                        "Maturity year",
                        min_value=2025,
                        max_value=2060,
                        value=pol.get("maturity_year") or 2040,
                        key=f"pol_mat_yr_{i}",
                    )
                with c2:
                    pol["maturity_value"] = st.number_input(
                        "Expected payout at maturity (₹)",
                        min_value=0,
                        value=pol.get("maturity_value") or 0,
                        step=1_00_000,
                        key=f"pol_mat_val_{i}",
                    )

            st.divider()

        if to_remove is not None:
            st.session_state.policies.pop(to_remove)
            st.rerun()

    # ── Expander: assets ──────────────────────────────────────────────────────
    with st.expander("Add existing assets  ·  optional"):
        investable_assets = st.number_input(
            "Investable assets (₹)",
            min_value=0,
            value=0,
            step=1_00_000,
            help="Savings, FDs, mutual funds, stocks — anything you could access",
        )
        epf_ppf = st.number_input(
            "EPF / PPF balance (₹)",
            min_value=0,
            value=0,
            step=50_000,
            help="Provident fund corpus (counted separately — illiquid and withdrawal-restricted)",
        )

    st.divider()

    analyze_clicked = st.button(
        "🔍 Analyze My Protection",
        type="primary",
        use_container_width=True,
    )


# ── Build payload and call API ────────────────────────────────────────────────

if analyze_clicked:
    payload: dict = {
        "age": int(age),
        "gender": _GENDER_MAP[gender],
        "city_tier": _CITY_MAP[city_tier],
        "annual_income": float(annual_income),
        "monthly_expenses": float(monthly_expenses),
        "monthly_insurance_budget": float(monthly_budget),
        "tax_regime": _TAX_MAP[tax_regime],
        "spouse": (
            {"age": int(spouse_age), "annual_income": float(spouse_income)}
            if has_spouse and spouse_age is not None and spouse_income is not None
            else None
        ),
        "children": [
            {
                "age": int(c["age"]),
                "education_cost_estimate": float(c["edu"]),
                "marriage_cost_estimate": float(c["marriage"]),
            }
            for c in st.session_state.children
        ],
        "dependent_parents": [
            {
                "age": int(p["age"]),
                "has_own_health_cover": bool(p["own_cover"]),
            }
            for p in st.session_state.parents
        ],
        "loans": [
            {
                "loan_type": ln["type"],
                "outstanding_balance": float(ln["balance"]),
                "remaining_tenure_years": int(ln["tenure"]),
            }
            for ln in st.session_state.loans
        ],
        "future_expenses": [],
        "investable_assets": float(investable_assets),
        "epf_ppf_balance": float(epf_ppf),
        "existing_policies": [
            {
                "policy_type": _POLICY_API_KEY[pol["label"]],
                "sum_assured": float(pol["sum_assured"]),
                "annual_premium": float(pol["premium"]),
                "start_year": int(pol["start_year"]),
                "maturity_year": (
                    int(pol["maturity_year"])
                    if pol["label"] in ("Endowment / Money-back", "ULIP")
                    else None
                ),
                "maturity_value": (
                    float(pol["maturity_value"])
                    if pol["label"] in ("Endowment / Money-back", "ULIP")
                    else None
                ),
            }
            for pol in st.session_state.policies
        ],
    }

    with st.spinner("Analyzing your protection…"):
        try:
            resp = requests.post(API_URL, json=payload, timeout=30)
            if resp.status_code == 200:
                st.session_state.result = resp.json()
                st.session_state.error = None
            else:
                st.session_state.result = None
                detail = resp.json().get("detail", f"HTTP {resp.status_code}")
                st.session_state.error = f"Assessment failed: {detail}"
        except requests.ConnectionError:
            st.session_state.result = None
            st.session_state.error = (
                "Cannot reach the API server at **http://localhost:8000**.\n\n"
                "Please start it in a separate terminal:\n\n"
                "```\nuvicorn src.engine.api:app --reload --port 8000\n```"
            )
        except requests.Timeout:
            st.session_state.result = None
            st.session_state.error = (
                "The server took too long to respond. Please try again."
            )
        except Exception as exc:  # noqa: BLE001
            st.session_state.result = None
            st.session_state.error = f"Unexpected error: {exc}"


# ── Main content ──────────────────────────────────────────────────────────────

if st.session_state.get("error"):
    st.error(st.session_state.error)

elif st.session_state.get("result") is None:
    # Welcome / empty state
    st.info(
        "👈 Fill in your details in the sidebar and click "
        "**🔍 Analyze My Protection** to get started."
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(
        "### 📊\nCoverage gap analysis across life, health, accident, and disability"
    )
    c2.markdown(
        "### 🔍\nAudit of your existing policies — including ULIP / endowment traps"
    )
    c3.markdown("### 📋\nPrioritized action plan that fits your monthly budget")
    c4.markdown("### 💬\nPlain-English explanation — no jargon, no upselling")

else:
    result: dict = st.session_state.result

    # ── A: Gap overview ───────────────────────────────────────────────────────
    st.header("📊 Your Coverage at a Glance")

    def _gap_row(label: str, existing: float, recommended: float, gap: float) -> None:
        ratio = min(existing / recommended, 1.0) if recommended > 0 else 1.0
        pct = int(ratio * 100)
        if gap == 0:
            status = ":green[Fully covered ✓]"
        elif ratio >= 0.5:
            status = f":orange[{pct}% covered]"
        else:
            status = f":red[{pct}% covered — large gap]"

        col_lbl, col_bar, col_nums = st.columns([1, 3, 3])
        with col_lbl:
            st.markdown(f"**{label}**")
        with col_bar:
            st.progress(ratio, text=status)
        with col_nums:
            if gap > 0:
                st.markdown(
                    f"{fmt_inr(existing)} covered &nbsp;·&nbsp; "
                    f"Need **{fmt_inr(recommended)}** &nbsp;·&nbsp; "
                    f":red[Gap: **{fmt_inr(gap)}**]"
                )
            else:
                st.markdown(
                    f"{fmt_inr(existing)} covered &nbsp;·&nbsp; "
                    f"Need {fmt_inr(recommended)}"
                )

    life = result["life_cover_need"]
    health = result["health_cover_need"]
    acc = result["accident_disability_need"]

    _gap_row("Life", life["existing_cover"], life["recommended_cover"], life["gap"])
    _gap_row(
        "Health", health["existing_cover"], health["recommended_cover"], health["gap"]
    )
    _gap_row(
        "Accident",
        acc["existing_accident_cover"],
        acc["recommended_accident_cover"],
        acc["accident_gap"],
    )
    _gap_row(
        "Disability",
        acc["existing_disability_cover"],
        acc["recommended_disability_cover"],
        acc["disability_gap"],
    )

    with st.expander("How is your life cover need calculated?"):
        c1, c2, c3 = st.columns(3)
        c1.metric(
            "HLV — income replacement method",
            fmt_inr(life["hlv_based_cover"]),
            help="Present value of income your family would lose if you weren't around",
        )
        c2.metric(
            "NBA — needs-based method",
            fmt_inr(life["nba_based_cover"]),
            help="Loans + future obligations + emergency corpus − your existing assets",
        )
        c3.metric(
            "Recommended (higher of the two)",
            fmt_inr(life["recommended_cover"]),
        )
        st.caption(
            f"For comparison, the common '10× income' heuristic gives "
            f"**{fmt_inr(life['heuristic_10x_cover'])}** — "
            "which may significantly overstate or understate your actual need depending "
            "on your outstanding loans and obligations."
        )

    # ── B: Policy audit ───────────────────────────────────────────────────────
    audits: list = result.get("policy_audits", [])
    if audits:
        st.header("🔍 Your Existing Policies")
        st.caption(
            "We've checked whether each policy gives you adequate cover, "
            "and — for investment-linked ones — whether it's earning a fair return."
        )

        for audit in audits:
            pol_label = _POLICY_DISPLAY.get(
                audit["policy_type"], audit["policy_type"].title()
            )
            eff = audit.get("efficiency_flag")
            eff_icon = _EFF_ICON.get(eff, "")
            adequacy_icon = "✅" if audit["is_adequate"] else "⚠️"

            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 4])
                with c1:
                    st.markdown(f"**{pol_label}** {eff_icon}")
                    st.caption(f"Sum assured: {fmt_inr(audit['sum_assured'])}")
                with c2:
                    verdict = "Adequate" if audit["is_adequate"] else "Not enough"
                    st.markdown(f"{adequacy_icon} {verdict}")
                    if audit["adequacy_gap"] > 0:
                        st.caption(f"Shortfall: {fmt_inr(audit['adequacy_gap'])}")
                with c3:
                    st.caption(audit["recommendation"])
                    if audit.get("implied_irr") is not None:
                        irr: float = audit["implied_irr"]
                        opp: float = audit.get("opportunity_cost") or 0.0
                        irr_color = (
                            "green" if irr >= 8 else ("orange" if irr >= 5 else "red")
                        )
                        st.caption(
                            f"Implied return: :{irr_color}[**{irr:.1f}% per year**]  ·  "
                            f"What you're giving up vs term + index fund: "
                            f"**{fmt_inr(opp)}**"
                        )

    # ── C: Action plan ────────────────────────────────────────────────────────
    st.header("📋 Your Action Plan")
    st.caption("Ordered by priority — most urgent gap first.")

    plan: dict = result["action_plan"]
    within: list = plan["items_within_budget"]
    beyond: list = plan["items_beyond_budget"]

    if within:
        st.subheader("✅ Within your monthly budget")
        for item in within:
            label = _PLAN_DISPLAY.get(item["policy_type"], item["policy_type"].title())
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                c1.markdown(f"**{item['priority_rank']}. {label}**")
                c2.metric("Cover", fmt_inr(item["recommended_cover"]))
                c3.metric(
                    "~Monthly premium", fmt_inr(item["estimated_monthly_premium"])
                )
                c4.metric(
                    "Budget left after", fmt_inr(max(item["remaining_budget"], 0))
                )

    if beyond:
        st.subheader("⛔ Beyond your current budget")
        st.caption(
            "These gaps remain open. Consider addressing them when your budget allows, "
            "or look for riders that combine protection more efficiently."
        )
        for item in beyond:
            label = _PLAN_DISPLAY.get(item["policy_type"], item["policy_type"].title())
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.markdown(f"**{item['priority_rank']}. {label}**")
                c2.metric("Cover needed", fmt_inr(item["recommended_cover"]))
                c3.metric(
                    "~Monthly premium", fmt_inr(item["estimated_monthly_premium"])
                )

    if not within and not beyond:
        st.success(
            "🎉 No coverage gaps detected. Your existing policies appear adequate."
        )
    elif plan["monthly_shortfall"] > 0:
        st.warning(
            f"To close **all** gaps you need an additional "
            f"**{fmt_inr(plan['monthly_shortfall'])}/month** beyond your current budget  "
            f"(total required: **{fmt_inr(plan['total_monthly_premium_required'])}/month**)."
        )
    else:
        st.success(
            f"All recommended coverage fits within your budget.  "
            f"Total monthly premium: **{fmt_inr(plan['total_monthly_premium_required'])}**."
        )

    # ── D: Explanation ────────────────────────────────────────────────────────
    st.header("💬 What This Means For You")

    explanation: str = result.get("explanation", "")
    is_llm: bool = result.get("explanation_is_llm_generated", False)

    st.info(explanation)
    st.caption(
        "✨ AI-generated, personalized explanation"
        if is_llm
        else "📝 Template summary (AI explanation unavailable — results are still accurate)"
    )

    # ── E: Disclaimer ─────────────────────────────────────────────────────────
    st.divider()
    disclaimer: str = result.get("disclaimer", "")
    if disclaimer:
        st.caption(f"⚠️  {disclaimer}")
