import {
  Activity,
  ArrowUpRight,
  BookOpen,
  Briefcase,
  Database,
  Newspaper,
  RefreshCcw,
  ShieldCheck,
} from "lucide-react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Panel } from "@/components/ui/Panel";
import { StatusDot } from "@/components/ui/StatusDot";
import { useMeta, useReadiness } from "@/hooks/useMeta";

function CheckRow({
  label,
  status,
  detail,
}: {
  label: string;
  status: "ok" | "warn" | "error" | "idle";
  detail?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line/60 px-3 py-2 last:border-0">
      <div className="flex items-center gap-2">
        <StatusDot status={status} />
        <span className="text-xs capitalize text-ink">{label}</span>
      </div>
      <span className="num text-2xs text-muted">
        {detail ?? (status === "ok" ? "healthy" : status === "idle" ? "unknown" : status)}
      </span>
    </div>
  );
}

export default function Home() {
  const meta = useMeta();
  const readiness = useReadiness();
  const checks = readiness.data?.checks ?? {};
  const today = new Intl.DateTimeFormat("en-GB", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(new Date());

  const moduleLinks = [
    { label: "Company analysis", to: "/companies", icon: BookOpen },
    { label: "Valuation workbench", to: "/valuation", icon: Activity },
    { label: "Portfolio risk", to: "/portfolios", icon: Briefcase },
    { label: "Macro dashboard", to: "/macro", icon: Database },
  ];

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-4 p-4">
      <PageHeader
        eyebrow={today}
        title="Workspace overview"
        description="Your research desk: watchlists, company fundamentals, valuation work and portfolio risk in one audited workspace."
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => void readiness.refetch()}>
              <RefreshCcw className="size-3.5" aria-hidden="true" /> Refresh status
            </Button>
            <Link to="/companies">
              <Button variant="primary" size="sm">
                Open company analysis <ArrowUpRight className="size-3.5" aria-hidden="true" />
              </Button>
            </Link>
          </>
        }
      />

      <div className="grid gap-3 lg:grid-cols-3">
        <Panel
          className="lg:col-span-2"
          title="Watchlist"
          subtitle="Live prices require an ingested market-data set"
          actions={<Badge>0 instruments</Badge>}
        >
          <EmptyState
            icon={Briefcase}
            title="No instruments in this watchlist"
            description="Load an instrument universe, then add companies here to see quotes, changes and alerts. Data gaps are shown explicitly and are never filled with placeholder prices."
            action={
              <Link to="/companies">
                <Button size="sm" variant="secondary">
                  Browse instruments
                </Button>
              </Link>
            }
          />
        </Panel>

        <Panel title="System readiness" subtitle="Live dependency checks">
          <div>
            <CheckRow
              label="API"
              status={readiness.isError ? "error" : readiness.data ? "ok" : "idle"}
              detail={readiness.data?.version ?? undefined}
            />
            <CheckRow
              label="Database"
              status={
                checks.database?.status === "ok"
                  ? "ok"
                  : checks.database?.status === "error"
                    ? "error"
                    : "idle"
              }
              detail={
                checks.database?.latency_ms !== undefined
                  ? `${checks.database.latency_ms} ms`
                  : checks.database?.error
              }
            />
            <CheckRow
              label="Redis / queue"
              status={
                checks.redis?.status === "ok"
                  ? "ok"
                  : checks.redis?.status === "not_configured"
                    ? "warn"
                    : checks.redis?.status === "error"
                      ? "error"
                      : "idle"
              }
              detail={
                checks.redis?.status === "not_configured" ? "inline mode" : checks.redis?.status
              }
            />
            <CheckRow label="Storage" status={checks.storage?.status === "ok" ? "ok" : "error"} />
          </div>
          <div className="flex items-start gap-2 border-t border-line px-3 py-2.5">
            <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-accent" aria-hidden="true" />
            <p className="text-2xs leading-relaxed text-muted">
              Every analytic records its provider, as-of timestamp and formula. Verification state
              is surfaced in the metric drawer.
            </p>
          </div>
        </Panel>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <Panel title="Market pulse" className="lg:col-span-2">
          <EmptyState
            icon={Activity}
            title="No market series loaded"
            description="Quotes, indices, yield curves and sector boards appear after the ingestion worker completes a run. Until then this panel stays explicitly empty rather than showing invented values."
            action={
              <Link to="/macro">
                <Button size="sm" variant="secondary">
                  Open macro dashboard
                </Button>
              </Link>
            }
          />
        </Panel>

        <Panel title="Latest research">
          <EmptyState
            icon={Newspaper}
            title="No research activity yet"
            description="News sentiment, filing diffs and AI research notes will appear here with their source passages and timestamps."
          />
        </Panel>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <Panel title="Workbench shortcuts" className="lg:col-span-2">
          <div className="grid gap-px bg-line sm:grid-cols-2">
            {moduleLinks.map(({ label, to, icon: Icon }) => (
              <Link
                key={to}
                to={to}
                className="flex items-center gap-3 bg-panel px-3 py-3 transition-colors hover:bg-elevated"
              >
                <span className="flex size-7 items-center justify-center rounded border border-line bg-elevated">
                  <Icon className="size-3.5 text-accent" aria-hidden="true" />
                </span>
                <span className="flex-1 text-xs font-medium">{label}</span>
                <ArrowUpRight className="size-3.5 text-muted" aria-hidden="true" />
              </Link>
            ))}
          </div>
        </Panel>

        <Panel title="Capabilities" subtitle="Resolved from environment">
          <dl className="divide-y divide-line/60">
            {meta.data ? (
              Object.entries(meta.data.capabilities).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between gap-2 px-3 py-2">
                  <dt className="text-xs capitalize text-muted">{key.replaceAll("_", " ")}</dt>
                  <dd>
                    {typeof value === "boolean" ? (
                      <Badge tone={value ? "positive" : "neutral"}>
                        {value ? "enabled" : "off"}
                      </Badge>
                    ) : (
                      <Badge tone={value === "none" ? "warning" : "accent"}>{value}</Badge>
                    )}
                  </dd>
                </div>
              ))
            ) : (
              <div className="space-y-2 p-3">
                <div className="skeleton h-4 w-full" />
                <div className="skeleton h-4 w-4/5" />
                <div className="skeleton h-4 w-3/5" />
              </div>
            )}
          </dl>
        </Panel>
      </div>

      <p className="px-1 pb-2 text-2xs leading-relaxed text-muted">
        {meta.data?.disclaimer ??
          "AnalystForge is a research tool, not investment advice. Data may be delayed or incomplete."}
      </p>
    </div>
  );
}
