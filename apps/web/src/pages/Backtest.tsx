import { FlaskConical } from "lucide-react";

import { ModuleScaffold } from "@/pages/ModuleScaffold";

export default function Backtest() {
  return (
    <ModuleScaffold
      icon={FlaskConical}
      title="Backtest lab"
      description="Design rule-based or sandboxed Python strategies, test with realistic costs and point-in-time data, inspect trades and overfitting diagnostics."
      status="Backtests require an ingested price history. No market series are available yet."
      capabilities={[
        "Point-in-time engine with commission and slippage",
        "Walk-forward and out-of-sample splits",
        "Parameter sweep heatmaps with deflated Sharpe",
        "Trade log, exposure and benchmark comparison",
      ]}
    />
  );
}
