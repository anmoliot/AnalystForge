import { Shield } from "lucide-react";

import { ModuleScaffold } from "@/pages/ModuleScaffold";

export default function Admin() {
  return (
    <ModuleScaffold
      icon={Shield}
      title="Team & access"
      description="Users, role assignments, immutable audit log, data-provider health, feature flags and API-key quotas."
      status="Sign-in and team administration are not yet configured for this workspace."
      capabilities={[
        "RBAC permission matrix enforced server-side",
        "Append-only audit log with before/after values",
        "Provider health and quota dashboard",
        "Immutable exportable compliance trail",
      ]}
    />
  );
}
