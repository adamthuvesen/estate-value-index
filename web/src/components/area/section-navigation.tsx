"use client";

import { useState, useEffect } from "react";
import { AREA_SECTIONS } from "@/components/area/section-registry";

interface SectionNavigationProps {
  areaName: string;
}

const sections = [
  { id: "overview", label: "Overview" },
  ...AREA_SECTIONS.map(({ id, title }) => ({ id, label: title })),
];

export function SectionNavigation({ areaName }: SectionNavigationProps) {
  const [activeSection, setActiveSection] = useState("overview");
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsVisible(window.scrollY > 300);

      const scrollPosition = window.scrollY + 100;
      for (const section of sections) {
        const element = document.getElementById(section.id);
        if (element) {
          const { offsetTop, offsetHeight } = element;
          if (scrollPosition >= offsetTop && scrollPosition < offsetTop + offsetHeight) {
            setActiveSection(section.id);
            break;
          }
        }
      }
    };

    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const scrollToSection = (sectionId: string) => {
    const element = document.getElementById(sectionId);
    if (element) {
      const offset = 80;
      const elementPosition = element.getBoundingClientRect().top;
      const offsetPosition = elementPosition + window.pageYOffset - offset;

      window.scrollTo({
        top: offsetPosition,
        behavior: "smooth",
      });
    }
  };

  if (!isVisible) return null;

  return (
    <div className="sticky top-4 z-40 mb-6">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="ledger-card p-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h3 className="text-[13px] font-semibold text-ledger-text">{areaName}</h3>
            </div>
            <nav className="hidden md:block">
              <ul className="flex gap-1">
                {sections.map((section) => (
                  <li key={section.id}>
                    <button
                      onClick={() => scrollToSection(section.id)}
                      className={`rounded-pill px-3 py-1.5 text-[13px] font-medium transition-colors ${
                        activeSection === section.id
                          ? "bg-ledger-text text-white"
                          : "text-ledger-muted hover:bg-ledger-elevated hover:text-ledger-text"
                      }`}
                    >
                      {section.label}
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
            <div className="md:hidden">
              <button className="ledger-btn-primary px-3 py-1.5 text-[13px]">
                Jump to section
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
