"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type {
  ListingPrefillResponse,
  PredictionInput,
  PredictionResult,
  SampleListing,
} from "@/lib/prediction-types";

export interface UsePredictionOptions {
  sampleListings: SampleListing[];
  defaultAreas: string[];
  modelLabels: Record<string, string>;
}

function normalizeRooms(value: number | null | undefined): string | null {
  if (value == null || Number.isNaN(value)) {
    return null;
  }
  if (value < 1) {
    return "1";
  }
  if (value >= 5) {
    return "5";
  }
  return String(Math.round(value));
}

export function usePrediction({
  sampleListings,
  defaultAreas,
  modelLabels,
}: UsePredictionOptions) {
  const defaultSample = sampleListings[0]?.data;
  const [formData, setFormData] = useState<PredictionInput>(
    () => ({
      ...(defaultSample ?? {
        listing_id: "",
        listing_price: "",
        living_area: "",
        rooms: "2",
        monthly_fee: "",
        days_on_market: "30",
        construction_year: "",
        property_type: "Lägenhet",
        area: defaultAreas[0] ?? "Södermalm",
        model: "auto",
        floor: "",
        elevator: "",
        balcony: "",
        latitude: "",
        longitude: "",
      }),
    })
  );
  const [listingUrl, setListingUrl] = useState("");
  const [areaOptions, setAreaOptions] = useState<string[]>(() => {
    const unique = new Set(defaultAreas);
    if (formData.area) {
      unique.add(formData.area);
    }
    return Array.from(unique);
  });
  const [prediction, setPrediction] = useState<PredictionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedSampleIndex, setSelectedSampleIndex] = useState(0);
  const [isPrefilling, setIsPrefilling] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isApiReady, setIsApiReady] = useState(false);

  const prefillController = useRef<AbortController | null>(null);
  const predictController = useRef<AbortController | null>(null);

  const currencyFormatter = useMemo(
    () =>
      new Intl.NumberFormat("sv-SE", {
        style: "currency",
        currency: "SEK",
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }),
    []
  );

  const handleFieldChange = (field: keyof PredictionInput, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSampleLoad = (index: number) => {
    if (!sampleListings[index]) {
      return;
    }
    setSelectedSampleIndex(index);
    setFormData({ ...sampleListings[index].data });
    setPrediction(null);
    setError(null);
    const sampleArea = sampleListings[index].data.area;
    if (sampleArea) {
      setAreaOptions((prev) => (prev.includes(sampleArea) ? prev : [...prev, sampleArea]));
    }
  };

  const handlePrefillFromUrl = async () => {
    const trimmedUrl = listingUrl.trim();
    if (!trimmedUrl) {
      setError("Provide a Booli listing URL to prefill the form.");
      return;
    }

    prefillController.current?.abort();
    const controller = new AbortController();
    prefillController.current = controller;

    setIsPrefilling(true);
    setError(null);

    try {
      const response = await fetch("/api/fetch-listing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: trimmedUrl }),
        signal: controller.signal,
      });

      const payload: ListingPrefillResponse = await response.json();

      if (!response.ok || payload.error) {
        throw new Error(payload.error || "Failed to fetch listing data");
      }

      const normalizedRooms = normalizeRooms(payload.rooms ?? null);

      setFormData((prev) => ({
        ...prev,
        listing_id: payload.listing_id ?? prev.listing_id,
        listing_price:
          payload.listing_price != null
            ? String(Math.round(payload.listing_price))
            : prev.listing_price,
        living_area:
          payload.living_area != null ? String(payload.living_area) : prev.living_area,
        rooms: normalizedRooms ?? prev.rooms,
        monthly_fee:
          payload.monthly_fee != null
            ? String(Math.round(payload.monthly_fee))
            : prev.monthly_fee,
        days_on_market:
          payload.days_on_market != null
            ? String(Math.round(payload.days_on_market))
            : prev.days_on_market,
        construction_year:
          payload.construction_year != null
            ? String(Math.round(payload.construction_year))
            : prev.construction_year,
        property_type: payload.property_type ?? prev.property_type,
        area: payload.area ?? prev.area,
        floor: payload.floor != null ? String(payload.floor) : prev.floor,
        elevator:
          payload.elevator != null
            ? String(payload.elevator)
            : prev.elevator,
        balcony:
          payload.balcony != null
            ? String(payload.balcony)
            : prev.balcony,
        latitude: payload.latitude != null ? String(payload.latitude) : prev.latitude,
        longitude: payload.longitude != null ? String(payload.longitude) : prev.longitude,
      }));

      if (payload.area) {
        const areaText = payload.area;
        setAreaOptions((prev) => (prev.includes(areaText) ? prev : [...prev, areaText]));
      }

      setPrediction(null);
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        return;
      }
      setError(err instanceof Error ? err.message : "Prefill failed");
    } finally {
      if (prefillController.current === controller) {
        setIsPrefilling(false);
        prefillController.current = null;
      }
    }
  };

  useEffect(() => {
    let mounted = true;
    const checkApi = async () => {
      try {
        const response = await fetch("/api/predict", { method: "GET" });
        if (mounted && response.ok) {
          setIsApiReady(true);
        }
      } catch (err) {
        console.warn("API not ready yet:", err);
        if (mounted) {
          setTimeout(checkApi, 1000);
        }
      }
    };

    checkApi();

    return () => {
      mounted = false;
      prefillController.current?.abort();
      predictController.current?.abort();
    };
  }, []);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!isApiReady) {
      setError("Prediction service is starting up. Please wait a moment and try again.");
      return;
    }

    predictController.current?.abort();
    const controller = new AbortController();
    predictController.current = controller;

    setIsLoading(true);
    setError(null);
    setPrediction(null);

    try {
      const requestData = {
        ...formData,
        municipality: "Stockholm",
      };

      const response = await fetch("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestData),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({ error: "Prediction failed" }));
        throw new Error(errorPayload.error || "Prediction failed");
      }

      const result = (await response.json()) as PredictionResult;
      setPrediction(result);
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        return;
      }
      const errorMessage = err instanceof Error ? err.message : "Prediction failed";
      if (errorMessage.includes("fetch failed") || errorMessage.includes("ECONNREFUSED")) {
        setError("Prediction service unavailable. Please ensure the prediction API server is running.");
      } else {
        setError(errorMessage);
      }
    } finally {
      if (predictController.current === controller) {
        setIsLoading(false);
        predictController.current = null;
      }
    }
  };


  const resolvedModelKey = (() => {
    if (prediction?.model_id) {
      return prediction.model_id;
    }
    return formData.model || "auto";
  })();

  const modelLabel = modelLabels[resolvedModelKey] ?? modelLabels[formData.model] ?? "Auto";

  const listingPriceValue = Number(formData.listing_price || 0);
  const displayedEstimateValue = prediction?.rounded_predicted_price ?? prediction?.predicted_price ?? null;
  const anchorPrice = prediction?.input_data.listing_price ?? listingPriceValue;
  const priceDifference = displayedEstimateValue !== null && anchorPrice > 0
    ? displayedEstimateValue - anchorPrice
    : null;
  const differencePercent = priceDifference !== null && anchorPrice > 0
    ? (priceDifference / anchorPrice) * 100
    : null;
  const isAboveAsking = priceDifference !== null ? priceDifference > 0 : null;

  return {
    formData,
    listingUrl,
    setListingUrl,
    areaOptions,
    prediction,
    error,
    selectedSampleIndex,
    isPrefilling,
    isLoading,
    isApiReady,
    currencyFormatter,
    handleFieldChange,
    handleSampleLoad,
    handlePrefillFromUrl,
    handleSubmit,
    modelLabel,
    priceDifference,
    differencePercent,
    isAboveAsking,
    sampleListings,
  };
}
