import { ArrowUpRight, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";

export function ModuleScaffold({
  icon: Icon,
  title,
  description,
  capabilities,
  status,
  actions,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  capabilities: string[];
  status: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-4 p-4">
      <PageHeader
        title={title}
        description={description}
        actions={
          actions ?? (
            <Link to="/">
              <Button variant="secondary" size="sm">
                Workspace overview <ArrowUpRight className="size-3.5" aria-hidden="true" />
              </Button>
            </Link>
          )
        }
      />
      <Panel title="Module status">
        <div className="flex flex-col items-center gap-4 px-6 py-12 text-center">
          <div className="flex size-10 items-center justify-center rounded-full border border-line bg-elevated">
            <Icon className="size-5 text-accent" aria-hidden="true" />
          </div>
          <div className="max-w-xl space-y-1.5">
            <p className="text-sm font-medium text-ink">No data is available in this workspace</p>
            <p className="text-xs leading-relaxed text-muted">{status}</p>
          </div>
          <ul className="grid w-full max-w-2xl gap-px overflow-hidden rounded border border-line bg-line text-left sm:grid-cols-2">
            {capabilities.map((capability) => (
              <li key={capability} className="bg-panel px-3 py-2 text-xs text-muted">
                {capability}
              </li>
            ))}
          </ul>
        </div>
      </Panel>
    </div>
  );
}
