from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from analystforge.quant.multiples import (
    MultipleInputs,
    MultipleUnit,
    compute_multiples,
    implied_enterprise_value,
    implied_equity_value,
    implied_share_price,
    peer_statistics,
)
from analystforge.quant.statements import FinancialStatements, LineItem

D = Decimal

EXPECTED_KEYS = {
    "market_cap",
    "enterprise_value",
    "price_to_earnings",
    "earnings_yield",
    "price_to_book",
    "price_to_sales",
    "ev_to_ebitda",
    "ev_to_ebit",
    "ev_to_sales",
    "ev_to_free_cash_flow",
    "price_to_free_cash_flow",
    "free_cash_flow_yield",
}


def _without_income(statements: FinancialStatements, line: LineItem) -> FinancialStatements:
    values = dict(statements.income.values)
    values.pop(line, None)
    return FinancialStatements(
        income=replace(statements.income, values=values),
        balance=statements.balance,
        cashflow=statements.cashflow,
    )


def _with_income(statements: FinancialStatements, **changes: Decimal) -> FinancialStatements:
    values = dict(statements.income.values)
    values.update(changes)
    return FinancialStatements(
        income=replace(statements.income, values=values),
        balance=statements.balance,
        cashflow=statements.cashflow,
    )


def test_reference_company_multiples(reference) -> None:
    multiples = compute_multiples(MultipleInputs.from_statements(reference.current, reference.market))

    assert multiples["market_cap"].value == D("1800000")
    assert multiples["enterprise_value"].value == D("2000000")
    assert multiples["price_to_earnings"].value == pytest.approx(D("12.5"))
    assert multiples["earnings_yield"].value == pytest.approx(D("0.08"))
    assert multiples["price_to_book"].value == pytest.approx(D("3"))
    assert multiples["price_to_sales"].value == pytest.approx(D("1.8"))
    assert multiples["ev_to_ebitda"].value == pytest.approx(D("2000000") / D("260000"))
    assert multiples["ev_to_ebit"].value == pytest.approx(D("10"))
    assert multiples["ev_to_sales"].value == pytest.approx(D("2"))
    assert multiples["ev_to_free_cash_flow"].value == pytest.approx(D("2000000") / D("110000"))
    assert multiples["price_to_free_cash_flow"].value == pytest.approx(
        D("1800000") / D("110000")
    )
    assert multiples["free_cash_flow_yield"].value == pytest.approx(D("110000") / D("1800000"))


def test_multiples_are_traceable(reference) -> None:
    multiples = compute_multiples(MultipleInputs.from_statements(reference.current, reference.market))

    assert set(multiples) == EXPECTED_KEYS
    for key, result in multiples.items():
        assert result.key == key
        assert result.label
        assert result.formula
        assert isinstance(result.unit, MultipleUnit)
    assert multiples["market_cap"].unit is MultipleUnit.CURRENCY
    assert multiples["earnings_yield"].unit is MultipleUnit.PERCENT
    assert multiples["price_to_earnings"].unit is MultipleUnit.TIMES


def test_loss_making_and_negative_book_companies_get_notes(reference) -> None:
    loss = _with_income(reference.current, **{LineItem.NET_INCOME: D("-5")})
    loss_multiples = compute_multiples(MultipleInputs.from_statements(loss, reference.market))
    assert loss_multiples["price_to_earnings"].value is None
    assert loss_multiples["price_to_earnings"].note == "Not meaningful for nil or negative earnings."
    assert loss_multiples["earnings_yield"].value == pytest.approx(D("-5") / D("1800000"))

    no_fcf = FinancialStatements(
        income=reference.current.income,
        balance=reference.current.balance,
        cashflow=replace(
            reference.current.cashflow,
            values={
                key: value
                for key, value in reference.current.cashflow.values.items()
                if key not in (LineItem.FREE_CASH_FLOW, LineItem.OPERATING_CASH_FLOW)
            },
        ),
    )
    no_fcf_multiples = compute_multiples(MultipleInputs.from_statements(no_fcf, reference.market))
    assert no_fcf_multiples["ev_to_free_cash_flow"].value is None
    assert no_fcf_multiples["price_to_free_cash_flow"].value is None


def test_negative_book_equity_is_not_meaningful(reference) -> None:
    values = dict(reference.current.balance.values)
    values[LineItem.TOTAL_EQUITY] = D("-10")
    negative_book = FinancialStatements(
        income=reference.current.income,
        balance=replace(reference.current.balance, values=values),
        cashflow=reference.current.cashflow,
    )
    multiples = compute_multiples(
        MultipleInputs.from_statements(negative_book, reference.market)
    )

    assert multiples["price_to_book"].value is None
    assert multiples["price_to_book"].note == "Not meaningful for negative book equity."


def test_without_market_data_market_multiples_are_unavailable(reference) -> None:
    multiples = compute_multiples(MultipleInputs.from_statements(reference.current))

    assert multiples["market_cap"].value is None
    assert multiples["enterprise_value"].value is None
    for key in (
        "price_to_earnings",
        "earnings_yield",
        "price_to_book",
        "price_to_sales",
        "ev_to_ebitda",
        "ev_to_ebit",
        "ev_to_sales",
        "ev_to_free_cash_flow",
        "price_to_free_cash_flow",
        "free_cash_flow_yield",
    ):
        assert multiples[key].value is None, key


def test_without_a_cash_flow_statement_ebitda_and_fcf_are_unavailable(reference) -> None:
    statements = FinancialStatements(
        income=reference.current.income,
        balance=reference.current.balance,
        cashflow=None,
    )
    inputs = MultipleInputs.from_statements(statements, reference.market)
    multiples = compute_multiples(inputs)

    assert inputs.ebitda is None
    assert inputs.free_cash_flow is None
    assert multiples["ev_to_ebitda"].value is None
    assert multiples["ev_to_ebit"].value == pytest.approx(D("10"))
    assert multiples["ev_to_free_cash_flow"].value is None


def test_free_cash_flow_falls_back_to_operating_cash_flow_less_capex(reference) -> None:
    without_reported = FinancialStatements(
        income=reference.current.income,
        balance=reference.current.balance,
        cashflow=replace(
            reference.current.cashflow,
            values={
                key: value
                for key, value in reference.current.cashflow.values.items()
                if key is not LineItem.FREE_CASH_FLOW
            },
        ),
    )
    inputs = MultipleInputs.from_statements(without_reported, reference.market)
    assert inputs.free_cash_flow == D("110000")


def test_enterprise_value_requires_market_cap_debt_and_cash() -> None:
    inputs = MultipleInputs(
        market_cap=D("100"),
        net_income=None,
        book_value_equity=None,
        revenue=None,
        ebitda=None,
        ebit=None,
        free_cash_flow=None,
        total_debt=None,
        cash=None,
    )
    assert inputs.enterprise_value() is None
    assert compute_multiples(inputs)["enterprise_value"].value is None


def test_peer_statistics_reference_values() -> None:
    even = peer_statistics([D("10"), D("20"), D("12"), D("15")])
    assert even.count == 4
    assert even.mean == D("14.25")
    assert even.median == D("13.5")
    assert even.harmonic_mean == pytest.approx(D("4") / D("0.3"))
    assert even.minimum == D("10")
    assert even.maximum == D("20")

    odd = peer_statistics([D("10"), D("20"), D("30")])
    assert odd.median == D("20")
    assert odd.harmonic_mean == pytest.approx(D("3") / D("0.1833333333333333"))
    assert odd.minimum == D("10")
    assert odd.maximum == D("30")


def test_peer_statistics_with_a_non_positive_multiple_omit_the_harmonic_mean() -> None:
    stats = peer_statistics([D("10"), D("0"), D("20")])
    assert stats.harmonic_mean is None
    assert stats.median == D("10")


def test_peer_statistics_validation() -> None:
    with pytest.raises(ValueError, match="at least one"):
        peer_statistics([])
    with pytest.raises(ValueError, match="finite"):
        peer_statistics([D("10"), D("NaN")])


def test_implied_valuation_reference_values() -> None:
    assert implied_enterprise_value(D("100"), D("8.5")) == D("850.00")
    assert implied_equity_value(D("100"), D("8.5"), D("200")) == D("650.00")
    assert implied_share_price(D("100"), D("8.5"), D("200"), D("50")) == D("13.0000")


def test_implied_valuation_validation() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        implied_enterprise_value(D("-1"), D("8"))
    with pytest.raises(ValueError, match="must be positive"):
        implied_enterprise_value(D("100"), D("0"))
    with pytest.raises(ValueError, match="must be positive"):
        implied_equity_value(D("100"), D("-2"), D("200"))
    with pytest.raises(ValueError, match="must be finite"):
        implied_enterprise_value(D("NaN"), D("8"))
    with pytest.raises(ValueError, match="shares_outstanding must be positive"):
        implied_share_price(D("100"), D("8"), D("0"), D("0"))
