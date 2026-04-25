import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";

import type {
  PublicMetricCount,
  PublicRecentActivityItem,
} from "../api/publicTrafficApi";
import { StatusBadge } from "./SurfacePrimitives";

type SecurityTelemetryGlobeProps = {
  aggregateCounts: ReadonlyArray<PublicMetricCount>;
  currentLocation: string | null;
  recentActivity: ReadonlyArray<PublicRecentActivityItem>;
  viewerTimezone?: string | null;
};

type GlobeMarker = {
  aggregateCount: number;
  currentViewer: boolean;
  label: string;
  latitude: number;
  longitude: number;
  recentHits: number;
};

type ProjectedMarker = GlobeMarker & {
  size: number;
  x: number;
  y: number;
};

const GLOBE_CENTER = 170;
const GLOBE_RADIUS = 122;
const DEFAULT_VIEW_LATITUDE = 18;
const DEFAULT_VIEW_LONGITUDE = -35;

const REGION_COORDINATES: Record<string, { latitude: number; longitude: number }> = {
  "us / alabama": { latitude: 32.3182, longitude: -86.9023 },
  "us / alaska": { latitude: 64.2008, longitude: -149.4937 },
  "us / arizona": { latitude: 34.0489, longitude: -111.0937 },
  "us / arkansas": { latitude: 34.7465, longitude: -92.2896 },
  "us / california": { latitude: 36.7783, longitude: -119.4179 },
  "us / colorado": { latitude: 39.5501, longitude: -105.7821 },
  "us / connecticut": { latitude: 41.6032, longitude: -73.0877 },
  "us / delaware": { latitude: 38.9108, longitude: -75.5277 },
  "us / florida": { latitude: 27.6648, longitude: -81.5158 },
  "us / georgia": { latitude: 32.1656, longitude: -82.9001 },
  "us / hawaii": { latitude: 19.8968, longitude: -155.5828 },
  "us / idaho": { latitude: 44.0682, longitude: -114.742 },
  "us / illinois": { latitude: 40.6331, longitude: -89.3985 },
  "us / indiana": { latitude: 40.2672, longitude: -86.1349 },
  "us / iowa": { latitude: 41.878, longitude: -93.0977 },
  "us / kansas": { latitude: 39.0119, longitude: -98.4842 },
  "us / kentucky": { latitude: 37.8393, longitude: -84.27 },
  "us / louisiana": { latitude: 30.9843, longitude: -91.9623 },
  "us / maine": { latitude: 45.2538, longitude: -69.4455 },
  "us / maryland": { latitude: 39.0458, longitude: -76.6413 },
  "us / massachusetts": { latitude: 42.4072, longitude: -71.3824 },
  "us / michigan": { latitude: 44.3148, longitude: -85.6024 },
  "us / minnesota": { latitude: 46.7296, longitude: -94.6859 },
  "us / mississippi": { latitude: 32.3547, longitude: -89.3985 },
  "us / missouri": { latitude: 37.9643, longitude: -91.8318 },
  "us / montana": { latitude: 46.8797, longitude: -110.3626 },
  "us / nebraska": { latitude: 41.4925, longitude: -99.9018 },
  "us / nevada": { latitude: 38.8026, longitude: -116.4194 },
  "us / new hampshire": { latitude: 43.1939, longitude: -71.5724 },
  "us / new jersey": { latitude: 40.0583, longitude: -74.4057 },
  "us / new mexico": { latitude: 34.5199, longitude: -105.8701 },
  "us / new york": { latitude: 42.1657, longitude: -74.9481 },
  "us / north carolina": { latitude: 35.7596, longitude: -79.0193 },
  "us / north dakota": { latitude: 47.5515, longitude: -101.002 },
  "us / ohio": { latitude: 40.4173, longitude: -82.9071 },
  "us / oklahoma": { latitude: 35.0078, longitude: -97.0929 },
  "us / oregon": { latitude: 43.8041, longitude: -120.5542 },
  "us / pennsylvania": { latitude: 41.2033, longitude: -77.1945 },
  "us / rhode island": { latitude: 41.5801, longitude: -71.4774 },
  "us / south carolina": { latitude: 33.8361, longitude: -81.1637 },
  "us / south dakota": { latitude: 43.9695, longitude: -99.9018 },
  "us / tennessee": { latitude: 35.5175, longitude: -86.5804 },
  "us / texas": { latitude: 31.9686, longitude: -99.9018 },
  "us / utah": { latitude: 39.321, longitude: -111.0937 },
  "us / vermont": { latitude: 44.5588, longitude: -72.5778 },
  "us / virginia": { latitude: 37.4316, longitude: -78.6569 },
  "us / washington": { latitude: 47.7511, longitude: -120.7401 },
  "us / west virginia": { latitude: 38.5976, longitude: -80.4549 },
  "us / wisconsin": { latitude: 43.7844, longitude: -88.7879 },
  "us / wyoming": { latitude: 43.076, longitude: -107.2903 },
  "us / district of columbia": { latitude: 38.9072, longitude: -77.0369 },
  // Azure region shortcuts
  "us / central us": { latitude: 41.25, longitude: -98.0 },
  "us / east us": { latitude: 37.5, longitude: -78.0 },
  "us / eastus": { latitude: 37.5, longitude: -78.0 },
  "us / eastus2": { latitude: 36.8, longitude: -76.1 },
  "us / west us": { latitude: 37.0, longitude: -120.0 },
  "us / westus": { latitude: 37.0, longitude: -120.0 },
  "us / westus2": { latitude: 47.2, longitude: -119.85 },
  "us / westus3": { latitude: 33.45, longitude: -112.07 },
  "us / south central us": { latitude: 31.0, longitude: -98.5 },
  "us / north central us": { latitude: 41.6, longitude: -87.65 },
  // Canada provinces
  "ca / ontario": { latitude: 51.2538, longitude: -85.3232 },
  "ca / quebec": { latitude: 52.9399, longitude: -73.5491 },
  "ca / british columbia": { latitude: 53.7267, longitude: -127.6476 },
  "ca / alberta": { latitude: 53.9333, longitude: -116.5765 },
  // Common metros
  "us / new york city": { latitude: 40.7128, longitude: -74.006 },
  "us / chicago": { latitude: 41.8781, longitude: -87.6298 },
  "us / los angeles": { latitude: 34.0522, longitude: -118.2437 },
  "us / san francisco": { latitude: 37.7749, longitude: -122.4194 },
  "us / seattle": { latitude: 47.6062, longitude: -122.3321 },
  "us / dallas": { latitude: 32.7767, longitude: -96.797 },
  "us / atlanta": { latitude: 33.749, longitude: -84.388 },
  "us / boston": { latitude: 42.3601, longitude: -71.0589 },
  "us / miami": { latitude: 25.7617, longitude: -80.1918 },
  "us / denver": { latitude: 39.7392, longitude: -104.9903 },
  "us / phoenix": { latitude: 33.4484, longitude: -112.074 },
  "us / columbus": { latitude: 39.9612, longitude: -82.9988 },
  "us / cleveland": { latitude: 41.4993, longitude: -81.6944 },
  "us / cincinnati": { latitude: 39.1031, longitude: -84.512 },
  "gb / london": { latitude: 51.5074, longitude: -0.1278 },
  "fr / paris": { latitude: 48.8566, longitude: 2.3522 },
  "de / berlin": { latitude: 52.52, longitude: 13.405 },
  "jp / tokyo": { latitude: 35.6762, longitude: 139.6503 },
};

const COUNTRY_COORDINATES: Record<string, { latitude: number; longitude: number }> = {
  ae: { latitude: 23.4241, longitude: 53.8478 },
  ar: { latitude: -38.4161, longitude: -63.6167 },
  at: { latitude: 47.5162, longitude: 14.5501 },
  au: { latitude: -25.2744, longitude: 133.7751 },
  be: { latitude: 50.5039, longitude: 4.4699 },
  br: { latitude: -14.235, longitude: -51.9253 },
  ca: { latitude: 56.1304, longitude: -106.3468 },
  ch: { latitude: 46.8182, longitude: 8.2275 },
  cl: { latitude: -35.6751, longitude: -71.543 },
  cn: { latitude: 35.8617, longitude: 104.1954 },
  co: { latitude: 4.5709, longitude: -74.2973 },
  cz: { latitude: 49.8175, longitude: 15.473 },
  de: { latitude: 51.1657, longitude: 10.4515 },
  dk: { latitude: 56.2639, longitude: 9.5018 },
  es: { latitude: 40.4637, longitude: -3.7492 },
  fi: { latitude: 61.9241, longitude: 25.7482 },
  fr: { latitude: 46.2276, longitude: 2.2137 },
  gb: { latitude: 55.3781, longitude: -3.436 },
  gr: { latitude: 39.0742, longitude: 21.8243 },
  hk: { latitude: 22.3193, longitude: 114.1694 },
  ie: { latitude: 53.1424, longitude: -7.6921 },
  il: { latitude: 31.0461, longitude: 34.8516 },
  in: { latitude: 20.5937, longitude: 78.9629 },
  it: { latitude: 41.8719, longitude: 12.5674 },
  jp: { latitude: 36.2048, longitude: 138.2529 },
  kr: { latitude: 35.9078, longitude: 127.7669 },
  mx: { latitude: 23.6345, longitude: -102.5528 },
  my: { latitude: 4.2105, longitude: 101.9758 },
  nl: { latitude: 52.1326, longitude: 5.2913 },
  no: { latitude: 60.472, longitude: 8.4689 },
  nz: { latitude: -40.9006, longitude: 174.886 },
  pe: { latitude: -9.19, longitude: -75.0152 },
  ph: { latitude: 12.8797, longitude: 121.774 },
  pl: { latitude: 51.9194, longitude: 19.1451 },
  pt: { latitude: 39.3999, longitude: -8.2245 },
  ro: { latitude: 45.9432, longitude: 24.9668 },
  ru: { latitude: 61.524, longitude: 105.3188 },
  sa: { latitude: 23.8859, longitude: 45.0792 },
  se: { latitude: 60.1282, longitude: 18.6435 },
  sg: { latitude: 1.3521, longitude: 103.8198 },
  th: { latitude: 15.87, longitude: 100.9925 },
  tr: { latitude: 38.9637, longitude: 35.2433 },
  tw: { latitude: 23.6978, longitude: 120.9605 },
  ua: { latitude: 48.3794, longitude: 31.1656 },
  us: { latitude: 39.8283, longitude: -98.5795 },
  vn: { latitude: 14.0583, longitude: 108.2772 },
  za: { latitude: -30.5595, longitude: 22.9375 },
};

const COUNTRY_ALIASES: Record<string, string> = {
  argentina: "ar",
  australia: "au",
  austria: "at",
  belgium: "be",
  brazil: "br",
  canada: "ca",
  chile: "cl",
  china: "cn",
  colombia: "co",
  "czech republic": "cz",
  czechia: "cz",
  denmark: "dk",
  finland: "fi",
  france: "fr",
  germany: "de",
  greece: "gr",
  "hong kong": "hk",
  india: "in",
  ireland: "ie",
  israel: "il",
  italy: "it",
  japan: "jp",
  malaysia: "my",
  mexico: "mx",
  netherlands: "nl",
  "new zealand": "nz",
  norway: "no",
  peru: "pe",
  philippines: "ph",
  poland: "pl",
  portugal: "pt",
  romania: "ro",
  russia: "ru",
  "saudi arabia": "sa",
  singapore: "sg",
  "south africa": "za",
  "south korea": "kr",
  korea: "kr",
  spain: "es",
  sweden: "se",
  switzerland: "ch",
  taiwan: "tw",
  thailand: "th",
  turkey: "tr",
  ukraine: "ua",
  "united arab emirates": "ae",
  uae: "ae",
  "united kingdom": "gb",
  uk: "gb",
  "united states": "us",
  usa: "us",
  vietnam: "vn",
};

// Coarse IANA timezone -> country code mapping used as a public-safe fallback
// when the server-side enrichment headers have not populated approximate_location.
const TIMEZONE_COUNTRY_FALLBACK: Record<string, string> = {
  "africa/cairo": "eg",
  "africa/johannesburg": "za",
  "africa/lagos": "ng",
  "africa/nairobi": "ke",
  "america/anchorage": "us",
  "america/argentina/buenos_aires": "ar",
  "america/bogota": "co",
  "america/chicago": "us",
  "america/denver": "us",
  "america/detroit": "us",
  "america/edmonton": "ca",
  "america/halifax": "ca",
  "america/indiana/indianapolis": "us",
  "america/lima": "pe",
  "america/los_angeles": "us",
  "america/mexico_city": "mx",
  "america/montreal": "ca",
  "america/new_york": "us",
  "america/phoenix": "us",
  "america/santiago": "cl",
  "america/sao_paulo": "br",
  "america/toronto": "ca",
  "america/vancouver": "ca",
  "asia/bangkok": "th",
  "asia/dubai": "ae",
  "asia/hong_kong": "hk",
  "asia/jakarta": "id",
  "asia/jerusalem": "il",
  "asia/karachi": "pk",
  "asia/kolkata": "in",
  "asia/kuala_lumpur": "my",
  "asia/manila": "ph",
  "asia/riyadh": "sa",
  "asia/seoul": "kr",
  "asia/shanghai": "cn",
  "asia/singapore": "sg",
  "asia/taipei": "tw",
  "asia/tokyo": "jp",
  "australia/brisbane": "au",
  "australia/melbourne": "au",
  "australia/perth": "au",
  "australia/sydney": "au",
  "europe/amsterdam": "nl",
  "europe/athens": "gr",
  "europe/berlin": "de",
  "europe/brussels": "be",
  "europe/copenhagen": "dk",
  "europe/dublin": "ie",
  "europe/helsinki": "fi",
  "europe/istanbul": "tr",
  "europe/kiev": "ua",
  "europe/kyiv": "ua",
  "europe/lisbon": "pt",
  "europe/london": "gb",
  "europe/madrid": "es",
  "europe/moscow": "ru",
  "europe/oslo": "no",
  "europe/paris": "fr",
  "europe/prague": "cz",
  "europe/rome": "it",
  "europe/stockholm": "se",
  "europe/vienna": "at",
  "europe/warsaw": "pl",
  "europe/zurich": "ch",
  "pacific/auckland": "nz",
};

const TIMEZONE_COUNTRY_LABEL: Record<string, string> = {
  ae: "United Arab Emirates",
  ar: "Argentina",
  at: "Austria",
  au: "Australia",
  be: "Belgium",
  br: "Brazil",
  ca: "Canada",
  ch: "Switzerland",
  cl: "Chile",
  cn: "China",
  co: "Colombia",
  cz: "Czechia",
  de: "Germany",
  dk: "Denmark",
  eg: "Egypt",
  es: "Spain",
  fi: "Finland",
  fr: "France",
  gb: "United Kingdom",
  gr: "Greece",
  hk: "Hong Kong",
  id: "Indonesia",
  ie: "Ireland",
  il: "Israel",
  in: "India",
  it: "Italy",
  jp: "Japan",
  ke: "Kenya",
  kr: "South Korea",
  mx: "Mexico",
  my: "Malaysia",
  ng: "Nigeria",
  nl: "Netherlands",
  no: "Norway",
  nz: "New Zealand",
  pe: "Peru",
  ph: "Philippines",
  pk: "Pakistan",
  pl: "Poland",
  pt: "Portugal",
  ro: "Romania",
  ru: "Russia",
  sa: "Saudi Arabia",
  se: "Sweden",
  sg: "Singapore",
  th: "Thailand",
  tr: "Turkey",
  tw: "Taiwan",
  ua: "Ukraine",
  us: "United States",
  vn: "Vietnam",
  za: "South Africa",
};

function resolveViewerLocationFromTimezone(timezone: string | null | undefined): string | null {
  if (!timezone) {
    return null;
  }
  const countryCode = TIMEZONE_COUNTRY_FALLBACK[timezone.trim().toLowerCase()];
  if (!countryCode) {
    return null;
  }
  const label = TIMEZONE_COUNTRY_LABEL[countryCode] || countryCode.toUpperCase();
  return `${label} (browser timezone)`;
}

function normalizeGeographyLabel(label: string): string {
  // Strip a trailing parenthesized qualifier (e.g. "United States (browser timezone)")
  // so timezone-derived fallback labels still resolve through the country alias map.
  return label.replace(/\s*\([^)]*\)\s*$/, "").trim().toLowerCase();
}

function resolveCountryCoordinate(label: string) {
  const normalizedLabel = normalizeGeographyLabel(label);
  const countryCode = COUNTRY_ALIASES[normalizedLabel] || normalizedLabel;

  return COUNTRY_COORDINATES[countryCode] || null;
}

function resolveTelemetryCoordinate(label: string) {
  const normalizedLabel = normalizeGeographyLabel(label);
  if (
    !normalizedLabel ||
    normalizedLabel.startsWith("unavailable") ||
    normalizedLabel.startsWith("no ")
  ) {
    return null;
  }

  const regionCoordinate = REGION_COORDINATES[normalizedLabel];
  if (regionCoordinate) {
    return regionCoordinate;
  }

  const locationParts = normalizedLabel.split("/").map((part) => part.trim());
  if (locationParts.length > 0) {
    return resolveCountryCoordinate(locationParts[0]);
  }

  return resolveCountryCoordinate(normalizedLabel);
}

function upsertMarker(
  markerMap: Map<string, GlobeMarker>,
  label: string,
  updateMarker: (marker: GlobeMarker) => GlobeMarker,
) {
  const coordinate = resolveTelemetryCoordinate(label);
  if (!coordinate) {
    return;
  }

  const existingMarker = markerMap.get(label) || {
    aggregateCount: 0,
    currentViewer: false,
    label,
    latitude: coordinate.latitude,
    longitude: coordinate.longitude,
    recentHits: 0,
  };
  markerMap.set(label, updateMarker(existingMarker));
}

function buildGlobeMarkers(
  aggregateCounts: ReadonlyArray<PublicMetricCount>,
  recentActivity: ReadonlyArray<PublicRecentActivityItem>,
  currentLocation: string | null,
) {
  const markerMap = new Map<string, GlobeMarker>();

  for (const item of aggregateCounts) {
    upsertMarker(markerMap, item.label, (marker) => ({
      ...marker,
      aggregateCount: marker.aggregateCount + item.count,
    }));
  }

  for (const item of recentActivity) {
    upsertMarker(markerMap, item.geography_bucket, (marker) => ({
      ...marker,
      recentHits: marker.recentHits + 1,
    }));
  }

  if (currentLocation) {
    upsertMarker(markerMap, currentLocation, (marker) => ({
      ...marker,
      currentViewer: true,
    }));
  }

  return Array.from(markerMap.values()).sort((leftMarker, rightMarker) => {
    const rightWeight =
      rightMarker.aggregateCount + rightMarker.recentHits * 2 + (rightMarker.currentViewer ? 3 : 0);
    const leftWeight =
      leftMarker.aggregateCount + leftMarker.recentHits * 2 + (leftMarker.currentViewer ? 3 : 0);

    return rightWeight - leftWeight;
  });
}

function clamp(value: number, minimumValue: number, maximumValue: number) {
  return Math.min(maximumValue, Math.max(minimumValue, value));
}

function degreesToRadians(value: number) {
  return (value * Math.PI) / 180;
}

function radiansToDegrees(value: number) {
  return (value * 180) / Math.PI;
}

function buildViewRotation(markers: ReadonlyArray<GlobeMarker>) {
  if (markers.length === 0) {
    return {
      latitude: DEFAULT_VIEW_LATITUDE,
      longitude: DEFAULT_VIEW_LONGITUDE,
    };
  }

  let latitudeTotal = 0;
  let longitudeX = 0;
  let longitudeY = 0;
  let weightTotal = 0;

  for (const marker of markers) {
    const weight = marker.aggregateCount + marker.recentHits * 2 + (marker.currentViewer ? 3 : 1);
    const longitudeRadians = degreesToRadians(marker.longitude);
    latitudeTotal += marker.latitude * weight;
    longitudeX += Math.cos(longitudeRadians) * weight;
    longitudeY += Math.sin(longitudeRadians) * weight;
    weightTotal += weight;
  }

  return {
    latitude: clamp((latitudeTotal / weightTotal) * 0.55, -30, 40),
    longitude: radiansToDegrees(Math.atan2(longitudeY, longitudeX)),
  };
}

function projectMarker(
  marker: GlobeMarker,
  centerLatitude: number,
  centerLongitude: number,
): ProjectedMarker | null {
  const latitudeRadians = degreesToRadians(marker.latitude);
  const longitudeRadians = degreesToRadians(marker.longitude);
  const centerLatitudeRadians = degreesToRadians(centerLatitude);
  const centerLongitudeRadians = degreesToRadians(centerLongitude);
  const visibility =
    Math.sin(centerLatitudeRadians) * Math.sin(latitudeRadians) +
    Math.cos(centerLatitudeRadians) *
      Math.cos(latitudeRadians) *
      Math.cos(longitudeRadians - centerLongitudeRadians);
  if (visibility <= 0) {
    return null;
  }

  const x =
    GLOBE_CENTER +
    GLOBE_RADIUS * Math.cos(latitudeRadians) * Math.sin(longitudeRadians - centerLongitudeRadians);
  const y =
    GLOBE_CENTER +
    GLOBE_RADIUS *
      (Math.cos(centerLatitudeRadians) * Math.sin(latitudeRadians) -
        Math.sin(centerLatitudeRadians) *
          Math.cos(latitudeRadians) *
          Math.cos(longitudeRadians - centerLongitudeRadians));
  const size = clamp(
    5 + marker.aggregateCount * 0.55 + marker.recentHits * 1.25 + (marker.currentViewer ? 2.5 : 0),
    5,
    18,
  );

  return {
    ...marker,
    size,
    x,
    y,
  };
}

function formatMarkerSummary(marker: GlobeMarker) {
  const summaryParts = [];
  if (marker.aggregateCount > 0) {
    summaryParts.push(`${marker.aggregateCount} retained`);
  }
  if (marker.recentHits > 0) {
    summaryParts.push(`${marker.recentHits} recent`);
  }
  if (marker.currentViewer) {
    summaryParts.push("current viewer");
  }

  return summaryParts.join(" · ") || "No visible signals";
}

// Approximate continent outlines as [latitude, longitude] vertex rings.
// Intentionally low-fidelity: enough to read as Earth, not a survey-grade map.
const CONTINENT_POLYGONS: ReadonlyArray<ReadonlyArray<readonly [number, number]>> = [
  // North America
  [
    [72, -156], [70, -140], [68, -110], [70, -85], [60, -64], [48, -52],
    [40, -70], [25, -80], [18, -92], [15, -100], [22, -107], [32, -117],
    [48, -125], [60, -140], [72, -156],
  ],
  // Greenland
  [
    [83, -32], [80, -18], [72, -22], [66, -36], [70, -52], [78, -55],
    [82, -42], [83, -32],
  ],
  // South America
  [
    [12, -72], [10, -60], [5, -50], [-5, -35], [-22, -40], [-35, -55],
    [-55, -68], [-40, -73], [-20, -70], [-5, -78], [5, -78], [12, -72],
  ],
  // Europe (with British Isles approximated as part of the outline)
  [
    [70, -8], [70, 30], [60, 42], [45, 40], [38, 28], [36, 14], [40, -2],
    [50, -10], [58, -8], [70, -8],
  ],
  // Africa
  [
    [35, -10], [33, 12], [32, 32], [12, 43], [-2, 42], [-15, 40], [-30, 32],
    [-35, 20], [-30, 16], [-20, 12], [-5, 8], [5, -2], [12, -16], [22, -17],
    [30, -10], [35, -10],
  ],
  // Asia (broad)
  [
    [72, 35], [75, 70], [73, 110], [70, 140], [60, 160], [50, 158],
    [38, 140], [22, 120], [10, 105], [8, 92], [22, 72], [25, 60],
    [38, 48], [50, 42], [62, 38], [72, 35],
  ],
  // South-East Asia / Indonesia stripe (very rough)
  [
    [5, 95], [2, 105], [-5, 115], [-9, 125], [-8, 135], [0, 132],
    [4, 120], [6, 105], [5, 95],
  ],
  // Australia
  [
    [-12, 130], [-12, 142], [-22, 152], [-35, 150], [-38, 142], [-35, 122],
    [-22, 114], [-15, 122], [-12, 130],
  ],
  // Antarctica strip
  [
    [-65, -180], [-70, -120], [-72, -60], [-75, 0], [-72, 60], [-70, 120],
    [-65, 180], [-65, -180],
  ],
];

function projectLatLon(
  latitude: number,
  longitude: number,
  centerLatitude: number,
  centerLongitude: number,
) {
  const latitudeRadians = degreesToRadians(latitude);
  const longitudeRadians = degreesToRadians(longitude);
  const centerLatitudeRadians = degreesToRadians(centerLatitude);
  const centerLongitudeRadians = degreesToRadians(centerLongitude);
  const visibility =
    Math.sin(centerLatitudeRadians) * Math.sin(latitudeRadians) +
    Math.cos(centerLatitudeRadians) *
      Math.cos(latitudeRadians) *
      Math.cos(longitudeRadians - centerLongitudeRadians);
  if (visibility <= 0) {
    return null;
  }
  const x =
    GLOBE_CENTER +
    GLOBE_RADIUS * Math.cos(latitudeRadians) * Math.sin(longitudeRadians - centerLongitudeRadians);
  const y =
    GLOBE_CENTER +
    GLOBE_RADIUS *
      (Math.cos(centerLatitudeRadians) * Math.sin(latitudeRadians) -
        Math.sin(centerLatitudeRadians) *
          Math.cos(latitudeRadians) *
          Math.cos(longitudeRadians - centerLongitudeRadians));
  return { x, y };
}

function buildContinentPaths(centerLatitude: number, centerLongitude: number): string {
  const subdivisions = 10;
  const segments: string[] = [];
  for (const polygon of CONTINENT_POLYGONS) {
    let currentRun = "";
    let runIsOpen = false;
    for (let vertexIndex = 0; vertexIndex < polygon.length - 1; vertexIndex++) {
      const [latitudeStart, longitudeStart] = polygon[vertexIndex];
      const [latitudeEnd, longitudeEnd] = polygon[vertexIndex + 1];
      for (let step = 0; step <= subdivisions; step++) {
        const interpolation = step / subdivisions;
        const latitude = latitudeStart + (latitudeEnd - latitudeStart) * interpolation;
        const longitude = longitudeStart + (longitudeEnd - longitudeStart) * interpolation;
        const projected = projectLatLon(latitude, longitude, centerLatitude, centerLongitude);
        if (projected === null) {
          if (runIsOpen) {
            segments.push(currentRun);
            currentRun = "";
            runIsOpen = false;
          }
          continue;
        }
        if (!runIsOpen) {
          currentRun = `M ${projected.x.toFixed(1)} ${projected.y.toFixed(1)}`;
          runIsOpen = true;
        } else {
          currentRun += ` L ${projected.x.toFixed(1)} ${projected.y.toFixed(1)}`;
        }
      }
    }
    if (runIsOpen) {
      segments.push(currentRun);
    }
  }
  return segments.join(" ");
}

export function SecurityTelemetryGlobe({
  aggregateCounts,
  currentLocation,
  recentActivity,
  viewerTimezone,
}: SecurityTelemetryGlobeProps) {
  const resolvedCurrentLocation = useMemo(() => {
    if (currentLocation && resolveTelemetryCoordinate(currentLocation)) {
      return currentLocation;
    }
    return resolveViewerLocationFromTimezone(viewerTimezone) || currentLocation;
  }, [currentLocation, viewerTimezone]);

  const markers = useMemo(
    () => buildGlobeMarkers(aggregateCounts, recentActivity, resolvedCurrentLocation),
    [aggregateCounts, recentActivity, resolvedCurrentLocation],
  );
  const rotation = useMemo(() => buildViewRotation(markers), [markers]);
  const [dragOffset, setDragOffset] = useState<{ dLat: number; dLon: number }>({
    dLat: 0,
    dLon: 0,
  });
  const [isDragging, setIsDragging] = useState(false);
  const [hasUserInteracted, setHasUserInteracted] = useState(false);
  const [autoSpinDeg, setAutoSpinDeg] = useState(0);
  const prefersReducedMotion = useMemo(() => {
    if (typeof window === "undefined" || !window.matchMedia) {
      return false;
    }
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }, []);
  const lastFrameRef = useRef<number | null>(null);

  useEffect(() => {
    if (isDragging || hasUserInteracted || prefersReducedMotion) {
      lastFrameRef.current = null;
      return;
    }

    let frameId = 0;
    const tick = (timestamp: number) => {
      const previous = lastFrameRef.current ?? timestamp;
      const elapsedMs = timestamp - previous;
      lastFrameRef.current = timestamp;
      // ~6 degrees per second so a full rotation takes ~60s.
      setAutoSpinDeg((value) => (value + (elapsedMs / 1000) * 6) % 360);
      frameId = window.requestAnimationFrame(tick);
    };
    frameId = window.requestAnimationFrame(tick);
    return () => {
      window.cancelAnimationFrame(frameId);
      lastFrameRef.current = null;
    };
  }, [isDragging, hasUserInteracted, prefersReducedMotion]);

  const viewLatitude = Math.max(
    -85,
    Math.min(85, rotation.latitude + dragOffset.dLat),
  );
  const viewLongitude =
    rotation.longitude + dragOffset.dLon + (hasUserInteracted ? 0 : autoSpinDeg);

  const continentPath = useMemo(
    () => buildContinentPaths(viewLatitude, viewLongitude),
    [viewLatitude, viewLongitude],
  );
  const projectedMarkers = useMemo(
    () =>
      markers
        .map((marker) => projectMarker(marker, viewLatitude, viewLongitude))
        .filter((marker): marker is ProjectedMarker => marker !== null),
    [markers, viewLatitude, viewLongitude],
  );

  const handlePointerDown = useCallback(
    (event: ReactPointerEvent<SVGSVGElement>) => {
      const startX = event.clientX;
      const startY = event.clientY;
      const startOffset = dragOffset;
      const sensitivity = 0.45;
      setIsDragging(true);
      setHasUserInteracted(true);

      const handleMove = (moveEvent: PointerEvent) => {
        setDragOffset({
          dLat: startOffset.dLat - (moveEvent.clientY - startY) * sensitivity,
          dLon: startOffset.dLon + (moveEvent.clientX - startX) * sensitivity,
        });
      };
      const handleUp = () => {
        setIsDragging(false);
        document.removeEventListener("pointermove", handleMove);
        document.removeEventListener("pointerup", handleUp);
        document.removeEventListener("pointercancel", handleUp);
      };

      document.addEventListener("pointermove", handleMove);
      document.addEventListener("pointerup", handleUp);
      document.addEventListener("pointercancel", handleUp);
    },
    [dragOffset],
  );

  return (
    <div className="security-globe-shell">
      <div className="security-globe-stage">
        <svg
          aria-label="Coarse geography globe (drag to rotate)"
          className={
            isDragging
              ? "security-globe-svg security-globe-svg-grabbing"
              : "security-globe-svg"
          }
          onPointerDown={handlePointerDown}
          role="img"
          viewBox="0 0 340 340"
        >
          <defs>
            <radialGradient id="security-globe-ocean" cx="38%" cy="30%" r="78%">
              <stop offset="0%" stopColor="#1e6fb8" />
              <stop offset="45%" stopColor="#0e3d72" />
              <stop offset="85%" stopColor="#061d3a" />
              <stop offset="100%" stopColor="#020a1a" />
            </radialGradient>
            <radialGradient id="security-globe-land" cx="40%" cy="32%" r="80%">
              <stop offset="0%" stopColor="#5fa86b" />
              <stop offset="60%" stopColor="#2f7a48" />
              <stop offset="100%" stopColor="#1b4a30" />
            </radialGradient>
            <radialGradient id="security-globe-terminator" cx="78%" cy="60%" r="82%">
              <stop offset="0%" stopColor="rgba(2, 6, 18, 0)" />
              <stop offset="55%" stopColor="rgba(2, 6, 18, 0.18)" />
              <stop offset="85%" stopColor="rgba(2, 6, 18, 0.62)" />
              <stop offset="100%" stopColor="rgba(2, 6, 18, 0.88)" />
            </radialGradient>
            <radialGradient id="security-globe-specular" cx="32%" cy="24%" r="32%">
              <stop offset="0%" stopColor="rgba(186, 230, 253, 0.55)" />
              <stop offset="60%" stopColor="rgba(186, 230, 253, 0.08)" />
              <stop offset="100%" stopColor="rgba(186, 230, 253, 0)" />
            </radialGradient>
            <radialGradient id="security-globe-atmosphere" cx="50%" cy="50%" r="50%">
              <stop offset="78%" stopColor="rgba(56, 189, 248, 0)" />
              <stop offset="92%" stopColor="rgba(56, 189, 248, 0.28)" />
              <stop offset="100%" stopColor="rgba(56, 189, 248, 0)" />
            </radialGradient>
            <clipPath id="security-globe-clip">
              <circle cx={GLOBE_CENTER} cy={GLOBE_CENTER} r={GLOBE_RADIUS} />
            </clipPath>
          </defs>

          <circle
            className="security-globe-shadow"
            cx={GLOBE_CENTER}
            cy={GLOBE_CENTER + 14}
            r={GLOBE_RADIUS}
          />
          <circle
            className="security-globe-atmosphere"
            cx={GLOBE_CENTER}
            cy={GLOBE_CENTER}
            r={GLOBE_RADIUS + 18}
          />
          <circle
            className="security-globe-sphere"
            cx={GLOBE_CENTER}
            cy={GLOBE_CENTER}
            r={GLOBE_RADIUS}
          />

          <g className="security-globe-grid-lines" clipPath="url(#security-globe-clip)">
            <ellipse cx={GLOBE_CENTER} cy={GLOBE_CENTER} rx={GLOBE_RADIUS} ry={34} />
            <ellipse cx={GLOBE_CENTER} cy={GLOBE_CENTER} rx={GLOBE_RADIUS} ry={66} />
            <ellipse cx={GLOBE_CENTER} cy={GLOBE_CENTER} rx={GLOBE_RADIUS} ry={94} />
            <ellipse cx={GLOBE_CENTER} cy={GLOBE_CENTER} rx={44} ry={GLOBE_RADIUS} />
            <ellipse cx={GLOBE_CENTER} cy={GLOBE_CENTER} rx={74} ry={GLOBE_RADIUS} />
            <ellipse cx={GLOBE_CENTER} cy={GLOBE_CENTER} rx={102} ry={GLOBE_RADIUS} />
          </g>

          <g className="security-globe-continents" clipPath="url(#security-globe-clip)">
            <path d={continentPath} />
          </g>

          <circle
            className="security-globe-terminator"
            clipPath="url(#security-globe-clip)"
            cx={GLOBE_CENTER}
            cy={GLOBE_CENTER}
            r={GLOBE_RADIUS}
          />
          <circle
            className="security-globe-specular"
            clipPath="url(#security-globe-clip)"
            cx={GLOBE_CENTER}
            cy={GLOBE_CENTER}
            r={GLOBE_RADIUS}
          />

          <g clipPath="url(#security-globe-clip)">
            {projectedMarkers.map((marker) => (
              <g key={marker.label}>
                <title>{`${marker.label} — ${formatMarkerSummary(marker)}`}</title>
                <circle
                  className={marker.recentHits > 0 || marker.currentViewer ? "security-globe-marker-halo security-globe-marker-halo-live" : "security-globe-marker-halo"}
                  cx={marker.x}
                  cy={marker.y}
                  r={marker.size + 5}
                />
                <circle
                  className={marker.currentViewer ? "security-globe-marker security-globe-marker-current" : marker.recentHits > 0 ? "security-globe-marker security-globe-marker-live" : "security-globe-marker"}
                  cx={marker.x}
                  cy={marker.y}
                  r={marker.size}
                />
              </g>
            ))}
          </g>
        </svg>
      </div>

      <div className="security-globe-meta">
        <p className="workspace-copy security-globe-copy">
          This layer plots only country or region centers from the public-safe labels already shown elsewhere on the page. It is a geography cue, not raw location tracking.
        </p>
        {markers.length > 0 ? (
          <ul className="security-globe-point-list">
            {markers.map((marker) => (
              <li className="security-globe-point-row" key={marker.label}>
                <div>
                  <strong>{marker.label}</strong>
                  <p>{formatMarkerSummary(marker)}</p>
                </div>
                <div className="security-globe-badges">
                  {marker.currentViewer ? (
                    <StatusBadge tone="accent">Current viewer</StatusBadge>
                  ) : null}
                  {marker.recentHits > 0 ? (
                    <StatusBadge tone="warning">{marker.recentHits} recent</StatusBadge>
                  ) : null}
                  {marker.aggregateCount > 0 ? (
                    <StatusBadge tone="neutral">{marker.aggregateCount} retained</StatusBadge>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="workspace-copy">
            No coarse geography buckets can be projected yet.
          </p>
        )}
      </div>
    </div>
  );
}