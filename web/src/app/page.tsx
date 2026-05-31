"use client";

import { useEffect, useState } from "react";
import PredictionApp from "@/components/prediction-app";
import { MODEL_LABELS, SAMPLE_LISTINGS } from "@/lib/sample-data";

export default function HomePage() {
  const [areas, setAreas] = useState<string[]>([]);
  const [isLoadingAreas, setIsLoadingAreas] = useState(true);

  useEffect(() => {
    const fetchAreas = async () => {
      try {
        const response = await fetch("/api/area");
        if (response.ok) {
          const data = await response.json();
          const areaNames = data.areas
            .map((area: { display_name: string }) => area.display_name)
            .sort((a: string, b: string) => a.localeCompare(b, "sv"));
          setAreas(areaNames);
        }
      } catch (error) {
        console.error("Failed to fetch areas:", error);
        setAreas(["Södermalm", "Östermalm", "Kungsholmen", "Vasastan", "Norrmalm", "Gamla Stan"]);
      } finally {
        setIsLoadingAreas(false);
      }
    };

    fetchAreas();
  }, []);

  return (
    <main className="min-h-screen bg-tactical-bg">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="border border-tactical-border bg-tactical-surface p-6 sm:p-8 lg:p-10 relative">
          <div className="absolute top-[-1px] left-[-1px] w-8 h-8 border-t-2 border-l-2 border-tactical-accent pointer-events-none" />
          <div className="absolute top-[-1px] right-[-1px] w-8 h-8 border-t-2 border-r-2 border-tactical-accent pointer-events-none" />

          <header className="text-center mb-10 space-y-3">
            <p className="tactical-label">CLASSIFIED // ESTATE VALUE INDEX</p>
            <h1 className="text-4xl font-bold tracking-tactical text-tactical-text sm:text-5xl font-mono">
              PROPERTY VALUATION SYSTEM
            </h1>
            <p className="mx-auto mt-4 max-w-2xl text-sm text-tactical-muted font-mono leading-relaxed">
              DEPLOY MACHINE LEARNING MODELS TO ESTIMATE MARKET VALUE // IMPORT BOOLI LISTING OR
              MANUALLY CONFIGURE PARAMETERS TO EXECUTE PREDICTION SCENARIOS
            </p>
          </header>

          {!isLoadingAreas && (
            <PredictionApp
              sampleListings={SAMPLE_LISTINGS}
              defaultAreas={areas}
              modelLabels={MODEL_LABELS}
            />
          )}

          {isLoadingAreas && (
            <div className="text-center py-12">
              <p className="tactical-label">LOADING AREAS...</p>
            </div>
          )}

          <div className="absolute bottom-[-1px] left-[-1px] w-8 h-8 border-b-2 border-l-2 border-tactical-accent pointer-events-none" />
          <div className="absolute bottom-[-1px] right-[-1px] w-8 h-8 border-b-2 border-r-2 border-tactical-accent pointer-events-none" />
        </div>
      </div>
    </main>
  );
}
