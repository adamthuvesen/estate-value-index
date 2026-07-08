import PredictionApp from "@/components/prediction-app";
import { PageHero } from "@/components/ui/page-hero";
import { getAreaOverviewList } from "@/lib/area-overview";
import { MODEL_LABELS, SAMPLE_LISTINGS } from "@/lib/sample-data";

// Area names come from the per-request area-statistics cache, so render at request time
// rather than baking a snapshot into the static build.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const areas = await getAreaOverviewList();
  const areaNames = areas
    .map((area) => area.display_name)
    .sort((a, b) => a.localeCompare(b, "sv"));

  return (
    <main className="min-h-screen bg-ledger-bg">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14">
        <PageHero
          chapter="01"
          eyebrow="Predictor"
          title="What's this home worth?"
          lead="Import a Booli listing or enter the details, and the model estimates its market value from thousands of Stockholm sales."
        />

        <div className="mt-10 lg:mt-12">
          <PredictionApp
            sampleListings={SAMPLE_LISTINGS}
            defaultAreas={areaNames}
            modelLabels={MODEL_LABELS}
          />
        </div>
      </div>
    </main>
  );
}
