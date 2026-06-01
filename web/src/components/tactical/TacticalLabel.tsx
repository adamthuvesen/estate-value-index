import { ReactNode } from "react";

interface TacticalLabelProps {
  children: ReactNode;
  className?: string;
}

export function TacticalLabel({ children, className = "" }: TacticalLabelProps) {
  return (
    <div className={`tactical-label ${className}`}>
      {children}
    </div>
  );
}
