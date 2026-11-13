import { Command, Menu, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { CommandPalette } from "@/components/CommandPalette";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Badge } from "@/components/ui/Badge";
import { StatusDot } from "@/components/ui/StatusDot";
import { findNavItem, navSections } from "@/config/nav";
import { useMeta, useReadiness } from "@/hooks/useMeta";
import { cn } from "@/lib/utils";
import { useCommandPalette } from "@/stores/commandPalette";

function UtcClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const time = now.toISOString().slice(11, 19);
  return (
    <span className="num" title="Coordinated Universal Time">
      {time} UTC
    </span>
  );
}

export function AppShell() {
  const location = useLocation();
  const current = findNavItem(location.pathname);
  const title = location.pathname === "/" ? "Overview" : (current?.label ?? "AnalystForge");
  const openPalette = useCommandPalette((state) => state.setOpen);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const meta = useMeta();
  const readiness = useReadiness();

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  const apiStatus = readiness.isError
    ? "error"
    : readiness.data?.status === "ready"
      ? "ok"
      : readiness.isLoading
        ? "idle"
        : "warn";

  const sidebar = (
    <div className="flex h-full w-56 shrink-0 flex-col border-r border-line bg-panel">
      <div className="flex h-11 items-center gap-2.5 border-b border-line px-3">
        <div className="flex size-6 items-center justify-center rounded bg-accent/15">
          <span className="font-mono text-sm font-bold text-accent">A</span>
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold tracking-tight">AnalystForge</p>
          <p className="truncate text-2xs text-muted">Research workspace</p>
        </div>
        <button
          type="button"
          onClick={() => setMobileNavOpen(false)}
          className="flex size-7 items-center justify-center rounded text-muted hover:bg-elevated hover:text-ink md:hidden"
          aria-label="Close navigation"
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="border-b border-line px-3 py-2.5">
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded border border-line bg-elevated px-2 py-1.5 text-left hover:border-muted/40"
          aria-label="Switch workspace"
        >
          <span className="flex size-5 items-center justify-center rounded-sm bg-accent/20 font-mono text-2xs font-semibold text-accent">
            AF
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-medium">Personal workspace</span>
            <span className="block truncate text-2xs text-muted">Local environment</span>
          </span>
        </button>
      </div>

      <nav aria-label="Primary" className="flex-1 overflow-y-auto px-2 py-3">
        {navSections.map((section) => (
          <div key={section.title} className="mb-4 last:mb-0">
            <p className="mb-1 px-2 text-2xs font-semibold uppercase tracking-[0.1em] text-muted/70">
              {section.title}
            </p>
            <ul className="space-y-0.5">
              {section.items.map((item) => {
                const Icon = item.icon;
                return (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.to === "/"}
                      className={({ isActive }) =>
                        cn(
                          "group flex h-7 items-center gap-2 rounded px-2 text-xs transition-colors",
                          isActive
                            ? "bg-accent/10 font-medium text-accent"
                            : "text-muted hover:bg-elevated hover:text-ink",
                        )
                      }
                    >
                      <Icon className="size-3.5 shrink-0" aria-hidden="true" />
                      <span className="flex-1 truncate">{item.label}</span>
                      {item.shortcut ? (
                        <span className="hidden font-mono text-2xs text-muted/50 group-hover:block">
                          {item.shortcut}
                        </span>
                      ) : null}
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-line px-3 py-2.5">
        <div className="flex items-center justify-between text-2xs text-muted">
          <span className="flex items-center gap-1.5">
            <StatusDot status={apiStatus} />
            {apiStatus === "ok"
              ? "API connected"
              : apiStatus === "error"
                ? "API offline"
                : "Checking API"}
          </span>
          <span className="num">{meta.data?.version ?? "—"}</span>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-canvas">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[60] focus:rounded focus:bg-accent focus:px-3 focus:py-1.5 focus:text-accent-ink"
      >
        Skip to content
      </a>

      {meta.data?.demo_mode ? (
        <div className="flex h-7 shrink-0 items-center justify-center gap-2 bg-warning px-3 text-center text-2xs font-semibold uppercase tracking-[0.12em] text-black">
          Demo mode — sample data is clearly labelled and must not be used for investment decisions
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1">
        <aside className="hidden md:block">{sidebar}</aside>

        {mobileNavOpen ? (
          <div className="fixed inset-0 z-40 flex md:hidden">
            <div className="animate-fade-in">{sidebar}</div>
            <button
              type="button"
              className="flex-1 bg-black/50"
              aria-label="Close navigation"
              onClick={() => setMobileNavOpen(false)}
            />
          </div>
        ) : null}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-11 shrink-0 items-center gap-3 border-b border-line bg-panel/60 px-3 backdrop-blur">
            <button
              type="button"
              onClick={() => setMobileNavOpen(true)}
              className="flex size-7 items-center justify-center rounded text-muted hover:bg-elevated hover:text-ink md:hidden"
              aria-label="Open navigation"
            >
              <Menu className="size-4" />
            </button>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h1 className="truncate text-sm font-semibold tracking-tight">{title}</h1>
                {meta.data ? (
                  <Badge tone={meta.data.environment === "production" ? "accent" : "neutral"}>
                    {meta.data.environment}
                  </Badge>
                ) : null}
              </div>
            </div>

            <button
              type="button"
              onClick={() => openPalette(true)}
              className="hidden h-7 w-64 items-center gap-2 rounded border border-line bg-canvas px-2 text-left text-xs text-muted transition-colors hover:border-muted/50 hover:text-ink sm:flex"
            >
              <Search className="size-3.5" aria-hidden="true" />
              <span className="flex-1">Search symbols or commands</span>
              <span className="flex items-center gap-0.5">
                <span className="kbd">
                  <Command className="size-2.5" />
                </span>
                <span className="kbd">K</span>
              </span>
            </button>
            <button
              type="button"
              onClick={() => openPalette(true)}
              className="flex size-7 items-center justify-center rounded text-muted hover:bg-elevated hover:text-ink sm:hidden"
              aria-label="Search symbols or commands"
            >
              <Search className="size-4" />
            </button>

            <ThemeToggle />
            <div
              className="flex size-6 items-center justify-center rounded-full border border-line bg-elevated font-mono text-2xs font-semibold text-ink"
              title="Signed out"
            >
              AF
            </div>
          </header>

          <main id="main-content" className="min-h-0 flex-1 overflow-y-auto">
            <Outlet />
          </main>

          <footer className="flex h-6 shrink-0 items-center justify-between border-t border-line bg-panel px-3 text-2xs text-muted">
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5">
                <StatusDot status={apiStatus} />
                {readiness.isError
                  ? "API unreachable"
                  : readiness.data
                    ? readiness.data.status.replace("_", " ")
                    : "connecting"}
              </span>
              <span className="hidden items-center gap-1 sm:flex">local · single node</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="hidden md:inline">Data may be delayed · Not investment advice</span>
              <UtcClock />
            </div>
          </footer>
        </div>
      </div>

      <CommandPalette />
    </div>
  );
}
