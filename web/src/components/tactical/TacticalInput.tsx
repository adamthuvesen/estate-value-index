import { InputHTMLAttributes, forwardRef } from "react";

interface TacticalInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const TacticalInput = forwardRef<HTMLInputElement, TacticalInputProps>(
  ({ label, error, className = "", ...props }, ref) => {
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label className="tactical-label">
            {label}
          </label>
        )}
        <input
          ref={ref}
          className={`tactical-input ${error ? "border-tactical-accent" : ""} ${className}`}
          {...props}
        />
        {error && (
          <span className="text-xs text-tactical-accent font-mono">
            {error}
          </span>
        )}
      </div>
    );
  }
);

TacticalInput.displayName = "TacticalInput";
