// Maps normalized ASCII keys (lowercase, underscores) to proper Swedish display names.

export const AREA_DISPLAY_NAMES: Record<string, string> = {
  // Areas requiring Swedish character corrections
  sodermalm: "Södermalm",
  ostermalm: "Östermalm",
  gardet: "Gärdet",
  hammarby_sjostad: "Hammarby Sjöstad",
  sodermalm_katarina: "Södermalm Katarina",
  sodermalm_hogalid: "Södermalm Högalid",
  sodermalm_sofia: "Södermalm Sofia",
  arsta: "Årsta",
  grondal: "Gröndal",
  sodermalm_maria: "Södermalm Maria",
  norra_djurgardsstaden: "Norra Djurgårdsstaden",
  fredhall: "Fredhäll",

  // Areas with correct spellings (no special characters needed)
  vasastan: "Vasastan",
  kungsholmen: "Kungsholmen",
  liljeholmen: "Liljeholmen",
  bromma: "Bromma",
  norrmalm: "Norrmalm",
  liljeholmskajen: "Liljeholmskajen",
  nacka: "Nacka",
  birkastan: "Birkastan",
  hornstull: "Hornstull",
  kungsholmen_fridhemsplan: "Kungsholmen Fridhemsplan",
  gamla_stan: "Gamla Stan",
  johanneshov: "Johanneshov",
  hornsbergs_strand: "Hornsbergs Strand",
  vasastan_odenplan: "Vasastan Odenplan",
  ekhagen: "Ekhagen",
  hagastaden: "Hagastaden",
  reimersholme: "Reimersholme",
  solna: "Solna",
  sundbyberg: "Sundbyberg",
  rasunda: "Råsunda",
  enskede_arsta_vantor: "Enskede-Årsta-Vantör",
  // Note: Kristineberg consolidated into Kungsholmen
  // Note: Frösunda consolidated into Solna
};

export function getDisplayName(areaKey: string): string {
  if (!areaKey) {
    return "Unknown";
  }

  if (areaKey in AREA_DISPLAY_NAMES) {
    return AREA_DISPLAY_NAMES[areaKey];
  }

  // Fallback: title-case the underscored key
  return areaKey
    .replace(/_/g, " ")
    .split(" ")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function normalizeAreaKey(areaName: string): string {
  if (!areaName) {
    return "unknown";
  }

  return areaName
    .toLowerCase()
    .replace(/ /g, "_")
    .replace(/-/g, "_")
    .replace(/å/g, "a")
    .replace(/ä/g, "a")
    .replace(/ö/g, "o");
}
