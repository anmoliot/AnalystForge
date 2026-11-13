import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
  id,
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cn("panel flex min-w-0 flex-col", className)}>
      {title ? (
        <header className="panel-header">
          <div className="flex min-w-0 items-baseline gap-2">
            <h2 className="panel-title">{title}</h2>
            {subtitle ? <span className="truncate text-2xs text-muted">{subtitle}</span> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-1">{actions}</div> : null}
        </header>
      ) : null}
      <div className={cn("min-h-0 flex-1", bodyClassName)}>{children}</div>
    </section>
  );
}
