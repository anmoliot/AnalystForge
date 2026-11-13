import { Building2 } from "lucide-react";

import { ModuleScaffold } from "@/pages/ModuleScaffold";

export default function Companies() {
  return (
    <ModuleScaffold
      icon={Building2}
      title="Companies"
      description="Normalised financial statements, ratio analysis, peer percentiles, filings and valuation entry points for every loaded instrument."
      status="The instrument master is empty. Load market and SEC EDGAR data, then search any ticker to open its research page."
      capabilities={[
        "10+ years of annual and quarterly statements",
        "50+ ratios with formula and source drawers",
        "SEC filing reader with period-over-period diffs",
        "Peer comparison and sector percentiles",
      ]}
    />
  );
}
