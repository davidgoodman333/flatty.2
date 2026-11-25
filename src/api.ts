// Client for the local Flatty back-end (backend/). Falls back to demo data when it isn't running,
// so the hosted Figma preview keeps working.

export type ReasonIcon = "check" | "home" | "mail" | "map" | "search" | "shop" | "train" | "work";

export type Reason = { tone: "yes" | "warn"; icon: ReasonIcon; title: string; detail: string; share?: number };
export type ReplyLevel = "likely" | "unlikely";
// Who the landlord is looking for, read from the listing by the local LLM. fit: does the student
// meet it (yes / no), or isn't it in the profile (unknown, so not part of the reply chance)?
export type Wish = { topic: string; title: string; quote: string; strength: "required" | "preferred"; fit: "yes" | "no" | "unknown" };

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
  wishes?: Wish[] | null; // null: not read yet
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
  /** The student needs the home from this date (YYYY-MM-DD)… */
  availableBy: string | null;
  /** …until this date. Empty means an open-ended stay. */
  neededUntil: string | null;
  areaLat: number | null;
  areaLng: number | null;
  radiusKm: number;
};

export const emptyFilters: Filters = {
  sources: [], priceMin: null, priceMax: null, roomsMin: null, surfaceMin: null, types: [], features: [],
  maxRisk: null, rental: "any", withPhotos: false, availableBy: null, neededUntil: null, areaLat: null, areaLng: null, radiusKm: 2,
};

export type SortKey = "reply" | "price_asc" | "price_desc" | "newest" | "risk" | "commute" | "size";

export type SourceInfo = { key: string; name: string; scraping_allowed: boolean; decision: string; terms: string; listings: number };

export type Profile = {
  /** Only used to sign application e-mails. */
  name: string;
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

async function request<T>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      credentials: "same-origin", // sends the session cookie
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiUnavailable("The Flatty back-end is not reachable.");
  }
  if (!response.headers.get("content-type")?.includes("application/json")) {
    throw new ApiUnavailable("The Flatty back-end is not running.");
  }
  const data = await response.json();
  // Not past the developer password yet (app/site_gate.py): go to its password page, then back.
  if (response.status === 401 && data?.detail?.code === "site_locked") {
    window.location.assign(`/__gate?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
  }
  if (!response.ok) {
    const detail = typeof data.detail === "object" && data.detail ? data.detail : { code: "error", message: String(data.detail ?? "Something went wrong.") };
    throw new ApiError(response.status, detail.code ?? "error", detail.message ?? "Something went wrong.");
  }
  return data as T;
}

const post = <T,>(path: string, body: unknown) => request<T>("POST", path, body);

// Accounts -----------------------------------------------------------------------------

export type Account = { email: string; profile: Profile | null; filters: Filters | null; sort: SortKey | null };
/** `private`: a private test, where everything needs a log-in. `siteGate`: the site is behind the developer
 * password. `available`: the back-end is running. */
export type Session = { user: Account | null; private: boolean; inviteRequired: boolean; siteGate?: boolean; available: boolean };
export type SavedItem = { listing: Apartment; savedAt: string; available: boolean | null };

type SessionResponse = Omit<Session, "available">;

/** Who is logged in (from the session cookie). Without the back-end nobody is: demo mode. */
export async function fetchSession(): Promise<Session> {
  try {
    return { ...(await request<SessionResponse>("GET", "/auth/me")), available: true };
  } catch {
    return { user: null, private: false, inviteRequired: false, available: false };
  }
}

export async function logIn(email: string, password: string): Promise<Account> {
  return (await post<SessionResponse>("/auth/login", { email, password })).user as Account;
}

export async function register(email: string, password: string, inviteCode: string): Promise<Account> {
  return (await post<SessionResponse>("/auth/register", { email, password, inviteCode })).user as Account;
}

export async function logOut(): Promise<void> {
  await post("/auth/logout", {});
}

export async function deleteAccount(): Promise<void> {
  await post("/auth/delete-account", {});
}

export async function savePreferences(profile: Profile, filters: Filters, sort: SortKey): Promise<void> {
  await request("PUT", "/account/preferences", { profile, filters, sort });
}

export async function fetchSaved(): Promise<SavedItem[]> {
  return (await request<{ items: SavedItem[] }>("GET", "/saved")).items;
}

export async function saveListing(listing: Apartment): Promise<void> {
  await post("/saved", { listing });
}

export async function unsaveListing(id: string): Promise<void> {
  await request("DELETE", `/saved?id=${encodeURIComponent(id)}`);
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
    const response = await fetch(`${API_BASE}/listings/${encodeURIComponent(id)}/check`, { credentials: "same-origin" });
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
    const response = await fetch(`${API_BASE}/sources`, { credentials: "same-origin" });
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

export type EmailLanguage = "English" | "German";

/** `language` only matters for e-mails; without it the back-end picks the listing's language. */
export async function generateText(kind: "email" | "summary", listing: Apartment, profile: Profile, language?: EmailLanguage) {
  return post<{ text: string; engine: string }>("/generate", { kind, listing, profile, language });
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
