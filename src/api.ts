// Client for the local Flatty back-end (backend/). Falls back to demo data when it isn't running,
// so the hosted Figma preview keeps working.

export type ReasonIcon = "check" | "home" | "mail" | "map" | "search" | "shop" | "train" | "work";

export type Reason = { tone: "yes" | "warn"; icon: ReasonIcon; title: string; detail: string; share?: number };
export type ReplyLevel = "likely" | "unlikely";

export type Photo = { thumb: string; full: string };

export type Apartment = {
  id: string;
  source: string;
  sourceName: string;
  url: string;
  kind: string;
  area: string;
  city?: string;
  title: string;
  originalTitle?: string;
  price: number;
  rent: string;
  meta: string;
  rooms?: number | null;
  surface?: number | null;
  rentNet?: number | null;
  rentCharges?: number | null;
  floor?: number | null;
  yearBuilt?: number | null;
  availableText?: string | null;
  published?: string | null;
  isTemporary?: boolean;
  features: string[];
  images: Photo[];
  lat?: number | null;
  lng?: number | null;
  replyLevel: ReplyLevel;
  replyLabel: string;
  replyScore: number;
  risk: number;
  commuteMinutes?: number | null;
  language?: string;
  movingDate?: string | null;
  tags: string[];
  reasons: Reason[];
  notes?: Reason[];
  riskFlags: string[];
  riskPositives?: string[];
  riskText?: number | null;
  riskTextEvidence?: number | null;
};

export type Filters = {
  sources: string[];
  priceMin: number | null;
  priceMax: number | null;
  roomsMin: number | null;
  surfaceMin: number | null;
  types: string[];
  features: string[];
  maxRisk: number | null;
  rental: "any" | "permanent" | "temporary";
  withPhotos: boolean;
  availableBy: string | null;
  areaLat: number | null;
  areaLng: number | null;
  radiusKm: number;
};

export const emptyFilters: Filters = {
  sources: [], priceMin: null, priceMax: null, roomsMin: null, surfaceMin: null, types: [], features: [],
  maxRisk: null, rental: "any", withPhotos: false, availableBy: null, areaLat: null, areaLng: null, radiusKm: 2,
};

export type SortKey = "reply" | "price_asc" | "price_desc" | "newest" | "risk" | "commute" | "size";

export type SourceInfo = { key: string; name: string; scraping_allowed: boolean; decision: string; terms: string; listings: number };

export type Profile = {
  languages: string[];
  budget: number;
  areas: string[];
  destination: string;
  priorities: string[];
  country: string;
  hasGuarantor: string;
  hasViewingPerson: string;
  hasSwissNumber: string;
  hasSwissBank: string;
  hasResidencePermit: string;
  apartmentTypes: string[];
};

export type MatchResult = {
  total: number;
  listings: Apartment[];
  live: boolean;
  updatedAt: string | null;
  refreshing?: boolean;
  nextRefresh?: string | null;
  sourceCounts: Record<string, number>;
};

export type ListingStatus = { available: boolean | null; message?: string; checkedAt?: string; cached?: boolean };

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export class ApiUnavailable extends Error {}

const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

async function post<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiUnavailable("The Flatty back-end is not reachable.");
  }
  if (!response.headers.get("content-type")?.includes("application/json")) {
    throw new ApiUnavailable("The Flatty back-end is not running.");
  }
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === "object" && data.detail ? data.detail : { code: "error", message: String(data.detail ?? "Something went wrong.") };
    throw new ApiError(response.status, detail.code ?? "error", detail.message ?? "Something went wrong.");
  }
  return data as T;
}

export const PAGE_SIZE = 30;

export async function matchListings(profile: Profile, filters: Filters, sort: SortKey, offset = 0): Promise<MatchResult> {
  try {
    const data = await post<Omit<MatchResult, "live">>("/match", { profile, filters, sort, offset, limit: PAGE_SIZE });
    return { ...data, live: true };
  } catch (error) {
    if (error instanceof ApiUnavailable) {
      const listings = offset ? [] : demoApartments;
      return { total: demoApartments.length, listings, live: false, updatedAt: null, sourceCounts: {} };
    }
    throw error;
  }
}

/** Asks the back-end to check (at most once an hour) that the listing is still online at its source. */
export async function checkListingOnline(id: string): Promise<ListingStatus> {
  try {
    const response = await fetch(`${API_BASE}/listings/${encodeURIComponent(id)}/check`);
    if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) {
      return { available: null };
    }
    return (await response.json()) as ListingStatus;
  } catch {
    return { available: null };
  }
}

export async function fetchSources(): Promise<SourceInfo[]> {
  try {
    const response = await fetch(`${API_BASE}/sources`);
    if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) return [];
    return (await response.json()) as SourceInfo[];
  } catch {
    return [];
  }
}

export async function checkLink(profile: Profile, input: { url?: string; text?: string }): Promise<Apartment> {
  const data = await post<{ listing: Apartment }>("/check-link", { profile, ...input });
  return data.listing;
}

export async function generateText(kind: "email" | "summary", listing: Apartment, profile: Profile) {
  return post<{ text: string; engine: string }>("/generate", { kind, listing, profile });
}

export async function translateTitle(title: string): Promise<{ title: string; originalTitle: string; engine: string }> {
  try {
    return await post<{ title: string; originalTitle: string; engine: string }>("/translate-title", { title });
  } catch {
    return { title, originalTitle: title, engine: "template" };
  }
}

export const demoApartments: Apartment[] = [
  {
    id: "demo:1", source: "demo", sourceName: "Demo", kind: "Apartment", features: ["Balcony or garden"], images: [], url: "", area: "Breitenrain", title: "Bright 2.5-room apartment", originalTitle: "Helle 2.5-Zimmer-Wohnung im Breitenrain", price: 1720, rent: "CHF 1,720",
    meta: "58 m² · 2.5 rooms", replyLevel: "likely", replyLabel: "Likely", replyScore: 0.78, risk: 8, tags: ["7 min to uni", "Tram nearby"], riskFlags: [],
    reasons: [
      { tone: "yes", icon: "home", title: "Private landlord", detail: "Private landlords reply to students more often than agencies", share: 46 },
      { tone: "yes", icon: "work", title: "Student-friendly", detail: "The listing mentions students", share: 54 },
    ],
    notes: [
      { tone: "yes", icon: "check", title: "Within your budget", detail: "CHF 80 below your maximum" },
      { tone: "yes", icon: "train", title: "Easy commute", detail: "7 minutes to your university" },
      { tone: "warn", icon: "home", title: "Smaller than average", detail: "6 m² below similar listings" },
    ],
  },
  {
    id: "demo:2", source: "demo", sourceName: "Demo", kind: "Apartment", features: [], images: [], url: "", area: "Länggasse", title: "Quiet apartment near Uni Bern", originalTitle: "Ruhige Wohnung nahe Uni Bern", price: 1890, rent: "CHF 1,890",
    meta: "64 m² · 3 rooms", replyLevel: "likely", replyLabel: "Likely", replyScore: 0.56, risk: 27, tags: ["4 min to uni", "Shops nearby"], riskFlags: ["Pushes contact off the platform (WhatsApp, private e-mail)"],
    reasons: [
      { tone: "yes", icon: "home", title: "Private landlord", detail: "Private landlords reply to students more often than agencies", share: 100 },
    ],
    notes: [
      { tone: "warn", icon: "check", title: "Slightly over budget", detail: "CHF 90 above your maximum" },
      { tone: "yes", icon: "train", title: "Easy commute", detail: "4 minutes to your university" },
    ],
  },
  {
    id: "demo:3", source: "demo", sourceName: "Demo", kind: "Apartment", features: [], images: [], url: "", area: "Mattenhof", title: "Renovated city apartment", originalTitle: "Renovierte Stadtwohnung im Mattenhof", price: 1650, rent: "CHF 1,650",
    meta: "51 m² · 2 rooms", replyLevel: "unlikely", replyLabel: "Unlikely", replyScore: 0.31, risk: 68, tags: ["18 min to uni", "Bus nearby"],
    riskFlags: ["No viewing offered or the owner is abroad", "Asks for a deposit or payment before a viewing"],
    reasons: [
      { tone: "warn", icon: "search", title: "Cheap for the area", detail: "Expect many other applicants", share: 100 },
    ],
    notes: [
      { tone: "yes", icon: "check", title: "Within your budget", detail: "CHF 150 below your maximum" },
      { tone: "warn", icon: "train", title: "Longer commute", detail: "18 minutes to your university" },
    ],
  },
];
