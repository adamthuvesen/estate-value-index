import { NextRequest, NextResponse } from "next/server";
import type {
  ValueProperty,
  ValueFinderFilters,
  ValueFinderResponse,
  SortField,
  SortOrder,
  ValueTier,
} from "@/lib/value-finder-types";
import { getValueAnalysisData } from "@/lib/value-analysis-cache";
import {
  isValueAnalysisDataMissingError,
  valueAnalysisDataErrorResponse,
  valueAnalysisDataMissingResponse,
} from "@/lib/api-errors";

// Lock to the Node runtime: this route imports `@google-cloud/storage` and
// `fs/promises` (transitively via `loadDataFile`), neither of which are
// available on the Edge runtime.
export const runtime = "nodejs";

function parseArrayParam(param: string | null): string[] | undefined {
  if (!param) return undefined;
  return param.split(",").map((s) => s.trim()).filter(Boolean);
}

function parseNumberParam(param: string | null): number | undefined {
  if (!param) return undefined;
  const num = Number(param);
  return isNaN(num) ? undefined : num;
}

function parseBooleanParam(param: string | null): boolean | undefined {
  if (!param) return undefined;
  return param.toLowerCase() === "true";
}

type Predicate = (property: ValueProperty) => boolean;

function buildPredicates(filters: ValueFinderFilters): Predicate[] {
  const predicates: Predicate[] = [];

  if (filters.value_tier) {
    const tiers = new Set(
      Array.isArray(filters.value_tier) ? filters.value_tier : [filters.value_tier]
    );
    predicates.push((p) => p.value_tier !== null && tiers.has(p.value_tier));
  }

  if (filters.area) {
    const areas = new Set(Array.isArray(filters.area) ? filters.area : [filters.area]);
    predicates.push((p) => areas.has(p.area));
  }

  if (filters.property_type) {
    const types = new Set(
      Array.isArray(filters.property_type) ? filters.property_type : [filters.property_type]
    );
    predicates.push((p) => types.has(p.property_type));
  }

  if (filters.min_living_area !== undefined) {
    const min = filters.min_living_area;
    predicates.push((p) => p.living_area >= min);
  }
  if (filters.max_living_area !== undefined) {
    const max = filters.max_living_area;
    predicates.push((p) => p.living_area <= max);
  }
  if (filters.min_rooms !== undefined) {
    const min = filters.min_rooms;
    predicates.push((p) => p.rooms >= min);
  }
  if (filters.max_rooms !== undefined) {
    const max = filters.max_rooms;
    predicates.push((p) => p.rooms <= max);
  }
  if (filters.min_price !== undefined) {
    const min = filters.min_price;
    predicates.push((p) => p.sold_price >= min);
  }
  if (filters.max_price !== undefined) {
    const max = filters.max_price;
    predicates.push((p) => p.sold_price <= max);
  }
  if (filters.has_elevator !== undefined) {
    const flag = filters.has_elevator;
    predicates.push((p) => p.elevator === flag);
  }
  if (filters.has_balcony !== undefined) {
    const flag = filters.has_balcony;
    predicates.push((p) => p.balcony === flag);
  }
  if (filters.min_value_score !== undefined) {
    const min = filters.min_value_score;
    predicates.push((p) => p.value_score !== null && p.value_score >= min);
  }
  if (filters.max_value_score !== undefined) {
    const max = filters.max_value_score;
    predicates.push((p) => p.value_score !== null && p.value_score <= max);
  }

  if (filters.search) {
    const needle = filters.search.toLowerCase();
    predicates.push(
      (p) =>
        p.address.toLowerCase().includes(needle) ||
        p.area.toLowerCase().includes(needle) ||
        p.municipality.toLowerCase().includes(needle)
    );
  }

  return predicates;
}

function applyFilters(properties: ValueProperty[], filters: ValueFinderFilters): ValueProperty[] {
  const predicates = buildPredicates(filters);
  if (predicates.length === 0) return properties;
  return properties.filter((property) => predicates.every((pred) => pred(property)));
}

function applySorting(
  properties: ValueProperty[],
  sortField: SortField = "value_score",
  sortOrder: SortOrder = "desc"
): ValueProperty[] {
  const sorted = [...properties];

  sorted.sort((a, b) => {
    let aVal: number | string | null;
    let bVal: number | string | null;

    switch (sortField) {
      case "value_score":
        aVal = a.value_score;
        bVal = b.value_score;
        break;
      case "prediction_delta_percentage":
        aVal = a.prediction_delta_percentage;
        bVal = b.prediction_delta_percentage;
        break;
      case "prediction_delta_absolute":
        aVal = a.prediction_delta_absolute;
        bVal = b.prediction_delta_absolute;
        break;
      case "sold_date":
        aVal = a.sold_date;
        bVal = b.sold_date;
        break;
      case "sold_price":
        aVal = a.sold_price;
        bVal = b.sold_price;
        break;
      case "living_area":
        aVal = a.living_area;
        bVal = b.living_area;
        break;
      default:
        aVal = a.value_score;
        bVal = b.value_score;
    }

    if (aVal === null && bVal === null) return 0;
    if (aVal === null) return 1;
    if (bVal === null) return -1;

    if (aVal < bVal) return sortOrder === "asc" ? -1 : 1;
    if (aVal > bVal) return sortOrder === "asc" ? 1 : -1;
    return 0;
  });

  return sorted;
}

export async function GET(request: NextRequest) {
  try {
    const data = await getValueAnalysisData();

    const searchParams = request.nextUrl.searchParams;

    const filters: ValueFinderFilters = {
      sort: (searchParams.get("sort") as SortField) || "value_score",
      order: (searchParams.get("order") as SortOrder) || "desc",
      limit: parseNumberParam(searchParams.get("limit")) || 50,
      offset: parseNumberParam(searchParams.get("offset")) || 0,

      area: parseArrayParam(searchParams.get("area")),
      min_living_area: parseNumberParam(searchParams.get("min_living_area")),
      max_living_area: parseNumberParam(searchParams.get("max_living_area")),
      min_rooms: parseNumberParam(searchParams.get("min_rooms")),
      max_rooms: parseNumberParam(searchParams.get("max_rooms")),
      min_price: parseNumberParam(searchParams.get("min_price")),
      max_price: parseNumberParam(searchParams.get("max_price")),
      property_type: parseArrayParam(searchParams.get("property_type")),
      has_elevator: parseBooleanParam(searchParams.get("has_elevator")),
      has_balcony: parseBooleanParam(searchParams.get("has_balcony")),

      min_value_score: parseNumberParam(searchParams.get("min_value_score")),
      max_value_score: parseNumberParam(searchParams.get("max_value_score")),
      value_tier: parseArrayParam(searchParams.get("value_tier")) as ValueTier[],

      search: searchParams.get("search") || undefined,
    };

    if (filters.limit && filters.limit > 200) {
      filters.limit = 200;
    }

    let properties = applyFilters(data.properties, filters);
    properties = applySorting(properties, filters.sort, filters.order);

    const total = properties.length;
    const offset = filters.offset || 0;
    const limit = filters.limit || 50;
    const totalPages = Math.ceil(total / limit);
    const page = Math.floor(offset / limit) + 1;

    const paginatedProperties = properties.slice(offset, offset + limit);

    const response: ValueFinderResponse = {
      total,
      page,
      page_size: limit,
      total_pages: totalPages,
      filters_applied: filters,
      metadata: data.metadata,
      properties: paginatedProperties,
    };

    return NextResponse.json(response, {
      headers: {
        "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600",
      },
    });
  } catch (error) {
    console.error("Error in value-finder API:", error);

    return isValueAnalysisDataMissingError(error)
      ? valueAnalysisDataMissingResponse()
      : valueAnalysisDataErrorResponse();
  }
}
