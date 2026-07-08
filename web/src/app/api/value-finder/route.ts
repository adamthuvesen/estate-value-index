import { NextRequest, NextResponse } from "next/server";
import {
  VALUE_TIERS,
  type SortField,
  type SortOrder,
  type ValueFinderFilters,
  type ValueFinderResponse,
  type ValueProperty,
  type ValueTier,
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

const SORT_FIELDS: readonly SortField[] = [
  "value_score",
  "prediction_delta_percentage",
  "prediction_delta_absolute",
  "sold_date",
  "sold_price",
  "living_area",
];
const SORT_ORDERS: readonly SortOrder[] = ["asc", "desc"];
const MAX_LIMIT = 200;

class QueryValidationError extends Error {}

function badRequest(message: string) {
  return NextResponse.json({ error: message }, { status: 400 });
}

function parseArrayParam(param: string | null): string[] | undefined {
  if (!param) return undefined;
  return param.split(",").map((s) => s.trim()).filter(Boolean);
}

function parseNumberParam(
  params: URLSearchParams,
  name: string,
  options: {
    integer?: boolean;
    min?: number;
    max?: number;
  } = {},
): number | undefined {
  const param = params.get(name);
  if (param === null || param.trim() === "") return undefined;
  const num = Number(param);
  if (!Number.isFinite(num)) {
    throw new QueryValidationError(`${name} must be a finite number`);
  }
  if (options.integer && !Number.isInteger(num)) {
    throw new QueryValidationError(`${name} must be an integer`);
  }
  if (options.min !== undefined && num < options.min) {
    throw new QueryValidationError(`${name} must be at least ${options.min}`);
  }
  if (options.max !== undefined && num > options.max) {
    throw new QueryValidationError(`${name} must be at most ${options.max}`);
  }
  return num;
}

function parseBooleanParam(params: URLSearchParams, name: string): boolean | undefined {
  const param = params.get(name);
  if (param === null || param.trim() === "") return undefined;
  const token = param.toLowerCase();
  if (token === "true") return true;
  if (token === "false") return false;
  throw new QueryValidationError(`${name} must be true or false`);
}

function parseSortField(param: string | null): SortField {
  if (!param) return "value_score";
  if (!SORT_FIELDS.includes(param as SortField)) {
    throw new QueryValidationError(`sort must be one of: ${SORT_FIELDS.join(", ")}`);
  }
  return param as SortField;
}

function parseSortOrder(param: string | null): SortOrder {
  if (!param) return "desc";
  if (!SORT_ORDERS.includes(param as SortOrder)) {
    throw new QueryValidationError("order must be asc or desc");
  }
  return param as SortOrder;
}

function parseValueTiers(param: string | null): ValueTier[] | undefined {
  const values = parseArrayParam(param);
  if (!values) return undefined;
  const allowed = new Set<ValueTier>(VALUE_TIERS);
  const invalid = values.filter((tier) => !allowed.has(tier as ValueTier));
  if (invalid.length > 0) {
    throw new QueryValidationError(`value_tier contains unknown value: ${invalid[0]}`);
  }
  return values as ValueTier[];
}

function parseFilters(searchParams: URLSearchParams): ValueFinderFilters {
  return {
    sort: parseSortField(searchParams.get("sort")),
    order: parseSortOrder(searchParams.get("order")),
    limit: parseNumberParam(searchParams, "limit", {
      integer: true,
      min: 1,
      max: MAX_LIMIT,
    }) ?? 50,
    offset: parseNumberParam(searchParams, "offset", { integer: true, min: 0 }) ?? 0,

    area: parseArrayParam(searchParams.get("area")),
    min_living_area: parseNumberParam(searchParams, "min_living_area", { min: 0 }),
    max_living_area: parseNumberParam(searchParams, "max_living_area", { min: 0 }),
    min_rooms: parseNumberParam(searchParams, "min_rooms", { min: 0 }),
    max_rooms: parseNumberParam(searchParams, "max_rooms", { min: 0 }),
    min_price: parseNumberParam(searchParams, "min_price", { min: 0 }),
    max_price: parseNumberParam(searchParams, "max_price", { min: 0 }),
    property_type: parseArrayParam(searchParams.get("property_type")),
    has_elevator: parseBooleanParam(searchParams, "has_elevator"),
    has_balcony: parseBooleanParam(searchParams, "has_balcony"),

    min_value_score: parseNumberParam(searchParams, "min_value_score", { min: 0 }),
    max_value_score: parseNumberParam(searchParams, "max_value_score", { min: 0 }),
    value_tier: parseValueTiers(searchParams.get("value_tier")),

    search: searchParams.get("search") || undefined,
  };
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
    const searchParams = request.nextUrl.searchParams;
    const filters = parseFilters(searchParams);
    const data = await getValueAnalysisData();

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
    if (error instanceof QueryValidationError) {
      return badRequest(error.message);
    }

    console.error("Error in value-finder API:", error);

    return isValueAnalysisDataMissingError(error)
      ? valueAnalysisDataMissingResponse()
      : valueAnalysisDataErrorResponse();
  }
}
