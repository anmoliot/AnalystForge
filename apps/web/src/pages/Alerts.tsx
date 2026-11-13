import { Bell } from "lucide-react";

import { ModuleScaffold } from "@/pages/ModuleScaffold";

export default function Alerts() {
  return (
    <ModuleScaffold
      icon={Bell}
      title="Alerts"
      description="Monitor price moves, valuation ratios, filing events and news sentiment with email, webhook and in-app delivery."
      status="No alert rules exist. Alerts require at least one watchlist instrument and a data source."
      capabilities={[
        "Price, ratio, sentiment and filing triggers",
        "Email, webhook and in-app delivery",
        "Delivery history and audit",
        "Quiet hours and per-channel preferences",
      ]}
    />
  );
}
