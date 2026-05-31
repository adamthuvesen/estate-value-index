import { ReactNode } from "react";

interface TacticalCardProps {
  children: ReactNode;
  className?: string;
  corners?: "all" | "tl" | "tr" | "bl" | "br" | "top" | "bottom" | "none";
  padding?: "sm" | "md" | "lg" | "xl";
}

const paddingClasses = {
  sm: "p-3",
  md: "p-5",
  lg: "p-6",
  xl: "p-8",
};

export function TacticalCard({
  children,
  className = "",
  corners = "none",
  padding = "md",
}: TacticalCardProps) {
  const cornerClasses = {
    all: "tactical-corners",
    tl: "tactical-card-corner-tl",
    tr: "tactical-card-corner-tr",
    bl: "tactical-card-corner-bl",
    br: "tactical-card-corner-br",
    top: "tactical-card-corner-tl tactical-card-corner-tr",
    bottom: "tactical-card-corner-bl tactical-card-corner-br",
    none: "",
  };

  return (
    <div
      className={`tactical-card ${paddingClasses[padding]} ${cornerClasses[corners]} ${className}`}
    >
      {children}
    </div>
  );
}
