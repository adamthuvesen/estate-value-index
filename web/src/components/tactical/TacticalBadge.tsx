import { ReactNode } from "react";

interface TacticalBadgeProps {
  children: ReactNode;
  variant?: "active" | "inactive" | "alert" | "success";
  pulse?: boolean;
  className?: string;
}

const variantClasses = {
  active: "tactical-badge-active",
  inactive: "tactical-badge-inactive",
  alert: "tactical-badge-alert",
  success: "tactical-badge border-tactical-success text-tactical-success",
};

export function TacticalBadge({
  children,
  variant = "inactive",
  pulse = false,
  className = "",
}: TacticalBadgeProps) {
  const pulseClass = pulse && variant === "active" ? "" : pulse ? "animate-glow-pulse" : "";

  return (
    <span className={`${variantClasses[variant]} ${pulseClass} ${className}`}>
      {children}
    </span>
  );
}
