import { cn } from "@/lib/utils";

const tones = {
  ok: "bg-positive",
  warn: "bg-warning",
  error: "bg-negative",
  idle: "bg-muted/60",
} as const;

export function StatusDot({
  status,
  className,
  pulse = false,
}: {
  status: keyof typeof tones;
  className?: string;
  pulse?: boolean;
}) {
  return (
    <span
      role="img"
      aria-label={status}
      className={cn("inline-block size-1.5 shrink-0 rounded-full", tones[status], className)}
    >
      {pulse ? (
        <span className={cn("block size-1.5 animate-ping rounded-full", tones[status])} />
      ) : null}
    </span>
  );
}
