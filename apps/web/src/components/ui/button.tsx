"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 rounded-sm border font-medium transition-colors disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        primary: "border-info/50 bg-info-soft text-info hover:bg-info/25 hover:text-foreground",
        default:
          "border-border-strong bg-panel-2 text-foreground hover:border-info/50 hover:bg-panel-3",
        ghost: "border-transparent bg-transparent text-muted hover:bg-panel-2 hover:text-foreground",
        danger: "border-bad/50 bg-bad-soft text-bad hover:bg-bad/25 hover:text-foreground",
        outline: "border-border-strong bg-transparent text-muted hover:bg-panel-2 hover:text-foreground",
      },
      size: {
        xs: "h-6 px-2 text-[11px]",
        sm: "h-7 px-2.5 text-[12px]",
        md: "h-8 px-3 text-[12px]",
        lg: "h-9 px-4 text-[13px]",
        icon: "h-7 w-7",
      },
    },
    defaultVariants: { variant: "default", size: "sm" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export { buttonVariants };
