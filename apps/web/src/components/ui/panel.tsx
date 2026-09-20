import { cn } from "@/lib/utils";

export function Panel({
  className,
  as: Tag = "section",
  ...props
}: React.HTMLAttributes<HTMLElement> & { as?: "section" | "div" | "article" | "aside" }) {
  return <Tag className={cn("panel flex min-h-0 flex-col", className)} {...props} />;
}

export function PanelHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex h-7 shrink-0 items-center gap-2 border-b border-border px-3", className)}
      {...props}
    />
  );
}

export function PanelTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("panel-title", className)} {...props} />;
}

export function PanelBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("min-h-0 flex-1 p-3", className)} {...props} />;
}

/** A label above a dense value, used across status bars and KPI panels. */
export function Field({
  label,
  children,
  className,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
  hint?: string;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-0.5", className)} title={hint}>
      <span className="panel-title text-[9.5px]">{label}</span>
      <span className="truncate text-[12px] text-foreground">{children}</span>
    </div>
  );
}
