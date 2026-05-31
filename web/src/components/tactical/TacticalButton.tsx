import { ButtonHTMLAttributes, ReactNode } from "react";

interface TacticalButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: "default" | "primary" | "alert" | "success";
  size?: "sm" | "md" | "lg";
}

const sizeClasses = {
  sm: "px-3 py-1.5 text-[10px]",
  md: "px-4 py-2 text-xs",
  lg: "px-6 py-3 text-sm",
};

const variantClasses = {
  default: "tactical-btn",
  primary: "tactical-btn-primary",
  alert: "tactical-btn border-tactical-accent text-tactical-accent hover:bg-tactical-accent hover:text-tactical-bg",
  success: "tactical-btn border-tactical-success text-tactical-success hover:bg-tactical-success hover:text-tactical-bg",
};

export function TacticalButton({
  children,
  variant = "default",
  size = "md",
  className = "",
  disabled,
  ...props
}: TacticalButtonProps) {
  return (
    <button
      className={`${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  );
}
