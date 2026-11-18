import { Panel } from "@/components/ui/Panel";
export default function Admin() {
  return <div className="space-y-4">
    <h1 className="text-xl font-semibold">Compliance & Governance Console</h1>
    <Panel className="p-5">Audit and team browsing are unavailable in this interface.
      Administrators can inspect the persisted audit_log table through their database administration tools.</Panel>
  </div>;
}
