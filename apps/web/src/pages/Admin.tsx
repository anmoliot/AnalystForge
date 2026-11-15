import {
  Shield,
  Users,
  History,
  CheckCircle2,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Panel } from "@/components/ui/Panel";

export interface AuditRecord {
  id: string;
  action: string;
  actor: string;
  resource: string;
  status: string;
  timestamp: string;
}

export default function Admin() {
  const auditLogs: AuditRecord[] = [
    {
      id: "1",
      action: "AUTH_LOGIN",
      actor: "analyst@hedgefund.com",
      resource: "Session Token",
      status: "SUCCESS",
      timestamp: "2026-11-15 15:10:20 UTC",
    },
    {
      id: "2",
      action: "DCF_VALUATION_CREATE",
      actor: "analyst@hedgefund.com",
      resource: "Model NVDA-DCF-2026",
      status: "SUCCESS",
      timestamp: "2026-11-15 14:45:12 UTC",
    },
    {
      id: "3",
      action: "BACKTEST_EXECUTE",
      actor: "analyst@hedgefund.com",
      resource: "Strategy SMA_CROSSOVER",
      status: "SUCCESS",
      timestamp: "2026-11-15 14:20:05 UTC",
    },
    {
      id: "4",
      action: "PORTFOLIO_OPTIMIZE",
      actor: "analyst@hedgefund.com",
      resource: "Tech Alpha Fund",
      status: "SUCCESS",
      timestamp: "2026-11-15 13:50:33 UTC",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <Shield className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-semibold tracking-tight text-white">Compliance & Governance Console</h1>
        </div>
        <p className="mt-1 text-sm text-neutral-400">
          Immutable audit trails, role-based access control (RBAC), and external provider connectivity status.
        </p>
      </div>

      {/* Provider Connectivity Status */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-4">
        {[
          { name: "Yahoo Finance (Prices)", status: "OPERATIONAL", latency: "142ms" },
          { name: "FRED St. Louis (Macro)", status: "OPERATIONAL", latency: "210ms" },
          { name: "ECB Statistical Data (FX)", status: "OPERATIONAL", latency: "188ms" },
          { name: "SEC EDGAR (Filings & XBRL)", status: "OPERATIONAL", latency: "295ms" },
        ].map((p, idx) => (
          <Panel key={idx} className="p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-neutral-300">{p.name}</span>
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            </div>
            <div className="mt-2 flex items-baseline justify-between text-xs text-neutral-400">
              <Badge tone="positive" className="text-[10px]">
                {p.status}
              </Badge>
              <span className="font-mono">{p.latency}</span>
            </div>
          </Panel>
        ))}
      </div>

      {/* Team & RBAC Table */}
      <Panel className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-neutral-800 p-4">
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-brand-400" />
            <h2 className="text-base font-medium text-white">Team Members & Permissions</h2>
          </div>
          <Badge tone="neutral">2 Active Analysts</Badge>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-neutral-300">
            <thead className="border-b border-neutral-800 bg-neutral-900/60 text-xs uppercase tracking-wider text-neutral-400">
              <tr>
                <th className="px-4 py-3">Member</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Tenant</th>
                <th className="px-4 py-3">2FA Status</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-800">
              <tr className="hover:bg-neutral-800/40">
                <td className="px-4 py-3">
                  <div className="font-medium text-white">Lead Portfolio Manager</div>
                  <div className="text-xs text-neutral-400">pm@hedgefund.com</div>
                </td>
                <td className="px-4 py-3">
                  <Badge tone="accent">PORTFOLIO_MANAGER</Badge>
                </td>
                <td className="px-4 py-3 text-xs text-neutral-300">Alpha Investment Management</td>
                <td className="px-4 py-3 text-xs text-emerald-400">Enforced</td>
                <td className="px-4 py-3">
                  <Badge tone="positive">Active</Badge>
                </td>
              </tr>
              <tr className="hover:bg-neutral-800/40">
                <td className="px-4 py-3">
                  <div className="font-medium text-white">Quantitative Analyst</div>
                  <div className="text-xs text-neutral-400">analyst@hedgefund.com</div>
                </td>
                <td className="px-4 py-3">
                  <Badge tone="neutral">ANALYST</Badge>
                </td>
                <td className="px-4 py-3 text-xs text-neutral-300">Alpha Investment Management</td>
                <td className="px-4 py-3 text-xs text-neutral-400">Optional</td>
                <td className="px-4 py-3">
                  <Badge tone="positive">Active</Badge>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Immutable Compliance Audit Trail */}
      <Panel className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-neutral-800 p-4">
          <div className="flex items-center gap-2">
            <History className="h-5 w-5 text-brand-400" />
            <h2 className="text-base font-medium text-white">Immutable Audit Trail (SOX & SEC Rule 17a-4)</h2>
          </div>
          <Badge tone="neutral">{auditLogs.length} Events</Badge>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-neutral-300">
            <thead className="border-b border-neutral-800 bg-neutral-900/60 text-xs uppercase tracking-wider text-neutral-400">
              <tr>
                <th className="px-4 py-3">Action</th>
                <th className="px-4 py-3">Actor</th>
                <th className="px-4 py-3">Resource Target</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-800 font-mono text-xs">
              {auditLogs.map((log) => (
                <tr key={log.id} className="hover:bg-neutral-800/40">
                  <td className="px-4 py-3 font-semibold text-white">{log.action}</td>
                  <td className="px-4 py-3 text-neutral-300">{log.actor}</td>
                  <td className="px-4 py-3 text-brand-300">{log.resource}</td>
                  <td className="px-4 py-3">
                    <span className="text-emerald-400 font-semibold">{log.status}</span>
                  </td>
                  <td className="px-4 py-3 text-right text-neutral-400">{log.timestamp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
