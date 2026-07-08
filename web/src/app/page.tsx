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
    <main className="min-h-screen bg-ledger-bg">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14">
        <header className="mx-auto max-w-2xl text-center animate-fade-in-up">
          <p className="font-mono text-[12px] font-semibold uppercase tracking-eyebrow text-ledger-accent">
            Predictor
          </p>
          <h1 className="mt-3 text-4xl font-semibold leading-[1.06] tracking-tight text-ledger-text sm:text-[46px]">
            What&rsquo;s this home worth?
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-[15px] leading-relaxed text-ledger-muted">
            Import a Booli listing or enter the details, and the model estimates its market value
            from thousands of Stockholm sales.
          </p>
        </header>

        <div className="mt-10 lg:mt-12">
          {!isLoadingAreas && (
            <PredictionApp
              sampleListings={SAMPLE_LISTINGS}
              defaultAreas={areas}
              modelLabels={MODEL_LABELS}
            />
          )}

          {isLoadingAreas && (
            <div className="flex items-center justify-center py-24">
              <div className="flex flex-col items-center gap-3">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-ledger-border border-t-ledger-text" />
                <p className="text-[13px] text-ledger-muted">Loading areas…</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
