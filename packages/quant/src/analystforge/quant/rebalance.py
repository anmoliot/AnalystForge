"""Portfolio rebalancing and trade list generation.

Generates actionable buy/sell orders to transition an existing portfolio
to target weights, calculating turnover, trade values, and transaction costs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class TradeAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True, slots=True)
class TradeOrder:
    ticker: str
    action: TradeAction
    current_shares: Decimal
    target_shares: Decimal
    delta_shares: Decimal
    price: Decimal
    current_value: Decimal
    target_value: Decimal
    trade_value: Decimal  # Absolute dollar value of trade
    current_weight: Decimal
    target_weight: Decimal
    weight_delta: Decimal
    estimated_commission: Decimal


@dataclass(frozen=True, slots=True)
class RebalancePlan:
    orders: tuple[TradeOrder, ...]
    portfolio_value: Decimal
    starting_cash: Decimal
    ending_cash: Decimal
    turnover: Decimal  # One-way turnover: 0.5 * sum(|delta_w|)
    total_traded_value: Decimal
    total_estimated_commissions: Decimal


def generate_rebalance_trades(
    current_shares: Mapping[str, Decimal | float],
    prices: Mapping[str, Decimal | float],
    target_weights: Mapping[str, Decimal | float],
    *,
    cash: Decimal | float = Decimal("0"),
    commission_bps: Decimal | float = Decimal("10"),  # 10 bps default
    allow_fractional: bool = True,
    min_trade_size: Decimal | float = Decimal("1.00"),
) -> RebalancePlan:
    """Generate trade orders to transition portfolio to target weights.

    Parameters
    ----------
    current_shares : Current share count per ticker.
    prices : Current market price per ticker.
    target_weights : Desired target weight per ticker (should sum to <= 1.0; remainder is cash).
    cash : Current uninvested cash.
    commission_bps : Commission in basis points of trade value (e.g., 10 = 0.10%).
    allow_fractional : If False, target shares are rounded to nearest whole share.
    min_trade_size : Trades smaller than this absolute dollar amount are treated as HOLD.

    Returns
    -------
    RebalancePlan with itemized orders and summary metrics.
    """
    cash_dec = Decimal(str(cash))
    comm_rate = Decimal(str(commission_bps)) / Decimal("10000")
    min_trade_dec = Decimal(str(min_trade_size))

    # All tickers present in either current holdings or target weights
    all_tickers = sorted(set(current_shares.keys()) | set(target_weights.keys()))

    # Convert prices and shares to Decimal
    dec_prices: dict[str, Decimal] = {}
    for t in all_tickers:
        if t not in prices or prices[t] is None:
            raise ValueError(f"Price missing for ticker '{t}'")
        p = Decimal(str(prices[t]))
        if p <= Decimal("0"):
            raise ValueError(f"Price for '{t}' must be strictly positive, got {p}")
        dec_prices[t] = p

    dec_shares: dict[str, Decimal] = {}
    for t in all_tickers:
        s = Decimal(str(current_shares.get(t, 0)))
        if s < Decimal("0"):
            raise ValueError(f"Current shares for '{t}' cannot be negative, got {s}")
        dec_shares[t] = s

    # Calculate current market values
    current_values = {t: dec_shares[t] * dec_prices[t] for t in all_tickers}
    holdings_value = sum(current_values.values(), Decimal("0"))
    total_portfolio_value = holdings_value + cash_dec

    if total_portfolio_value <= Decimal("0"):
        raise ValueError("Total portfolio value (holdings + cash) must be positive.")

    # Target weights validation
    dec_targets: dict[str, Decimal] = {}
    target_sum = Decimal("0")
    for t in all_tickers:
        w = Decimal(str(target_weights.get(t, 0)))
        if w < Decimal("0"):
            raise ValueError(f"Target weight for '{t}' cannot be negative, got {w}")
        dec_targets[t] = w
        target_sum += w

    if target_sum > Decimal("1.0001"):
        raise ValueError(f"Target weights sum to {target_sum}, which exceeds 100%.")

    # Current weights
    current_weights = {t: current_values[t] / total_portfolio_value for t in all_tickers}

    orders: list[TradeOrder] = []
    total_trade_value = Decimal("0")
    total_commissions = Decimal("0")
    cash_delta = Decimal("0")
    turnover_sum = Decimal("0")

    for t in all_tickers:
        curr_sh = dec_shares[t]
        p = dec_prices[t]
        curr_val = current_values[t]
        curr_w = current_weights[t]
        tgt_w = dec_targets[t]

        tgt_val = total_portfolio_value * tgt_w
        if allow_fractional:
            tgt_sh = tgt_val / p
        else:
            tgt_sh = Decimal(str(round(float(tgt_val / p))))
            tgt_val = tgt_sh * p

        delta_sh = tgt_sh - curr_sh
        delta_val = delta_sh * p
        abs_trade_val = abs(delta_val)

        w_delta = tgt_w - curr_w
        turnover_sum += abs(w_delta)

        if abs_trade_val < min_trade_dec or abs(delta_sh) < Decimal("1e-6"):
            action = TradeAction.HOLD
            comm = Decimal("0")
            delta_sh = Decimal("0")
            abs_trade_val = Decimal("0")
        elif delta_sh > Decimal("0"):
            action = TradeAction.BUY
            comm = abs_trade_val * comm_rate
            cash_delta -= abs_trade_val + comm
        else:
            action = TradeAction.SELL
            comm = abs_trade_val * comm_rate
            cash_delta += abs_trade_val - comm

        total_trade_value += abs_trade_val
        total_commissions += comm

        orders.append(
            TradeOrder(
                ticker=t,
                action=action,
                current_shares=curr_sh,
                target_shares=tgt_sh,
                delta_shares=delta_sh,
                price=p,
                current_value=curr_val,
                target_value=tgt_val,
                trade_value=abs_trade_val,
                current_weight=curr_w,
                target_weight=tgt_w,
                weight_delta=w_delta,
                estimated_commission=comm,
            )
        )

    ending_cash = cash_dec + cash_delta
    # One-way turnover is 0.5 * sum(|delta_w|)
    turnover = turnover_sum / Decimal("2")

    return RebalancePlan(
        orders=tuple(orders),
        portfolio_value=total_portfolio_value,
        starting_cash=cash_dec,
        ending_cash=ending_cash,
        turnover=turnover,
        total_traded_value=total_trade_value,
        total_estimated_commissions=total_commissions,
    )
