import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

interface FieldProps {
  label: string;
  required?: boolean;
  className?: string;
  children: ReactNode;
}

/** Label-over-control wrapper: eyebrow-weight caption label above a `.ledger-input`. */
export function Field({ label, required = false, className, children }: FieldProps) {
  return (
    <label className={cn("flex flex-col gap-1.5", className)}>
      <span className="text-caption font-medium text-ledger-muted">
        {label}
        {required && <span className="text-ledger-accent"> *</span>}
      </span>
      {children}
    </label>
  );
}
