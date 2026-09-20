"use client";

import * as LabelPrimitive from "@radix-ui/react-label";
import * as SwitchPrimitive from "@radix-ui/react-switch";

import { cn } from "@/lib/utils";

export function Label({ className, ...props }: React.ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      className={cn("panel-title select-none text-[9.5px]", className)}
      {...props}
    />
  );
}

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-7 w-full rounded-sm border border-border-strong bg-panel-2 px-2 text-[12px] text-foreground placeholder:text-dim transition-colors hover:border-border-strong focus:border-info/60 disabled:opacity-45",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "w-full rounded-sm border border-border-strong bg-panel-2 px-2 py-1.5 text-[12px] leading-relaxed text-foreground placeholder:text-dim focus:border-info/60",
        className,
      )}
      {...props}
    />
  );
}

export function FormRow({
  label,
  htmlFor,
  hint,
  children,
  className,
}: {
  label: string;
  htmlFor?: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint ? <p className="text-[10.5px] leading-snug text-dim">{hint}</p> : null}
    </div>
  );
}

export function Switch({ className, ...props }: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      className={cn(
        "relative inline-flex h-4 w-7 shrink-0 items-center rounded-full border border-border-strong bg-panel-3 transition-colors data-[state=checked]:border-info/60 data-[state=checked]:bg-info-soft",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb className="block h-2.5 w-2.5 translate-x-[3px] rounded-full bg-dim transition-transform data-[state=checked]:translate-x-[14px] data-[state=checked]:bg-info" />
    </SwitchPrimitive.Root>
  );
}
