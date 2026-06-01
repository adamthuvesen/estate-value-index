/**
 * Parse Booli listing HTML / __NEXT_DATA__ payloads.
 * Boolean coercion matches `estate_value_index.ingestion.booli.normalization.to_bool`.
 */

export type JsonRecord = Record<string, unknown>;

export const LISTING_ID_PATTERNS = [/^\/(?:annons|bostad)\/(?:[^/]+\/)*?(\d+)\/?$/i];
export const LISTING_ID_QUERY_KEYS = ['booliid', 'listingid', 'objectid', 'id'];

const TRUTHY = new Set(['true', 't', 'yes', 'y', '1', 'ja']);
const FALSY = new Set(['false', 'f', 'no', 'n', '0', 'nej']);

export function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

/** Align with Python `to_bool` / `_coerce_nullable_bool` truth table. */
export function coerceBool(value: unknown): boolean | null {
  if (value == null) {
    return null;
  }
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number') {
    if (value === 1) return true;
    if (value === 0) return false;
    return null;
  }
  if (typeof value === 'string') {
    const token = value.trim().toLowerCase();
    if (TRUTHY.has(token)) return true;
    if (FALSY.has(token)) return false;
    return null;
  }
  return null;
}

export function extractNumber(value: unknown): number | null {
  if (value == null) {
    return null;
  }

  if (typeof value === 'number' && !Number.isNaN(value)) {
    return value;
  }

  if (typeof value === 'string') {
    const digits = value.replace(/[^0-9.,-]/g, '').replace(',', '.');
    const parsed = Number(digits);
    return Number.isNaN(parsed) ? null : parsed;
  }

  if (isRecord(value)) {
    if ('raw' in value) {
      const extracted = extractNumber(value.raw);
      if (extracted !== null) {
        return extracted;
      }
    }
    if ('value' in value) {
      return extractNumber(value.value);
    }
  }

  return null;
}

export function extractString(value: unknown): string | null {
  if (typeof value === 'string' && value.trim().length > 0) {
    return value.trim();
  }

  if (isRecord(value) && typeof value.value === 'string') {
    return value.value.trim();
  }

  return null;
}

export function extractFloorFromText(text: string): number | null {
  const normalized = text.toLowerCase();

  const groundPatterns = ['entreplan', 'entréplan', 'bottenplan', 'markplan', 'gatuplan'];
  for (const pattern of groundPatterns) {
    if (normalized.includes(pattern)) {
      return 0;
    }
  }

  const floorPatterns = [
    /våning\s*(\d+)/,
    /(\d+)\s*tr/,
    /(\d+):\s*an/,
    /plan\s*(\d+)/,
    /etage\s*(\d+)/,
    /(\d+)\s*våningar?\s+upp/,
  ];

  for (const pattern of floorPatterns) {
    const match = normalized.match(pattern);
    if (match) {
      return parseInt(match[1], 10);
    }
  }

  return null;
}

export function extractElevatorFromText(text: string, amenities: Set<string>): boolean | null {
  if (amenities.has('elevator')) return true;
  if (amenities.has('noelevator')) return false;

  const normalized = text.toLowerCase();

  const negativePatterns = ['utan hiss', 'saknar hiss', 'ingen hiss', 'hiss saknas', 'ej hiss'];
  for (const pattern of negativePatterns) {
    if (normalized.includes(pattern)) {
      return false;
    }
  }

  const positivePatterns = [
    'med hiss',
    'hiss finns',
    'tillgång till hiss',
    'hiss i huset',
    'hiss i fastigheten',
    'gemensam hiss',
  ];
  for (const pattern of positivePatterns) {
    if (normalized.includes(pattern)) {
      return true;
    }
  }

  if (normalized.includes('hiss')) {
    return true;
  }

  return null;
}

export function extractBalconyFromText(text: string, amenities: Set<string>): boolean | null {
  const balconyKeys = ['balcony', 'frenchbalcony', 'rooftopbalcony'];
  for (const key of balconyKeys) {
    if (amenities.has(key)) return true;
  }
  if (amenities.has('nobalcony')) return false;

  const normalized = text.toLowerCase();

  const negativePatterns = ['utan balkong', 'saknar balkong', 'ingen balkong', 'balkong saknas'];
  for (const pattern of negativePatterns) {
    if (normalized.includes(pattern)) {
      return false;
    }
  }

  const positivePatterns = [
    'med balkong',
    'har balkong',
    'egen balkong',
    'stor balkong',
    'liten balkong',
    'balkong ut mot',
    'solig balkong',
    'skyddad balkong',
    'fransk balkong',
    'franskt balkong',
  ];
  for (const pattern of positivePatterns) {
    if (normalized.includes(pattern)) {
      return true;
    }
  }

  if (normalized.match(/\bbalkong(er)?\b/)) {
    return true;
  }

  return null;
}

export function extractListingId(parsed: URL): string | null {
  for (const pattern of LISTING_ID_PATTERNS) {
    const match = parsed.pathname.match(pattern);
    if (match) {
      return match[1];
    }
  }
  for (const key of LISTING_ID_QUERY_KEYS) {
    const value = parsed.searchParams.get(key);
    if (value && /^\d+$/.test(value)) {
      return value;
    }
  }
  return null;
}

export type ParsedBooliListing = {
  listing_id: string;
  listing_price: number | null;
  living_area: number | null;
  rooms: number | null;
  monthly_fee: number | null;
  construction_year: number | null;
  days_on_market: number | null;
  property_type: string;
  municipality: string;
  area: string | null;
  floor: number | null;
  elevator: boolean | null;
  balcony: boolean | null;
  source_url: string;
};

export function parseBooliListingFromHtml(
  html: string,
  listingId: string,
  sourceUrl: string
): ParsedBooliListing | { error: string } {
  const nextDataMatch = html.match(
    /<script id="__NEXT_DATA__" type="application\/json">([\s\S]*?)<\/script>/
  );

  if (!nextDataMatch) {
    return { error: 'Could not find listing data on the page' };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(nextDataMatch[1]);
  } catch {
    return { error: 'Failed to parse listing data payload' };
  }

  if (!isRecord(parsed)) {
    return { error: 'Listing data payload missing expected structure' };
  }

  const propsRaw = parsed.props;
  const props = isRecord(propsRaw) ? propsRaw : undefined;
  const pagePropsRaw = props?.pageProps;
  const pageProps = isRecord(pagePropsRaw) ? pagePropsRaw : undefined;
  const apolloStateRaw = pageProps?.__APOLLO_STATE__;
  if (!isRecord(apolloStateRaw)) {
    return { error: 'Listing data payload missing expected structure' };
  }
  const apolloState = apolloStateRaw;

  const candidateKeys = [
    `Listing:${listingId}`,
    `SoldProperty:${listingId}`,
    `Property:${listingId}`,
    `Bostad:${listingId}`,
    `Ad:${listingId}`,
  ];
  let listingData: JsonRecord | null = null;

  for (const key of candidateKeys) {
    const candidate = apolloState[key];
    if (isRecord(candidate)) {
      listingData = candidate;
      break;
    }
  }

  if (!listingData) {
    const fallbackCandidate =
      Object.values(apolloState).find((candidate): candidate is JsonRecord => {
        if (!isRecord(candidate) || !listingId) {
          return false;
        }
        return ['booliId', 'id', 'listingId', 'residenceId'].some((key) => {
          const value = candidate[key];
          return typeof value === 'string' && value === listingId;
        });
      }) ?? null;

    if (fallbackCandidate) {
      listingData = fallbackCandidate;
    }
  }

  if (!listingData) {
    for (const [, value] of Object.entries(apolloState)) {
      if (isRecord(value) && listingId) {
        const residenceId = value.residenceId;
        if (typeof residenceId === 'string' && residenceId === listingId) {
          listingData = value;
          break;
        }
      }
    }
  }

  if (!listingData) {
    return { error: 'Unable to resolve structured listing data' };
  }

  const listingPrice = extractNumber(listingData.listPrice);
  const livingArea = extractNumber(listingData.livingArea);
  const rooms = extractNumber(listingData.rooms);
  const monthlyFee = extractNumber(listingData.rent);
  const constructionYear = extractNumber(listingData.constructionYear);

  let daysOnMarket: number | null = null;

  if (listingData.infoSections && Array.isArray(listingData.infoSections) && listingData.infoSections.length > 0) {
    const infoSection = listingData.infoSections[0];

    if (isRecord(infoSection) && isRecord(infoSection.content) && infoSection.content.infoPoints) {
      const infoPoints = infoSection.content.infoPoints;
      if (Array.isArray(infoPoints)) {
        const daysActivePoint = infoPoints.find(
          (point: unknown) => isRecord(point) && point.key === 'daysActive'
        );

        if (
          isRecord(daysActivePoint) &&
          isRecord(daysActivePoint.displayText) &&
          typeof daysActivePoint.displayText.markdown === 'string'
        ) {
          const markdown = daysActivePoint.displayText.markdown;
          const daysMatch = markdown.match(/Bostaden har varit till salu i \*\*(\d+)\*\* dagar?/i);
          if (daysMatch) {
            daysOnMarket = extractNumber(daysMatch[1]);
          }
        }
      }
    }
  }

  const primaryAreaName = isRecord(listingData.primaryArea)
    ? extractString(listingData.primaryArea.name)
    : null;
  const locationNamedArea =
    isRecord(listingData.location) && Array.isArray(listingData.location.namedAreas)
      ? extractString(listingData.location.namedAreas[0])
      : null;
  const area = primaryAreaName || locationNamedArea || extractString(listingData.descriptiveAreaName);

  const municipalityName =
    isRecord(listingData.location) && isRecord(listingData.location.region)
      ? extractString(listingData.location.region.municipalityName)
      : null;
  const municipality = municipalityName || 'Stockholm';
  const propertyType = extractString(listingData.objectType) || 'Lägenhet';

  let finalDaysOnMarket = daysOnMarket;

  if (finalDaysOnMarket === null) {
    const patterns = [
      /Bostaden\s+har\s+varit\s+till\s+salu\s+i\s+<strong>(\d+)<\/strong>\s+dag(?:ar)?\b/i,
      /till\s+salu\s+i\s+<strong>(\d+)<\/strong>\s+dag(?:ar)?\b/i,
      /<strong>(\d+)<\/strong>\s+dag(?:ar)?\b/i,
    ];

    for (const pattern of patterns) {
      const match = html.match(pattern);
      if (match) {
        finalDaysOnMarket = parseInt(match[1], 10);
        break;
      }
    }
  }

  let floor: number | null =
    extractNumber(listingData.floor) ?? extractNumber(listingData.floorNumber);
  let elevator: boolean | null = coerceBool(listingData.hasElevator);
  let balcony: boolean | null = coerceBool(listingData.hasBalcony);

  const amenities = new Set<string>();
  if (listingData.amenities && Array.isArray(listingData.amenities)) {
    for (const amenity of listingData.amenities) {
      if (typeof amenity === 'string') {
        amenities.add(amenity.toLowerCase());
      } else if (isRecord(amenity) && typeof amenity.key === 'string') {
        amenities.add(amenity.key.toLowerCase());
      }
    }
  }

  const infoTexts: string[] = [];
  if (listingData.infoSections && Array.isArray(listingData.infoSections)) {
    for (const section of listingData.infoSections) {
      if (isRecord(section) && isRecord(section.content)) {
        const content = section.content;
        if (Array.isArray(content.infoPoints)) {
          for (const point of content.infoPoints) {
            if (isRecord(point)) {
              const key = String(point.key || '').toLowerCase();

              if ((key === 'floor' || key === 'våning') && floor === null) {
                const label = point.label ? String(point.label) : '';
                const value = point.value ? String(point.value) : '';
                const displayMarkdown = isRecord(point.displayText)
                  ? String(point.displayText.markdown || '')
                  : '';

                const textToCheck = `${label} ${value} ${displayMarkdown}`;
                const extractedFloor = extractFloorFromText(textToCheck);
                if (extractedFloor !== null) {
                  floor = extractedFloor;
                }
              }

              if (point.value) infoTexts.push(String(point.value));
              if (point.label) infoTexts.push(String(point.label));
              if (isRecord(point.displayText) && point.displayText.markdown) {
                infoTexts.push(String(point.displayText.markdown));
              }
            }
          }
        }
      }
    }
  }

  if (floor === null) {
    const combinedText = `${infoTexts.join(' ')} ${html}`;
    floor = extractFloorFromText(combinedText);
  }

  if (elevator === null) {
    const combinedText = `${infoTexts.join(' ')} ${html}`;
    elevator = extractElevatorFromText(combinedText, amenities);
  }

  if (balcony === null) {
    const combinedText = `${infoTexts.join(' ')} ${html}`;
    balcony = extractBalconyFromText(combinedText, amenities);
  }

  return {
    listing_id: listingId,
    listing_price: listingPrice,
    living_area: livingArea,
    rooms,
    monthly_fee: monthlyFee,
    construction_year: constructionYear,
    days_on_market: finalDaysOnMarket,
    property_type: propertyType,
    municipality,
    area,
    floor,
    elevator,
    balcony,
    source_url: sourceUrl,
  };
}
