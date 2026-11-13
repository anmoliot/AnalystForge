import {
  Activity,
  ArrowUpRight,
  BookOpen,
  Briefcase,
  Database,
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
import { useCoverage, useMeta, useProviderHealth, useReadiness } from "@/hooks/useMeta";
import { formatCompact, formatDate } from "@/lib/format";

function healthTone(status: string, configured: boolean): "ok" | "warn" | "error" | "idle" {
  if (!configured) return "idle";
  if (status === "ok") return "ok";
  if (status === "error") return "error";
  if (status === "cooldown" || status === "degraded") return "warn";
  return "idle";
}

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
  const coverage = useCoverage();
  const providerHealth = useProviderHealth();
  const checks = readiness.data?.checks ?? {};
  const instrumentTotal =
    coverage.data?.exchanges.reduce((total, exchange) => total + exchange.instruments, 0) ?? 0;
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
        <Panel
          className="lg:col-span-2"
          title="Data coverage"
          subtitle="Persisted reference and market data"
          actions={
            <Badge tone={coverage.data?.prices.last_day ? "positive" : "neutral"}>
              {coverage.data?.prices.last_day
                ? `last bar ${formatDate(coverage.data.prices.last_day)}`
                : "no price data"}
            </Badge>
          }
        >
          {coverage.isError ? (
            <EmptyState
              icon={Database}
              title="Coverage unavailable"
              description={coverage.error.message}
              action={
                <Button size="sm" variant="secondary" onClick={() => void coverage.refetch()}>
                  Retry
                </Button>
              }
            />
          ) : !coverage.data ? (
            <div className="space-y-2 p-3">
              <div className="skeleton h-14 w-full" />
              <div className="skeleton h-8 w-full" />
              <div className="skeleton h-8 w-4/5" />
            </div>
          ) : coverage.data.exchanges.length === 0 ? (
            <EmptyState
              icon={Database}
              title="No reference universe loaded"
              description="Seed the exchange and instrument master and run an ingestion job. This panel reports only persisted data; gaps are never filled with placeholder values."
              action={
                <Link to="/macro">
                  <Button size="sm" variant="secondary">
                    Open macro dashboard
                  </Button>
                </Link>
              }
            />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-px border-b border-line bg-line sm:grid-cols-4">
                {[
                  ["Instruments", formatCompact(instrumentTotal)],
                  ["Daily bars", formatCompact(coverage.data.prices.bars)],
                  ["XBRL facts", formatCompact(coverage.data.fundamentals.facts)],
                  ["Macro points", formatCompact(coverage.data.macro.observations)],
                ].map(([label, value]) => (
                  <div key={label} className="bg-panel px-3 py-3">
                    <p className="text-2xs uppercase tracking-wide text-muted">{label}</p>
                    <p className="num mt-0.5 text-lg text-ink">{value}</p>
                  </div>
                ))}
              </div>
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-line text-2xs uppercase tracking-wide text-muted">
                    <th className="px-3 py-2 font-medium">Exchange</th>
                    <th className="px-3 py-2 text-right font-medium">Instruments</th>
                    <th className="px-3 py-2 text-right font-medium">Priced</th>
                    <th className="px-3 py-2 text-right font-medium">Last bar</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/60">
                  {coverage.data.exchanges.map((exchange) => (
                    <tr key={exchange.code}>
                      <td className="px-3 py-2">
                        <span className="flex items-center gap-2">
                          <span className="font-medium text-ink">{exchange.code}</span>
                          <span className="text-muted">{exchange.currency}</span>
                        </span>
                      </td>
                      <td className="num px-3 py-2 text-right text-ink">{exchange.instruments}</td>
                      <td className="num px-3 py-2 text-right text-muted">
                        {exchange.priced_instruments}
                      </td>
                      <td className="num px-3 py-2 text-right text-muted">
                        {formatDate(exchange.last_day)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </Panel>

        <Panel
          title="Provider health"
          subtitle="Latest attempt per adapter"
          actions={
            <Badge>
              {providerHealth.data
                ? `${providerHealth.data.providers.filter((row) => row.configured).length} active`
                : "—"}
            </Badge>
          }
        >
          {providerHealth.isError ? (
            <EmptyState
              icon={Activity}
              title="Provider health unavailable"
              description={providerHealth.error.message}
              action={
                <Button size="sm" variant="secondary" onClick={() => void providerHealth.refetch()}>
                  Retry
                </Button>
              }
            />
          ) : !providerHealth.data ? (
            <div className="space-y-2 p-3">
              <div className="skeleton h-8 w-full" />
              <div className="skeleton h-8 w-4/5" />
            </div>
          ) : (
            <div>
              {providerHealth.data.providers.map((row) => (
                <div
                  key={`${row.capability}:${row.provider}`}
                  className="border-b border-line/60 px-3 py-2.5 last:border-0"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 items-start gap-2">
                      <StatusDot status={healthTone(row.status, row.configured)} className="mt-1" />
                      <div className="min-w-0">
                        <p className="truncate text-xs font-medium text-ink">{row.provider}</p>
                        <p className="text-2xs text-muted">
                          {row.capability}
                          {row.latency_ms !== null ? ` · ${row.latency_ms} ms` : ""}
                        </p>
                      </div>
                    </div>
                    <Badge tone={row.configured ? "positive" : "neutral"}>
                      {row.configured ? "on" : "off"}
                    </Badge>
                  </div>
                  {row.error ? (
                    <p className="mt-1 pl-3.5 text-2xs leading-relaxed text-negative">
                      {row.error}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          )}
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
                    ) : typeof value === "string" ? (
                      <Badge tone={value === "none" ? "warning" : "accent"}>{value}</Badge>
                    ) : (
                      <span className="max-w-52 text-right font-mono text-2xs leading-relaxed text-muted">
                        {Object.entries(value)
                          .map(([name, provider]) => `${name} ${provider ?? "off"}`)
                          .join(" · ")}
                      </span>
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
