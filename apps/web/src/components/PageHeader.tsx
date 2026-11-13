import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        {eyebrow ? (
          <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-accent">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="mt-0.5 text-lg font-semibold tracking-tight text-ink">{title}</h1>
        {description ? (
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-muted">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}
