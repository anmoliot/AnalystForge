"""AnalystForge quantitative core.

Pure functions and data containers only: this package must never import web,
database or provider libraries. All monetary results use :class:`decimal.Decimal`.
"""

from analystforge.quant.black_litterman import (
    BlackLittermanResult,
    black_litterman,
)
from analystforge.quant.dcf import (
    DCFAssumptions,
    DCFResult,
    ForecastYear,
    TerminalValueMethod as DCFTerminalValueMethod,
    project_fcff,
    run_dcf,
)
from analystforge.quant.ddm import (
    DividendYear,
    GordonGrowthResult,
    MultiStageDDMAssumptions,
    MultiStageDDMResult,
    gordon_growth_ddm,
    multi_stage_ddm,
)
from analystforge.quant.factors import (
    FactorRegressionResult,
    fama_french_regression,
)
from analystforge.quant.fcfe import (
    FCFEAssumptions,
    FCFEResult,
    FCFEYearForecast,
    TerminalValueMethod as FCFETerminalValueMethod,
    fcfe_valuation,
)
from analystforge.quant.football_field import (
    FootballFieldResult,
    ValuationRange,
    build_football_field,
)
from analystforge.quant.money import ONE, ZERO, discount_factor, quantize, to_decimal
from analystforge.quant.multiples import (
    MultipleInputs,
    MultipleResult,
    MultipleUnit,
    PeerStats,
    compute_multiples,
    implied_enterprise_value,
    implied_equity_value,
    implied_share_price,
    peer_statistics,
)
from analystforge.quant.precedents import (
    PrecedentAnalysisResult,
    PrecedentDeal,
    precedent_transactions_valuation,
)
from analystforge.quant.rebalance import (
    RebalancePlan,
    TradeAction,
    TradeOrder,
    generate_rebalance_trades,
)
from analystforge.quant.residual_income import (
    ResidualIncomeAssumptions,
    ResidualIncomeResult,
    ResidualIncomeTerminalMethod,
    ResidualIncomeYear,
    residual_income_valuation,
)
from analystforge.quant.rolling import (
    rolling_beta,
    rolling_information_ratio,
    rolling_max_drawdown,
    rolling_sharpe,
    rolling_tracking_error,
    rolling_volatility,
)
from analystforge.quant.sotp import (
    SegmentValuation,
    SOTPResult,
    sotp_valuation,
)
from analystforge.quant.wacc import (
    WACCResult,
    after_tax_cost_of_debt,
    blume_adjusted_beta,
    capm_cost_of_equity,
    compute_wacc,
    relever_beta,
    unlever_beta,
    wacc_from_capm,
)

__version__ = "0.1.0"

__all__ = [
    "BlackLittermanResult",
    "DCFAssumptions",
    "DCFResult",
    "DCFTerminalValueMethod",
    "DividendYear",
    "FactorRegressionResult",
    "FCFEAssumptions",
    "FCFEResult",
    "FCFETerminalValueMethod",
    "FCFEYearForecast",
    "FootballFieldResult",
    "ForecastYear",
    "GordonGrowthResult",
    "MultipleInputs",
    "MultipleResult",
    "MultipleUnit",
    "MultiStageDDMAssumptions",
    "MultiStageDDMResult",
    "ONE",
    "PeerStats",
    "PrecedentAnalysisResult",
    "PrecedentDeal",
    "RebalancePlan",
    "ResidualIncomeAssumptions",
    "ResidualIncomeResult",
    "ResidualIncomeTerminalMethod",
    "ResidualIncomeYear",
    "SOTPResult",
    "SegmentValuation",
    "TradeAction",
    "TradeOrder",
    "ValuationRange",
    "WACCResult",
    "ZERO",
    "after_tax_cost_of_debt",
    "black_litterman",
    "blume_adjusted_beta",
    "build_football_field",
    "capm_cost_of_equity",
    "compute_multiples",
    "compute_wacc",
    "discount_factor",
    "fama_french_regression",
    "fcfe_valuation",
    "generate_rebalance_trades",
    "gordon_growth_ddm",
    "implied_enterprise_value",
    "implied_equity_value",
    "implied_share_price",
    "multi_stage_ddm",
    "peer_statistics",
    "precedent_transactions_valuation",
    "project_fcff",
    "quantize",
    "relever_beta",
    "residual_income_valuation",
    "rolling_beta",
    "rolling_information_ratio",
    "rolling_max_drawdown",
    "rolling_sharpe",
    "rolling_tracking_error",
    "rolling_volatility",
    "run_dcf",
    "sotp_valuation",
    "to_decimal",
    "unlever_beta",
    "wacc_from_capm",
]
