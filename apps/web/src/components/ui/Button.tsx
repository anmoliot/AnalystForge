import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const variants: Record<Variant, string> = {
  primary:
    "bg-accent text-accent-ink hover:brightness-110 active:brightness-95 border border-transparent",
  secondary: "bg-elevated text-ink border border-line hover:border-muted/50 hover:bg-panel",
  ghost: "bg-transparent text-muted hover:bg-elevated hover:text-ink border border-transparent",
  danger: "bg-negative text-ink hover:brightness-110 border border-transparent",
};

const sizes: Record<Size, string> = {
  sm: "h-7 px-2.5 text-xs gap-1.5",
  md: "h-8 px-3 text-sm gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "secondary", size = "md", loading, disabled, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center rounded font-medium transition-colors disabled:pointer-events-none disabled:opacity-50",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {loading ? (
        <span
          aria-hidden="true"
          className="size-3.5 animate-spin rounded-full border border-current border-r-transparent"
        />
      ) : null}
      {children}
    </button>
  );
});
