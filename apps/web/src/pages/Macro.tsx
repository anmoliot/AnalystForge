import { LineChart } from "lucide-react";

import { ModuleScaffold } from "@/pages/ModuleScaffold";

export default function Macro() {
  return (
    <ModuleScaffold
      icon={LineChart}
      title="Macro & markets"
      description="Yield curves, inflation, growth, labour, credit, FX and commodity dashboards built sourced series with explicit as-of dates."
      status="No macro observations have been ingested. FRED, World Bank and ECB adapters are configured through environment credentials."
      capabilities={[
        "Current vs historical yield curves",
        "CPI, GDP, unemployment and policy-rate trends",
        "Sector, FX, commodity and crypto boards",
        "Correlation regime view with as-of timestamps",
      ]}
    />
  );
}
