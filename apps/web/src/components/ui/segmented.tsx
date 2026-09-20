"use client";

import * as ToggleGroupPrimitive from "@radix-ui/react-toggle-group";

import { cn } from "@/lib/utils";

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  title?: string;
}

/**
 * Single-choice segmented control (camera mode, replay speed, column mode).
 * Keeps the current value when the user clicks the active segment.
 */
export function Segmented<T extends string>({
  value,
  onValueChange,
  options,
  ariaLabel,
  className,
  size = "sm",
}: {
  value: T;
  onValueChange: (value: T) => void;
  options: readonly SegmentedOption<T>[];
  ariaLabel: string;
  className?: string;
  size?: "xs" | "sm";
}) {
  return (
    <ToggleGroupPrimitive.Root
      type="single"
      value={value}
      aria-label={ariaLabel}
      onValueChange={(next) => {
        if (next) onValueChange(next as T);
      }}
      className={cn(
        "inline-flex items-stretch overflow-hidden rounded-sm border border-border-strong bg-panel-2",
        className,
      )}
    >
      {options.map((option) => (
        <ToggleGroupPrimitive.Item
          key={option.value}
          value={option.value}
          title={option.title}
          className={cn(
            "border-r border-border px-2 font-medium text-muted transition-colors last:border-r-0 hover:text-foreground data-[state=on]:bg-info-soft data-[state=on]:text-info",
            size === "xs" ? "h-5 text-[10.5px]" : "h-6 text-[11.5px]",
          )}
        >
          {option.label}
        </ToggleGroupPrimitive.Item>
      ))}
    </ToggleGroupPrimitive.Root>
  );
}
