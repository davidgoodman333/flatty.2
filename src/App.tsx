import { useEffect, useRef, useState } from "react";
import {
  ApiError, ApiUnavailable, checkLink, checkListingOnline, deleteAccount, demoApartments, emptyFilters, fetchSaved, fetchSession,
  fetchSources, generateText, logOut, matchListings, PAGE_SIZE, saveListing, savePreferences, unsaveListing,
  type Account, type Apartment, type EmailLanguage, type Filters, type ListingStatus, type Profile, type Reason, type SavedItem,
  type Session, type SortKey, type SourceInfo,
} from "./api";
import AuthBox, { type AuthMode } from "./AuthBox";
import HowItWorks from "./HowItWorks";
import Icon from "./Icon";
import { APARTMENT_TYPES, AREAS, BUDGET_MAX, BUDGET_MIN, CAMPUSES, CAMPUS_GROUPS, COUNTRIES, DEFAULT_CAMPUS, findCampus, MAIN_LANGUAGES, OTHER_LANGUAGES, PRIORITIES } from "./options";
import MapRadius from "./MapRadius";
import PreferencesDrawer from "./PreferencesDrawer";

const SORT_OPTIONS: [SortKey, string][] = [
  ["reply", "Best reply chance"], ["price_asc", "Price: low to high"], ["price_desc", "Price: high to low"],
  ["newest", "Newest first"], ["risk", "Lowest risk"], ["commute", "Shortest commute"], ["size", "Largest first"],
];
const TYPE_FILTERS: [string, string, string][] = [
  ["Shared apartment", "Room", "In a shared flat or residence, shared kitchen"],
  ["Studio", "Studio", "1–1.5 rooms, own kitchen and bathroom, up to 50 m²"],
  ["Proper flat", "Apartment or house", "2+ rooms, or a 1.5-room flat over 50 m²"],
];
const KIND_DESCRIPTIONS: Record<string, string> = {
  Room: "Room (shared kitchen or flat)",
  Studio: "Studio (own kitchen and bathroom)",
  Apartment: "Apartment",
  House: "House",
};
const FEATURE_FILTERS = ["Furnished", "Balcony or garden", "Pets allowed", "Dishwasher", "Washing machine", "Lift", "Parking", "Wheelchair accessible"];
const PRICE_GAP = 100; // smallest distance between the two price handles
const pricePercent = (value: number) => ((value - BUDGET_MIN) / (BUDGET_MAX - BUDGET_MIN)) * 100;
// Quick type chips → the five home types used in the preferences.
const APARTMENT_KINDS = ["Proper flat", "2-person flat", "3-person flat"];
const ROOM_OPTIONS = [1, 1.5, 2, 2.5, 3, 3.5, 4, 5];

const formatChf = (value: number) => `CHF ${Math.round(value).toLocaleString("de-CH")}`;
const timeAgo = (value: string) => {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 60) return minutes <= 1 ? "just now" : `${minutes} minutes ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  return `${Math.round(hours / 24)} days ago`;
};
const formatDate = (value: string) => new Date(value).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
// Filters inside the "More filters" panel (the second step of the filter box).
const countActiveFilters = (filters: Filters) =>
  [filters.roomsMin, filters.surfaceMin, filters.maxRisk].filter((value) => value !== null).length + filters.features.length
  + (filters.rental !== "any" ? 1 : 0) + (filters.withPhotos ? 1 : 0) + (filters.sources.length ? 1 : 0);
// Type and maximum price are preferences, so "Reset filters" leaves them alone.
const hasAnyFilter = (filters: Filters) =>
  countActiveFilters(filters) > 0 || filters.priceMin !== null || filters.availableBy !== null || filters.neededUntil !== null
  || filters.areaLat !== null;
// "1 Feb 2027 – 30 Jun 2027" for the period the student needs the home.
const periodLabel = (from: string | null, until: string | null) =>
  from && until ? `${formatDate(from)} – ${formatDate(until)}` : from ? `From ${formatDate(from)}` : until ? `Until ${formatDate(until)}` : "";
const NO_LISTINGS: Apartment[] = []; // the map in the setup shows no listings yet
const EMAIL_LANGUAGES: [EmailLanguage, string][] = [["English", "English"], ["German", "Deutsch"]];
type Draft = { text: string; engine: string };

// Map marker colour per reply level, the same colours as the "Reply …" badges in the list.
const replyColor = (apartment: Apartment) => (apartment.replyLevel === "likely" ? "#e55242" : "#4c2730");

type Screen = "welcome" | "about" | "onboarding" | "browse" | "result";
const WEIGHTS_NOTE = "How much each point counts is Flatty's own assumption. It is not yet checked against real replies.";
const signedShare = (reason: Reason) => `${reason.tone === "warn" ? "−" : "+"}${reason.share}%`;

const naturalList = (items: string[]) => {
  if (items.length <= 1) return items[0] || "";
  return `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
};

const riskLevel = (score: number) => {
  if (score < 25) return { label: "Low risk", tone: "low" };
  if (score < 55) return { label: "Medium risk", tone: "medium" };
  return { label: "High risk", tone: "high" };
};

export default function App() {
  const [screen, setScreen] = useState<Screen>("welcome");
  // Who is logged in. null until the back-end has answered (or turned out not to be running).
  const [session, setSession] = useState<Session | null>(null);
  const account = session?.user ?? null;
  // The log-in box: inside the welcome page, a dialog on every other screen.
  const [authBox, setAuthBox] = useState<{ mode: AuthMode; reason?: string } | null>(null);
  // True once the setup is finished (now, or earlier and remembered by the account).
  const [onboarded, setOnboarded] = useState(false);
  const [saved, setSaved] = useState<SavedItem[]>([]);
  const pendingSave = useRef<Apartment | null>(null); // the home to save right after logging in
  const [justSaved, setJustSaved] = useState(""); // id of the home whose heart was just tapped (it pops once)
  const savedPreferences = useRef("");
  const [aboutReturn, setAboutReturn] = useState<Screen>("welcome");
  const [step, setStep] = useState(1);
  const [fullName, setFullName] = useState("");
  const [languages, setLanguages] = useState(["English"]);
  const [budget, setBudget] = useState(1800);
  const [areas, setAreas] = useState(["Länggasse"]);
  const [showMap, setShowMap] = useState(false);
  const [destination, setDestination] = useState(DEFAULT_CAMPUS.name);
  const [priorities, setPriorities] = useState(["Public transport", "Grocery stores"]);
  const [country, setCountry] = useState("Switzerland");
  const [hasGuarantor, setHasGuarantor] = useState<"yes" | "no" | "">("");
  const [hasViewingPerson, setHasViewingPerson] = useState<"yes" | "no" | "">("");
  const [hasSwissNumber, setHasSwissNumber] = useState<"yes" | "no" | "">("");
  const [hasSwissBank, setHasSwissBank] = useState<"yes" | "no" | "">("");
  const [hasResidencePermit, setHasResidencePermit] = useState<"yes" | "no" | "">("");
  const [apartmentTypes, setApartmentTypes] = useState(["Studio"]);
  const [activeTab, setActiveTab] = useState<"search" | "link" | "saved">("search");
  const [link, setLink] = useState("");
  const [pastedText, setPastedText] = useState("");
  const [linkProblem, setLinkProblem] = useState<{ message: string; askForText: boolean } | null>(null);
  const [checkingLink, setCheckingLink] = useState(false);
  const [apartments, setApartments] = useState<Apartment[]>([]);
  const [totalMatches, setTotalMatches] = useState(0);
  const [liveData, setLiveData] = useState(false);
  const [loadingListings, setLoadingListings] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [listingError, setListingError] = useState("");
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [sort, setSort] = useState<SortKey>("reply");
  // The filter box opens in two steps: main filters, then "More filters".
  const [showMainFilters, setShowMainFilters] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [showBlockedSources, setShowBlockedSources] = useState(false);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [sourceCounts, setSourceCounts] = useState<Record<string, number>>({});
  const [photoIndex, setPhotoIndex] = useState(0);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [showPreferences, setShowPreferences] = useState(false);
  const [notice, setNotice] = useState("");
  const [listingStatus, setListingStatus] = useState<ListingStatus & { checking?: boolean }>({ available: null });
  const listingRequest = useRef(0);
  const openListingId = useRef("");
  const lastQuery = useRef("");
  const [selectedApartment, setSelectedApartment] = useState<Apartment>(demoApartments[0]);
  const [generated, setGenerated] = useState<"summary" | "email" | null>(null);
  const [generatedText, setGeneratedText] = useState("");
  const [generatedEngine, setGeneratedEngine] = useState("");
  const [generating, setGenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  // E-mail drafts come in both languages; each one appears as soon as it is written.
  const [emailLanguage, setEmailLanguage] = useState<EmailLanguage>("English");
  const [emails, setEmails] = useState<Partial<Record<EmailLanguage, Draft>>>({});
  const generateRequest = useRef(0);

  const progress = `${step * (100 / 6)}%`;
  const campus = findCampus(destination);
  const profile: Profile = {
    name: fullName.trim(), languages, budget, areas, destination, priorities, country, hasGuarantor, hasViewingPerson,
    hasSwissNumber, hasSwissBank, hasResidencePermit, apartmentTypes,
  };

  type YesNo = "yes" | "no" | "";
  const setProfile = (next: Profile) => {
    setFullName(next.name);
    setLanguages(next.languages);
    setBudget(next.budget);
    setAreas(next.areas);
    setDestination(next.destination);
    setPriorities(next.priorities);
    setCountry(next.country);
    setHasGuarantor(next.hasGuarantor as YesNo);
    setHasViewingPerson(next.hasViewingPerson as YesNo);
    setHasSwissNumber(next.hasSwissNumber as YesNo);
    setHasSwissBank(next.hasSwissBank as YesNo);
    setHasResidencePermit(next.hasResidencePermit as YesNo);
    setApartmentTypes(next.apartmentTypes);
  };
  const applyPreferences = (next: Profile) => {
    setProfile(next);
    setShowPreferences(false);
    setNotice(screen === "result" ? "Preferences saved. Your results update when you go back to them." : "Preferences saved. Your results are updating.");
  };

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const toggle = (value: string, values: string[], setter: (next: string[]) => void) => {
    setter(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  };

  // Accounts ---------------------------------------------------------------------------
  // Loads what the account remembers: profile, filters and sort order.
  const restore = (user: Account) => {
    if (user.profile) {
      setProfile(user.profile);
      setOnboarded(true);
    }
    if (user.filters) setFilters({ ...emptyFilters, ...user.filters, types: [], priceMax: null });
    if (user.sort) setSort(user.sort);
  };

  const refreshSaved = () => fetchSaved().then(setSaved).catch(() => undefined);

  useEffect(() => {
    let cancelled = false;
    fetchSession().then((next) => {
      if (cancelled) return;
      setSession(next);
      if (!next.user) return;
      restore(next.user);
      if (next.user.profile) setScreen("browse");
      refreshSaved();
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The session ended (expired, or logged out elsewhere): ask to log in again. True if it handled the error.
  const sessionEnded = (error: unknown) => {
    if (!(error instanceof ApiError && error.code === "login_required")) return false;
    setSession((current) => current && { ...current, user: null });
    setSaved([]);
    setShowPreferences(false);
    setScreen("welcome");
    setAuthBox({ mode: "login", reason: "Please log in to continue." });
    return true;
  };

  const addSaved = async (apartment: Apartment) => {
    setJustSaved(apartment.id);
    setSaved((current) => current.some((item) => item.listing.id === apartment.id)
      ? current : [{ listing: apartment, savedAt: new Date().toISOString(), available: null }, ...current]);
    try {
      await saveListing(apartment);
    } catch (error) {
      setSaved((current) => current.filter((item) => item.listing.id !== apartment.id));
      if (!sessionEnded(error)) setNotice(error instanceof ApiError ? error.message : "Couldn’t save this home. Please try again.");
    }
  };

  const removeSaved = async (item: SavedItem) => {
    setSaved((current) => current.filter((other) => other.listing.id !== item.listing.id));
    try {
      await unsaveListing(item.listing.id);
    } catch (error) {
      setSaved((current) => [item, ...current]);
      if (!sessionEnded(error)) setNotice("Couldn’t remove this home. Please try again.");
    }
  };

  const isSaved = (apartment: Apartment) => saved.some((item) => item.listing.id === apartment.id);
  const toggleSave = (apartment: Apartment) => {
    if (!account) {
      pendingSave.current = apartment;
      setAuthBox({ mode: "login", reason: "Log in to save this home." });
      return;
    }
    const item = saved.find((other) => other.listing.id === apartment.id);
    if (item) removeSaved(item);
    else addSaved(apartment);
  };

  const closeAuthBox = () => {
    pendingSave.current = null;
    setAuthBox(null);
  };

  const onLoggedIn = (user: Account) => {
    setSession((current) => current && { ...current, user });
    setAuthBox(null);
    const pending = pendingSave.current;
    pendingSave.current = null;
    refreshSaved().then(() => pending && addSaved(pending));
    if (user.profile) {
      // What the account remembers wins over what was typed in before logging in.
      restore(user);
      if (screen === "welcome" || screen === "onboarding") setScreen("browse");
      setNotice("Welcome back. Your profile is loaded.");
    } else if (onboarded) {
      if (screen === "welcome") setScreen("browse"); // the profile from this visit is saved below
    } else if (screen !== "onboarding") {
      setStep(1);
      setScreen("onboarding");
    }
  };

  // Logging out starts from a clean page, so nothing of the profile stays in the browser tab.
  const signOut = async () => {
    try {
      await logOut();
    } finally {
      window.location.reload();
    }
  };

  const removeAccount = async () => {
    if (!window.confirm("Delete your Flatty account? Your profile and saved homes are erased. This can’t be undone.")) return;
    try {
      await deleteAccount();
      window.location.reload();
    } catch (error) {
      if (!sessionEnded(error)) setNotice("Couldn’t delete the account. Please try again.");
    }
  };

  // "Start a new search" / "Continue your search", also used by the How-it-works page.
  const startSearch = () => {
    if (session?.private && !account) {
      setScreen("welcome");
      setAuthBox({ mode: "register" });
    } else if (onboarded) {
      setScreen("browse");
    } else {
      setStep(1);
      setScreen("onboarding");
    }
  };

  const openAbout = () => {
    setAboutReturn(screen);
    setScreen("about");
    window.scrollTo(0, 0);
  };
  // Back to where "How it works" was opened from, if that was the search.
  const leaveAbout = () => (aboutReturn === "browse" || aboutReturn === "result" ? setScreen(aboutReturn) : startSearch());

  const loadListings = async (append = false) => {
    const request = ++listingRequest.current;
    if (append) setLoadingMore(true);
    else setLoadingListings(true);
    setListingError("");
    try {
      const result = await matchListings(profile, { ...filters, types: apartmentTypes, priceMax: null }, sort, append ? apartments.length : 0);
      if (request !== listingRequest.current) return; // filters changed meanwhile
      setApartments(append ? [...apartments, ...result.listings] : result.listings);
      setTotalMatches(result.total);
      setLiveData(result.live);
      setSourceCounts(result.sourceCounts);
      setUpdatedAt(result.updatedAt);
      setRefreshing(Boolean(result.refreshing));
    } catch (error) {
      if (request === listingRequest.current && !sessionEnded(error)) setListingError(error instanceof Error ? error.message : "Couldn’t load listings.");
    } finally {
      if (request === listingRequest.current) {
        setLoadingListings(false);
        setLoadingMore(false);
      }
    }
  };

  // Reload whenever the browse screen is shown with a new profile, filter or sort order
  // (but not when returning from a listing, so the scroll position and loaded pages stay).
  const queryKey = JSON.stringify({ profile, filters, sort });
  useEffect(() => {
    if (screen !== "browse" || queryKey === lastQuery.current) return;
    const timer = window.setTimeout(() => {
      lastQuery.current = queryKey;
      loadListings();
    }, 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen, queryKey]);

  useEffect(() => {
    if (screen === "browse" && sources.length === 0) fetchSources().then(setSources);
  }, [screen, sources.length]);

  // Remember the profile, filters and sort order of a logged-in student (shortly after each change).
  useEffect(() => {
    if (!account || !onboarded || queryKey === savedPreferences.current) return;
    const timer = window.setTimeout(() => {
      savedPreferences.current = queryKey;
      savePreferences(profile, filters, sort).catch((error) => {
        savedPreferences.current = "";
        sessionEnded(error);
      });
    }, 800);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account, onboarded, queryKey]);

  // The Saved tab shows fresh scores, and whether each home is still online.
  useEffect(() => {
    if (screen === "browse" && activeTab === "saved" && account) refreshSaved();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen, activeTab, account?.email]);

  const enabledSources = sources.filter((source) => source.scraping_allowed);
  const blockedSources = sources.filter((source) => !source.scraping_allowed);
  const activeSources = filters.sources.length ? filters.sources : enabledSources.map((source) => source.key);

  const updateFilters = (patch: Partial<Filters>) => setFilters((current) => ({ ...current, ...patch }));

  const toggleSource = (key: string) => {
    const next = activeSources.includes(key) ? activeSources.filter((item) => item !== key) : [...activeSources, key];
    if (next.length === 0) return; // keep at least one website selected
    updateFilters({ sources: next.length === enabledSources.length ? [] : next });
  };

  // The type chips edit the same home types as the preferences panel.
  const typeSelected = (value: string) =>
    value === "Proper flat" ? apartmentTypes.some((type) => APARTMENT_KINDS.includes(type)) : apartmentTypes.includes(value);
  const toggleType = (value: string) => {
    if (value === "Proper flat") {
      setApartmentTypes(typeSelected(value) ? apartmentTypes.filter((type) => !APARTMENT_KINDS.includes(type)) : [...apartmentTypes, "Proper flat"]);
    } else {
      setApartmentTypes(typeSelected(value) ? apartmentTypes.filter((type) => type !== value) : [...apartmentTypes, value]);
    }
  };

  const numberOrNull = (value: string) => (value.trim() === "" ? null : Number(value));

  // Shown in the closed filter box, so the current search is visible without opening it.
  const selectedTypeLabels = TYPE_FILTERS.filter(([value]) => typeSelected(value)).map(([, label]) => label);
  const moreFilterCount = countActiveFilters(filters);
  const filterSummary = [
    selectedTypeLabels.length ? selectedTypeLabels.join(", ") : "All types",
    `CHF ${(filters.priceMin ?? BUDGET_MIN).toLocaleString("de-CH")} – ${budget.toLocaleString("de-CH")}`,
    periodLabel(filters.availableBy, filters.neededUntil),
    filters.areaLat !== null ? `Within ${filters.radiusKm} km` : "",
    moreFilterCount ? `${moreFilterCount} more` : "",
  ].filter(Boolean);
  const toggleMainFilters = () => {
    if (showMainFilters) setShowFilters(false);
    setShowMainFilters(!showMainFilters);
  };

  const finishOnboarding = () => {
    setOnboarded(true);
    setScreen("browse");
    setGenerated(null);
  };

  const checkApartment = (apartment: Apartment = apartments[0] ?? demoApartments[0]) => {
    setSelectedApartment(apartment);
    setGenerated(null);
    setGeneratedText("");
    setPhotoIndex(0);
    setScreen("result");
    window.scrollTo(0, 0);
    openListingId.current = apartment.id;
    verifyOnline(apartment);
  };

  // Re-check at the source that the listing is still online (one request, at most hourly per listing).
  const verifyOnline = async (apartment: Apartment) => {
    if (!liveData || !["flatfox", "unibe", "studentlodge"].includes(apartment.source)) {
      setListingStatus({ available: null });
      return;
    }
    setListingStatus({ available: null, checking: true });
    const status = await checkListingOnline(apartment.id);
    if (openListingId.current === apartment.id) setListingStatus(status); // ignore if the student moved on
    if (status.available === false) {
      setApartments((current) => current.filter((item) => item.id !== apartment.id));
      setTotalMatches((current) => Math.max(0, current - 1));
      setSaved((current) => current.map((item) => (item.listing.id === apartment.id ? { ...item, available: false } : item)));
    }
  };

  const listingGone = listingStatus.available === false;

  const checkPastedListing = async (input: { url?: string; text?: string }) => {
    setCheckingLink(true);
    setLinkProblem(null);
    try {
      checkApartment(await checkLink(profile, input));
    } catch (error) {
      if (error instanceof ApiUnavailable) {
        checkApartment(demoApartments[0]);
      } else if (error instanceof ApiError) {
        setLinkProblem({ message: error.message, askForText: ["source_blocked", "robots_disallow", "fetch_failed", "not_html"].includes(error.code) });
      } else {
        setLinkProblem({ message: "Something went wrong. Please try again.", askForText: true });
      }
    } finally {
      setCheckingLink(false);
    }
  };

  // Used only when the back-end can't be reached (demo mode).
  const fallbackSummary = () =>
    `${selectedApartment.title} in ${selectedApartment.area}. ${selectedApartment.meta} for ${selectedApartment.rent} per month. ${[...(selectedApartment.notes ?? []), ...selectedApartment.reasons].map((reason) => reason.title).join(", ")}.`;
  const fallbackEmail = (language: EmailLanguage) => {
    const name = fullName.trim();
    if (language === "German") {
      return [
        "Guten Tag",
        "",
        `Ich interessiere mich für Ihr Inserat «${selectedApartment.originalTitle || selectedApartment.title}» (${selectedApartment.area}).`
          + (name ? ` Ich heisse ${name}.` : "") + ` Ich studiere ${campus.schoolDe}.`,
        "",
        "Gerne sende ich Ihnen meine Unterlagen und komme für eine Besichtigung vorbei.",
        "",
        "Freundliche Grüsse",
        ...(name ? [name] : []),
      ].join("\n");
    }
    return [
      "Hello,",
      "",
      `I am interested in your listing “${selectedApartment.title}” in ${selectedApartment.area}.` + (name ? ` My name is ${name}.` : "")
        + (country && country !== "Other" ? ` I am from ${country} and study at ${campus.school}.` : ` I study at ${campus.school}.`),
      "",
      `I speak ${naturalList(languages)}.`
        + (hasGuarantor === "yes" ? " I have a guarantor who lives in Switzerland." : "")
        + (hasViewingPerson === "yes" ? " Someone can attend a viewing on my behalf." : ""),
      "I would be happy to send my documents and to arrange a viewing.",
      "",
      "Kind regards",
      ...(name ? [name] : []),
    ].join("\n");
  };

  // True if the listing went offline meanwhile (then nothing is drafted for it).
  const listingWentOffline = (error: unknown, request: number) => {
    if (!(error instanceof ApiError && error.code === "listing_inactive")) return false;
    if (request === generateRequest.current) {
      setListingStatus({ available: false, message: error.message });
      setGenerated(null);
      setGenerating(false);
    }
    return true;
  };

  const generate = async (kind: "summary" | "email") => {
    const request = ++generateRequest.current;
    setGenerated(kind);
    setCopied(false);
    if (kind === "email") {
      // Both versions are written: the listing's language first, because that is the one to send.
      const first: EmailLanguage = selectedApartment.language === "German" ? "German" : "English";
      setEmailLanguage(first);
      setEmails({});
      await Promise.all([first, first === "German" ? "English" : "German"].map(async (item) => {
        const language = item as EmailLanguage;
        let draft: Draft;
        try {
          draft = await generateText("email", selectedApartment, profile, language);
        } catch (error) {
          if (listingWentOffline(error, request)) return;
          draft = { text: fallbackEmail(language), engine: "template" };
        }
        if (request === generateRequest.current) setEmails((current) => ({ ...current, [language]: draft }));
      }));
      return;
    }
    setGenerating(true);
    let text: string, engine: string;
    try {
      ({ text, engine } = await generateText(kind, selectedApartment, profile));
    } catch (error) {
      if (listingWentOffline(error, request)) return;
      [text, engine] = [fallbackSummary(), "template"];
    }
    if (request !== generateRequest.current) return; // a newer request replaced this one
    setGeneratedText(text);
    setGeneratedEngine(engine);
    setGenerating(false);
  };

  // What the "Use this listing" card shows right now.
  const emailDraft = emails[emailLanguage];
  const shownText = generated === "email" ? emailDraft?.text ?? "" : generatedText;
  const shownEngine = generated === "email" ? emailDraft?.engine ?? "" : generatedEngine;
  const writing = generated === "email" ? !emailDraft : generating;

  const copyGenerated = async () => {
    await navigator.clipboard.writeText(shownText);
    setCopied(true);
  };

  const heartClass = (apartment: Apartment, base: string) =>
    !isSaved(apartment) ? base : justSaved === apartment.id ? `${base} saved pop` : `${base} saved`;

  // One listing card, used by the results and by the Saved tab.
  const listingCard = (apartment: Apartment, index: number, gone = false) => {
    const liked = isSaved(apartment);
    return (
      <article className={gone ? "apartment-card gone" : "apartment-card"} key={apartment.id}>
        <div className={`apartment-visual visual-${(index % 3) + 1}`}>
          {apartment.images[0] ? (
            <img alt="" className="apartment-photo" loading="lazy" referrerPolicy="no-referrer" src={apartment.images[0].thumb} />
          ) : (
            <div className="pixel-windows"><i /><i /><i /><i /></div>
          )}
          {gone
            ? <span className="reply-badge unlikely">No longer online</span>
            : <span className={`reply-badge ${apartment.replyLevel}`}>Reply {apartment.replyLabel.toLowerCase()}</span>}
          <span className={`risk-badge ${riskLevel(apartment.risk).tone}`}>{apartment.risk}% risk</span>
          <button
            aria-label={liked ? `Remove ${apartment.title} from your saved homes` : `Save ${apartment.title}`} aria-pressed={liked}
            className={heartClass(apartment, "save-button")} onClick={() => toggleSave(apartment)} title={liked ? "Saved" : "Save"} type="button"
          >
            <Icon name="heart" size={17} />
          </button>
        </div>
        <div className="apartment-info">
          <span className="area-label"><Icon name="map" size={13} /> {apartment.area}<em>· {apartment.sourceName}</em></span>
          <h2>{apartment.title}</h2>
          <p>{apartment.meta}</p>
          <div className="mini-tags">{apartment.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
        </div>
        <div className="apartment-action"><strong>{apartment.rent}<small>/month</small></strong><button onClick={() => checkApartment(apartment)} type="button">Check listing <Icon name="arrow" size={16} /></button></div>
      </article>
    );
  };

  // Nothing is drawn until we know whether someone is logged in, so the welcome page doesn't flash by.
  if (!session) return <div className="app-shell" />;

  return (
    <div className="app-shell">
      {screen !== "welcome" && (
        <header className="topbar">
          <button className="brand" onClick={() => { setScreen("welcome"); closeAuthBox(); }} type="button">
            <span className="brand-mark"><Icon name="home" size={16} /></span>
            <span>Flatty</span>
          </button>
          {screen === "about" && <span className="header-pref">How Flatty works</span>}
          <nav className="topbar-actions" aria-label="Flatty">
            {(screen === "browse" || screen === "result") && (
              <>
                <button className="topbar-link" onClick={openAbout} type="button">How it works</button>
                <button aria-haspopup="dialog" className="edit-button" onClick={() => setShowPreferences(true)} type="button">
                  Edit profile
                </button>
              </>
            )}
            {screen === "about" && (
              <button className="edit-button" onClick={leaveAbout} type="button">
                {onboarded ? "Back to your search" : "Start a search"}
              </button>
            )}
            {screen !== "about" && (account
              ? <button className="topbar-link" onClick={signOut} type="button">Log out</button>
              : <button className="topbar-link" onClick={() => setAuthBox({ mode: "login" })} type="button">Log in</button>)}
            {/* Online test: forget the developer password on this device. */}
            {session.siteGate && <a className="topbar-link" href="/__gate/logout">Lock site</a>}
          </nav>
        </header>
      )}

      {screen === "welcome" && (
        <main className="welcome-page">
          <div className="welcome-backdrop" aria-hidden="true">
            <span className="geo-circle" />
            <span className="swiss-cross"><i /><i /></span>
            <span className="alpine-line" />
            <span className="rail-line"><i /><i /><i /><i /><i /></span>
            <span className="pattern-label">46.9480° N · 7.4474° E</span>
          </div>
          <section className="welcome-copy">
            <span className="step-code">APARTMENT MATCHING, MADE SIMPLE</span>
            <h1>Find a flat<br />that fits you.</h1>
            <p>Set your budget, commute, and everyday needs. Flatty checks the rest.</p>

            {!authBox ? (
              <>
                <div className="welcome-actions">
                  <button className="welcome-primary" onClick={startSearch} type="button">
                    {onboarded ? "Continue your search" : "Start a new search"} <Icon name="arrow" size={19} />
                  </button>
                  {account
                    ? <button className="login-trigger" onClick={signOut} type="button">Log out</button>
                    : <button className="login-trigger" onClick={() => setAuthBox({ mode: "login" })} type="button">Log in</button>}
                  <button className="info-trigger" onClick={openAbout} type="button">
                    How it works
                  </button>
                </div>
                {account && <p className="welcome-account">Signed in as {account.email}</p>}
                {session.private && !account && <p className="welcome-account">Private test · you need an invitation to use Flatty</p>}
              </>
            ) : (
              <AuthBox initialMode={authBox.mode} key={authBox.mode} onCancel={closeAuthBox} onDone={onLoggedIn} reason={authBox.reason} session={session} />
            )}
          </section>
        </main>
      )}

      {screen === "about" && (
        <HowItWorks ctaLabel={onboarded && !(session.private && !account) ? "Back to your search" : "Start matching"} onStart={leaveAbout} />
      )}

      {screen === "onboarding" && (
        <main className="onboarding">
          <div className="pixel-house" aria-hidden="true"><i /><i /><i /><i /></div>
          <div className="onboarding-top">
            <span className="step-code">SETUP / 0{step}</span>
            <span>{step} of 6</span>
          </div>
          <div className="progress"><span style={{ width: progress }} /></div>

          {step === 1 && (
            <section className="step-content">
              <h1>Let’s find your fit.</h1>
              <p>Start with language and budget.</p>
              <div className="question">
                <label>Which languages do you speak?</label>
                <div className="chips">
                  {/* The four main languages, plus any others the student added from the list below. */}
                  {[...MAIN_LANGUAGES, ...languages.filter((language) => !MAIN_LANGUAGES.includes(language))].map((language) => (
                    <button aria-pressed={languages.includes(language)} className={languages.includes(language) ? "chip active" : "chip"} key={language} onClick={() => toggle(language, languages, setLanguages)} type="button">
                      {languages.includes(language) && <Icon name="check" size={14} />}{language}
                    </button>
                  ))}
                </div>
                <select
                  aria-label="Add another language" className="option-select" value=""
                  onChange={(event) => event.target.value && setLanguages([...languages, event.target.value])}
                >
                  <option value="">Other languages…</option>
                  {OTHER_LANGUAGES.filter((language) => !languages.includes(language)).map((language) => <option key={language}>{language}</option>)}
                </select>
              </div>
              <div className="question">
                <div className="label-row"><label>Maximum monthly rent</label><strong>CHF {budget.toLocaleString("de-CH")}</strong></div>
                <input className="range-input" min={BUDGET_MIN} max={BUDGET_MAX} step="50" type="range" value={budget} onChange={(event) => setBudget(Number(event.target.value))} />
                <div className="range-labels"><span>CHF 400</span><span>CHF 3,500</span></div>
              </div>
            </section>
          )}

          {step === 2 && (
            <section className="step-content">
              <h1>Where should it be?</h1>
              <p>Tell us where you study and where you would like to live.</p>
              <div className="question">
                <label htmlFor="destination">Where do you study?</label>
                <select className="option-select campus-select" id="destination" onChange={(event) => setDestination(event.target.value)} value={campus.name}>
                  {CAMPUS_GROUPS.map((group) => (
                    <optgroup key={group} label={group}>
                      {CAMPUSES.filter((item) => item.group === group).map((item) => <option key={item.name}>{item.name}</option>)}
                    </optgroup>
                  ))}
                </select>
                <span className="input-note">Flatty estimates the commute from every home to this place.</span>
              </div>
              <div className="question">
                <label>Preferred areas</label>
                <div className="chips">
                  {AREAS.map((area) => (
                    <button aria-pressed={areas.includes(area)} className={areas.includes(area) ? "chip active" : "chip"} key={area} onClick={() => toggle(area, areas, setAreas)} type="button">
                      {areas.includes(area) && <Icon name="check" size={14} />}{area}
                    </button>
                  ))}
                  <button aria-expanded={showMap} className={showMap || filters.areaLat !== null ? "chip active" : "chip"} onClick={() => setShowMap((value) => !value)} type="button"><Icon name="map" size={15} /> Choose on map</button>
                </div>
                {showMap && (
                  <div className="setup-map">
                    <MapRadius
                      area={filters.areaLat !== null && filters.areaLng !== null ? { lat: filters.areaLat, lng: filters.areaLng } : null}
                      centre={{ name: campus.short, lat: campus.lat, lng: campus.lng }}
                      colorFor={replyColor}
                      listings={NO_LISTINGS}
                      onAreaChange={(area, radiusKm) => updateFilters({ areaLat: area?.lat ?? null, areaLng: area?.lng ?? null, radiusKm })}
                      onSelect={checkApartment}
                      radiusKm={filters.radiusKm}
                    />
                    <span className="input-note">Only homes inside the circle are shown. You can change the area later under Filters.</span>
                  </div>
                )}
              </div>
            </section>
          )}

          {step === 3 && (
            <section className="step-content">
              <h1>What matters nearby?</h1>
              <p>Select your everyday essentials.</p>
              <div className="priority-grid">
                {PRIORITIES.map(([name, icon, defaultNote]) => [name, icon, name === "Short commute" ? `To ${campus.short}` : defaultNote] as const).map(([name, icon, note]) => (
                  <button className={priorities.includes(name) ? "priority active" : "priority"} key={name} onClick={() => toggle(name, priorities, setPriorities)} type="button">
                    <span className="priority-icon"><Icon name={icon} size={21} /></span>
                    <span><strong>{name}</strong><small>{note}</small></span>
                    <span className="pixel-check">{priorities.includes(name) && <Icon name="check" size={13} />}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {step === 4 && (
            <section className="step-content">
              <h1>Tell us about you.</h1>
              <p>This helps personalize your application.</p>
              <div className="question">
                <label htmlFor="full-name">Your name</label>
                <div className="text-input">
                  <Icon name="mail" size={18} />
                  <input autoComplete="name" id="full-name" maxLength={80} onChange={(event) => setFullName(event.target.value)} placeholder="First and last name" value={fullName} />
                </div>
                <span className="input-note">Only used to sign your application e-mails.</span>
              </div>
              <div className="question">
                <label htmlFor="country">Where are you from?</label>
                <select className="option-select country-select" id="country" value={country} onChange={(event) => setCountry(event.target.value)}>
                  {COUNTRIES.map((item) => <option key={item}>{item}</option>)}
                </select>
              </div>
              <div className="question support-question">
                <label>Do you have a guarantor who lives in Switzerland?</label>
                <div className="binary-row">
                  <button className={hasGuarantor === "yes" ? "binary-choice active" : "binary-choice"} onClick={() => setHasGuarantor("yes")} type="button">Yes</button>
                  <button className={hasGuarantor === "no" ? "binary-choice active" : "binary-choice"} onClick={() => setHasGuarantor("no")} type="button">No</button>
                </div>
              </div>
              <div className="question support-question">
                <label>Can someone attend accommodation viewings for you?</label>
                <div className="binary-row">
                  <button className={hasViewingPerson === "yes" ? "binary-choice active" : "binary-choice"} onClick={() => setHasViewingPerson("yes")} type="button">Yes</button>
                  <button className={hasViewingPerson === "no" ? "binary-choice active" : "binary-choice"} onClick={() => setHasViewingPerson("no")} type="button">No</button>
                </div>
              </div>
            </section>
          )}

          {step === 5 && (
            <section className="step-content">
              <h1>Your Swiss setup.</h1>
              <p>Tell us which local essentials you already have.</p>
              <div className="setup-checks">
                {[
                  ["Swiss phone number", hasSwissNumber, setHasSwissNumber],
                  ["Swiss bank account", hasSwissBank, setHasSwissBank],
                  ["Residence permit", hasResidencePermit, setHasResidencePermit],
                ].map(([label, value, setter]) => (
                  <div className="question support-question setup-check" key={label as string}>
                    <label>{`Do you have a ${label as string}?`}</label>
                    <div className="binary-row">
                      <button
                        className={value === "yes" ? "binary-choice active" : "binary-choice"}
                        onClick={() => (setter as typeof setHasSwissNumber)("yes")}
                        type="button"
                      >
                        Yes
                      </button>
                      <button
                        className={value === "no" ? "binary-choice active" : "binary-choice"}
                        onClick={() => (setter as typeof setHasSwissNumber)("no")}
                        type="button"
                      >
                        No
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {step === 6 && (
            <section className="step-content">
              <h1>What are you looking for?</h1>
              <p>Choose your preferred apartment type.</p>
              <div className="apartment-types">
                {APARTMENT_TYPES.map(([type, note]) => (
                  <button
                    className={apartmentTypes.includes(type) ? "type-card active" : "type-card"}
                    key={type}
                    onClick={() => toggle(type, apartmentTypes, setApartmentTypes)}
                    type="button"
                  >
                    <span className="type-icon"><Icon name="home" size={20} /></span>
                    <span><strong>{type}</strong><small>{note}</small></span>
                    <span className="pixel-check">{apartmentTypes.includes(type) && <Icon name="check" size={13} />}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          <div className="onboarding-actions">
            {step > 1 ? <button className="back-button" onClick={() => setStep(step - 1)} type="button"><Icon name="back" size={17} /> Back</button> : <span />}
            <button className="primary-button" onClick={() => step < 6 ? setStep(step + 1) : finishOnboarding()} type="button">
              {step < 6 ? "Continue" : "Show apartments"} <Icon name="arrow" size={17} />
            </button>
          </div>
          <p className="setup-privacy">
            <span>PRIVATE BY DEFAULT</span>
            We only use your data to adapt application details and offer better findings.
          </p>
        </main>
      )}

      {screen === "browse" && (
        <main className="browse-page">
          <div className="browse-heading">
            <div><span className="step-code">YOUR SEARCH</span><h1>Find your flat.</h1></div>
            <div className="pixel-pin" aria-hidden="true" />
          </div>
          <div className="tabs">
            <button className={activeTab === "search" ? "active" : ""} onClick={() => setActiveTab("search")} type="button"><Icon name="search" size={17} /> Search apartments</button>
            <button className={activeTab === "link" ? "active" : ""} onClick={() => setActiveTab("link")} type="button"><Icon name="link" size={17} /> Paste a link</button>
            <button className={activeTab === "saved" ? "active" : ""} onClick={() => setActiveTab("saved")} type="button">
              <Icon name="heart" size={17} /> Saved{saved.length > 0 && <span className="tab-count">{saved.length}</span>}
            </button>
          </div>

          {activeTab === "saved" ? (
            <section className="listings saved-list">
              {!account ? (
                <div className="link-panel">
                  <span className="big-link-icon"><Icon name="heart" size={26} /></span>
                  <h2>Keep the homes you like</h2>
                  <p>Log in or create an account. Flatty then remembers your profile and every home you save.</p>
                  <div className="saved-auth">
                    <button className="primary-button" onClick={() => setAuthBox({ mode: "register" })} type="button">Create an account <Icon name="arrow" size={17} /></button>
                    <button className="login-trigger" onClick={() => setAuthBox({ mode: "login" })} type="button">Log in</button>
                  </div>
                </div>
              ) : saved.length === 0 ? (
                <p className="list-message">No saved homes yet. Tap the heart on a listing to keep it here.</p>
              ) : (
                <>
                  <div className="filter-line">
                    <span>
                      {saved.length} saved {saved.length === 1 ? "home" : "homes"}
                      <small className="source-note">Newest first · scores are for your current profile</small>
                    </span>
                  </div>
                  <div className="listing-stack">
                    {saved.map((item, index) => listingCard(item.listing, index, item.available === false))}
                  </div>
                </>
              )}
            </section>
          ) : activeTab === "search" ? (
            <section className="listings">
              <div className={showMainFilters ? "filter-box open" : "filter-box"}>
                <div className="filter-box-head">
                  <button aria-controls="main-filters" aria-expanded={showMainFilters} className="filter-box-toggle" onClick={toggleMainFilters} type="button">
                    <span className="filter-box-title">Filters</span>
                    <span className="filter-summary">
                      {filterSummary.map((item) => <span key={item}>{item}</span>)}
                    </span>
                    <span className="filter-box-action">
                      {showMainFilters ? "Hide" : "Edit"}
                      <span className={showMainFilters ? "chevron open" : "chevron"}><Icon name="chevron" size={14} /></span>
                    </span>
                  </button>
                  {hasAnyFilter(filters) && (
                    <button className="reset-filters" onClick={() => setFilters(emptyFilters)} type="button">Reset filters</button>
                  )}
                </div>
                {showMainFilters && (<>
                <div className="quick-filters" id="main-filters">
                  <div className="quick-main">
                    <div className="filter-group">
                      <span>Type</span>
                      <div className="chips">
                        {TYPE_FILTERS.map(([value, label, hint]) => {
                          const active = typeSelected(value);
                          return (
                            <button aria-pressed={active} className={active ? "chip active" : "chip"} key={value} onClick={() => toggleType(value)} title={hint} type="button">
                              {active && <Icon name="check" size={14} />}{label}
                            </button>
                          );
                        })}
                      </div>
                      <small className="filter-hint">
                        {apartmentTypes.length ? "From your preferences. " : "All types shown. "}A studio has its own kitchen and bathroom; rooms share a kitchen.
                      </small>
                    </div>
                    <div className="filter-group quick-price">
                      <div className="label-row">
                        <span>Monthly rent</span>
                        <strong>CHF {(filters.priceMin ?? BUDGET_MIN).toLocaleString("de-CH")} – {budget.toLocaleString("de-CH")}</strong>
                      </div>
                      <div className="dual-range" style={{ "--from": `${pricePercent(filters.priceMin ?? BUDGET_MIN)}%`, "--to": `${pricePercent(budget)}%` } as React.CSSProperties}>
                        <input
                          aria-label="Minimum rent" max={BUDGET_MAX} min={BUDGET_MIN} step="50" type="range" value={filters.priceMin ?? BUDGET_MIN}
                          onChange={(event) => {
                            const value = Math.min(Number(event.target.value), budget - PRICE_GAP);
                            updateFilters({ priceMin: value <= BUDGET_MIN ? null : value });
                          }}
                        />
                        <input
                          aria-label="Maximum rent (your budget)" max={BUDGET_MAX} min={BUDGET_MIN} step="50" type="range" value={budget}
                          onChange={(event) => setBudget(Math.max(Number(event.target.value), (filters.priceMin ?? BUDGET_MIN) + PRICE_GAP))}
                        />
                      </div>
                      <small className="filter-hint">The maximum is your budget. Listings up to 15 % above it are shown with a warning.</small>
                    </div>
                    <div className="filter-group quick-dates">
                      <span>When do you need it?</span>
                      <div className="date-range">
                        <label className="filter-field">
                          <span>From</span>
                          <input
                            onChange={(event) => {
                              const from = event.target.value || null;
                              // An "until" before the new "from" makes no sense, so it is cleared.
                              updateFilters({ availableBy: from, neededUntil: from && filters.neededUntil && filters.neededUntil < from ? null : filters.neededUntil });
                            }}
                            type="date" value={filters.availableBy ?? ""}
                          />
                        </label>
                        <label className="filter-field">
                          <span>Until</span>
                          <input
                            min={filters.availableBy ?? undefined}
                            onChange={(event) => {
                              const until = event.target.value || null;
                              updateFilters({ neededUntil: until && filters.availableBy && until < filters.availableBy ? filters.availableBy : until });
                            }}
                            type="date" value={filters.neededUntil ?? ""}
                          />
                        </label>
                      </div>
                      <small className="filter-hint">Leave “Until” empty for an open-ended stay. Homes that are free too late, or that end before you leave, are hidden.</small>
                    </div>
                  </div>
                  <MapRadius
                    area={filters.areaLat !== null && filters.areaLng !== null ? { lat: filters.areaLat, lng: filters.areaLng } : null}
                    colorFor={replyColor}
                    listings={apartments}
                    onAreaChange={(area, radiusKm) => updateFilters({ areaLat: area?.lat ?? null, areaLng: area?.lng ?? null, radiusKm })}
                    onSelect={checkApartment}
                    centre={{ name: campus.short, lat: campus.lat, lng: campus.lng }}
                    radiusKm={filters.radiusKm}
                  />
                </div>
                {showFilters && (
                  <div className="filter-panel">
                    <div className="filter-group">
                      <span>Must have</span>
                      <div className="chips">
                        {FEATURE_FILTERS.map((feature) => (
                          <button aria-pressed={filters.features.includes(feature)} className={filters.features.includes(feature) ? "chip active" : "chip"} key={feature} onClick={() => updateFilters({ features: filters.features.includes(feature) ? filters.features.filter((item) => item !== feature) : [...filters.features, feature] })} type="button">
                            {filters.features.includes(feature) && <Icon name="check" size={14} />}{feature}
                          </button>
                        ))}
                      </div>
                    </div>
                    <label className="filter-field">
                      <span>Rooms from</span>
                      <select onChange={(event) => updateFilters({ roomsMin: numberOrNull(event.target.value) })} value={filters.roomsMin ?? ""}>
                        <option value="">Any</option>
                        {ROOM_OPTIONS.map((rooms) => <option key={rooms} value={rooms}>{rooms}+</option>)}
                      </select>
                    </label>
                    <label className="filter-field">
                      <span>Size from (m²)</span>
                      <input inputMode="numeric" min={0} onChange={(event) => updateFilters({ surfaceMin: numberOrNull(event.target.value) })} placeholder="Any" type="number" value={filters.surfaceMin ?? ""} />
                    </label>
                    <label className="filter-field">
                      <span>Scam risk</span>
                      <select onChange={(event) => updateFilters({ maxRisk: numberOrNull(event.target.value) })} value={filters.maxRisk ?? ""}>
                        <option value="">Show all (with warnings)</option>
                        <option value="54">Hide high risk</option>
                        <option value="24">Low risk only</option>
                      </select>
                    </label>
                    <label className="filter-field">
                      <span>Rental period</span>
                      <select onChange={(event) => updateFilters({ rental: event.target.value as Filters["rental"] })} value={filters.rental}>
                        <option value="any">Any</option>
                        <option value="permanent">Long-term only</option>
                        <option value="temporary">Temporary / sublet only</option>
                      </select>
                    </label>
                    <label className="filter-check">
                      <input checked={filters.withPhotos} onChange={(event) => updateFilters({ withPhotos: event.target.checked })} type="checkbox" />
                      <span>With photos only</span>
                    </label>
                    {liveData && enabledSources.length > 0 && (
                      <div className="filter-group">
                        <span>Websites</span>
                        <div className="chips">
                          {enabledSources.map((source) => (
                            <button
                              className={activeSources.includes(source.key) ? "chip active" : "chip"}
                              key={source.key}
                              onClick={() => toggleSource(source.key)}
                              type="button"
                            >
                              {activeSources.includes(source.key) && <Icon name="check" size={14} />}
                              {source.name}
                              <span className="chip-count">{sourceCounts[source.key] ?? 0}</span>
                            </button>
                          ))}
                        </div>
                        {blockedSources.length > 0 && (
                          <button className="info-trigger blocked-toggle" onClick={() => setShowBlockedSources((value) => !value)} type="button">
                            Why not {blockedSources.slice(0, 3).map((source) => source.name).join(", ")}…?
                          </button>
                        )}
                        {showBlockedSources && (
                          <ul className="blocked-sources">
                            {blockedSources.map((source) => <li key={source.key}><strong>{source.name}</strong> {source.decision}</li>)}
                          </ul>
                        )}
                      </div>
                    )}
                  </div>
                )}
                <div className="filter-box-foot">
                  <button className={showFilters ? "filter-toggle active" : "filter-toggle"} aria-expanded={showFilters} onClick={() => setShowFilters((value) => !value)} type="button">
                    {showFilters ? "Fewer filters" : "More filters"}{moreFilterCount > 0 && ` (${moreFilterCount})`} <span className={showFilters ? "chevron open" : "chevron"}><Icon name="chevron" size={14} /></span>
                  </button>
                </div>
                </>)}
              </div>

              <div className="filter-line">
                <span>
                  {loadingListings ? "Checking listings…" : `${totalMatches} matching apartments`}
                  <small className="source-note">
                    {liveData
                      ? `Showing ${apartments.length} of ${totalMatches} · ${refreshing ? "refreshing listings now…" : updatedAt ? `updated ${timeAgo(updatedAt)}` : "not updated yet"}`
                      : "Demo data · start the local back-end for live listings"}
                  </small>
                </span>
                <div className="filter-controls">
                  <select aria-label="Sort listings" className="sort-select" onChange={(event) => setSort(event.target.value as SortKey)} value={sort}>
                    {SORT_OPTIONS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                  </select>
                </div>
              </div>


              {listingError && <p className="list-message">{listingError}</p>}
              {!loadingListings && !listingError && apartments.length === 0 && (
                <p className="list-message">No listings match these settings. Try a higher budget, fewer filters or more websites.</p>
              )}
              <div className={loadingListings ? "listing-stack is-loading" : "listing-stack"}>
                {apartments.map((apartment, index) => listingCard(apartment, index))}
              </div>
              {liveData && apartments.length < totalMatches && !loadingListings && (
                <button className="show-more" disabled={loadingMore} onClick={() => loadListings(true)} type="button">
                  {loadingMore ? "Loading…" : `Show ${Math.min(PAGE_SIZE, totalMatches - apartments.length)} more`} <Icon name="chevron" size={15} />
                </button>
              )}
            </section>
          ) : (
            <section className="link-panel">
              <span className="big-link-icon"><Icon name="link" size={28} /></span>
              <h2>Paste an apartment link</h2>
              <p>Flatfox, Uni Bern and studentlodge links are checked directly. For sites that don’t allow automated reading, paste the listing text.</p>
              <div className="link-input">
                <input value={link} onChange={(event) => setLink(event.target.value)} placeholder="https://..." />
                <button onClick={() => checkPastedListing({ url: link })} disabled={!link.trim() || checkingLink} type="button">
                  {checkingLink ? "Checking…" : "Check listing"} <Icon name="arrow" size={17} />
                </button>
              </div>
              {linkProblem && <p className="link-error">{linkProblem.message}</p>}
              {linkProblem?.askForText && (
                <div className="paste-text">
                  <textarea
                    onChange={(event) => setPastedText(event.target.value)}
                    placeholder="Paste the title, rent, size and description of the listing here"
                    rows={7}
                    value={pastedText}
                  />
                  <button className="primary-button" disabled={!pastedText.trim() || checkingLink} onClick={() => checkPastedListing({ text: pastedText })} type="button">
                    Check text <Icon name="arrow" size={17} />
                  </button>
                </div>
              )}
            </section>
          )}
        </main>
      )}

      {screen === "result" && (
        <main className="result-page">
          <button className="back-link" onClick={() => setScreen("browse")} type="button"><Icon name="back" size={17} /> {activeTab === "saved" ? "Back to saved homes" : "Back to results"}</button>
          {listingStatus.checking && <p className="online-status checking">Checking that this listing is still online…</p>}
          {listingGone && (
            <p className="online-status gone">
              <strong>No longer available.</strong> {listingStatus.message ?? "This listing has been taken offline."} Flatty has removed it from your results.
            </p>
          )}
          {listingStatus.available === true && listingStatus.checkedAt && (
            <p className="online-status ok">Still online at {selectedApartment.sourceName} · checked {timeAgo(listingStatus.checkedAt)}</p>
          )}
          {listingStatus.available === null && !listingStatus.checking && listingStatus.message && (
            <p className="online-status unknown">{listingStatus.message}</p>
          )}

          <header className="listing-head">
            <span className="step-code">THE LISTING</span>
            <div className="listing-title-row">
              <h1>{selectedApartment.title}</h1>
              <button
                aria-pressed={isSaved(selectedApartment)} className={heartClass(selectedApartment, "save-toggle")}
                onClick={() => toggleSave(selectedApartment)} type="button"
              >
                <Icon name="heart" size={17} /> {isSaved(selectedApartment) ? "Saved" : "Save"}
              </button>
            </div>
            {selectedApartment.originalTitle && selectedApartment.originalTitle.toLowerCase() !== selectedApartment.title.toLowerCase() && (
              <p>Original German title: “{selectedApartment.originalTitle}”</p>
            )}
          </header>
          <section className={selectedApartment.images.length ? "listing-details with-photos" : "listing-details"}>
            {selectedApartment.images.length > 0 && (
              <div className="gallery">
                <a href={selectedApartment.images[photoIndex]?.full} rel="noreferrer" target="_blank">
                  <img alt={`Photo ${photoIndex + 1} of ${selectedApartment.title}`} className="gallery-main" referrerPolicy="no-referrer" src={selectedApartment.images[photoIndex]?.thumb} />
                </a>
                {selectedApartment.images.length > 1 && (
                  <div className="gallery-strip">
                    {selectedApartment.images.map((image, index) => (
                      <button className={index === photoIndex ? "active" : ""} key={image.thumb} onClick={() => setPhotoIndex(index)} type="button">
                        <img alt="" loading="lazy" referrerPolicy="no-referrer" src={image.thumb} />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            <div className="detail-facts">
              <span className="step-code">LISTING DETAILS</span>
              <dl>
                <div><dt>Area</dt><dd>{selectedApartment.area}</dd></div>
                <div><dt>Rent</dt><dd>{selectedApartment.rent} / month{selectedApartment.rentNet && selectedApartment.rentCharges ? ` (${formatChf(selectedApartment.rentNet)} + ${formatChf(selectedApartment.rentCharges)} charges)` : ""}</dd></div>
                <div><dt>Type</dt><dd>{KIND_DESCRIPTIONS[selectedApartment.kind] ?? selectedApartment.kind}</dd></div>
                {selectedApartment.rooms && selectedApartment.kind !== "Room" ? <div><dt>Rooms</dt><dd>{selectedApartment.rooms}</dd></div> : null}
                {selectedApartment.surface ? <div><dt>Size</dt><dd>{selectedApartment.surface} m²</dd></div> : null}
                {selectedApartment.floor !== null && selectedApartment.floor !== undefined ? <div><dt>Floor</dt><dd>{selectedApartment.floor === 0 ? "Ground floor" : selectedApartment.floor}</dd></div> : null}
                {selectedApartment.movingDate || selectedApartment.availableText ? (
                  <div><dt>Available</dt><dd>{selectedApartment.movingDate ? `From ${formatDate(selectedApartment.movingDate)}` : selectedApartment.availableText}</dd></div>
                ) : null}
                <div><dt>Rental</dt><dd>{selectedApartment.isTemporary ? "Temporary / sublet" : "Long-term"}</dd></div>
                {selectedApartment.yearBuilt ? <div><dt>Built</dt><dd>{selectedApartment.yearBuilt}</dd></div> : null}
                <div>
                  <dt>Website</dt>
                  <dd>
                    {selectedApartment.url ? (
                      <a className="detail-link" href={selectedApartment.url} rel="noreferrer" target="_blank">
                        View the original listing on {selectedApartment.sourceName === "Pasted listing" ? "the website" : selectedApartment.sourceName} ↗
                      </a>
                    ) : selectedApartment.sourceName}
                  </dd>
                </div>
                {selectedApartment.published ? <div><dt>Listed</dt><dd>{formatDate(selectedApartment.published)}</dd></div> : null}
              </dl>
              {selectedApartment.features.length > 0 && (
                <div className="mini-tags detail-features">{selectedApartment.features.map((feature) => <span key={feature}>{feature}</span>)}</div>
              )}
            </div>
          </section>

          {(selectedApartment.notes?.length ?? 0) > 0 && (
            <section className="listing-notes">
              <span className="step-code">COMPARED WITH YOUR PREFERENCES</span>
              <div className="notes-grid">
                {selectedApartment.notes?.map((note) => (
                  <div key={note.title}>
                    {note.tone === "warn" ? <span className="fit-icon warn">!</span> : <span className="fit-icon yes"><Icon name={note.icon} size={15} /></span>}
                    <p><strong>{note.title}</strong><small>{note.detail}</small></p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {(selectedApartment.wishes?.length ?? 0) > 0 && (
            <section className="listing-notes">
              <span className="step-code">WHO THEY’RE LOOKING FOR</span>
              <div className="notes-grid">
                {selectedApartment.wishes?.map((wish) => (
                  <div key={`${wish.topic}-${wish.title}`}>
                    {wish.fit === "yes" ? <span className="fit-icon yes"><Icon name="check" size={15} /></span>
                      : wish.fit === "no" ? <span className="fit-icon warn">!</span>
                      : <span className="fit-icon unknown">?</span>}
                    <p>
                      <strong>{wish.title}</strong>
                      <small>{wish.strength === "required" ? "Required" : "Preferred"} · “{wish.quote}”</small>
                      {wish.fit === "unknown" && <small>Not in your profile, so it isn’t part of your reply chance.</small>}
                    </p>
                  </div>
                ))}
              </div>
              <p className="fit-empty">Read from the listing text by Flatty’s local AI. Check the original listing if a point matters to you.</p>
            </section>
          )}

          <section className="result-layout">
            <div className={`score-panel reply-${selectedApartment.replyLevel}`}>
              <span className="step-code">WILL THE LANDLORD REPLY?</span>
              <h1>{selectedApartment.replyLabel}.</h1>
              <div className="score-box"><strong>{Math.round(selectedApartment.replyScore * 100)}</strong><span>%</span></div>
              <p>Flatty’s estimate of the chance that this landlord replies to you. From 50% it counts as likely.</p>
            </div>
            <div className="fit-panel">
              <h2>What affects your reply chance</h2>
              {selectedApartment.reasons.length > 0 ? (
                <>
                  <p className="fit-empty">Each percentage is how much that point counts. Together they make 100%. + raises your chance, − lowers it.</p>
                  <div className="fit-list">
                    {selectedApartment.reasons.map((reason) => (
                      <div key={reason.title}>
                        {reason.tone === "warn" ? <span className="fit-icon warn">!</span> : <span className="fit-icon yes"><Icon name={reason.icon} size={15} /></span>}
                        <p><strong>{reason.title}</strong><small>{reason.detail}</small></p>
                        <span className={`share ${reason.tone}`}>{signedShare(reason)}</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="fit-empty">Nothing in this listing or your profile raises or lowers your reply chance.</p>
              )}
              <p className="fit-empty">{WEIGHTS_NOTE}</p>
            </div>
          </section>

          <section className={`risk-panel ${riskLevel(selectedApartment.risk).tone}`}>
            <div className="risk-score">
              <span>AI RISK SCORE</span>
              <strong>{selectedApartment.risk}<small>%</small></strong>
            </div>
            <div className="risk-explanation">
              <span className="risk-status">{riskLevel(selectedApartment.risk).label}</span>
              <h2>
                {selectedApartment.risk < 25
                  ? selectedApartment.riskFlags.length ? "Looks fine, with minor points to check." : "No major warning signals found."
                  : selectedApartment.risk < 55
                    ? "A few details need a closer look."
                    : "This listing shows several warning signals."}
              </h2>
              <p>
                {selectedApartment.risk < 25
                  ? "The listing looks consistent, but always verify the landlord and never pay before viewing."
                  : selectedApartment.risk < 55
                    ? "Ask for more photos and the exact address, and visit before you send documents or money."
                    : "Proceed carefully. Do not transfer money or share sensitive documents until the listing and landlord are verified."}
              </p>
              <div className="risk-breakdown">
                {selectedApartment.riskFlags.length > 0 && (
                  <div>
                    <span className="breakdown-label">Raises the risk</span>
                    <ul className="risk-flags">{selectedApartment.riskFlags.map((flag) => <li key={flag}>{flag}</li>)}</ul>
                  </div>
                )}
                {(selectedApartment.riskPositives?.length ?? 0) > 0 && (
                  <div>
                    <span className="breakdown-label">Lowers the risk</span>
                    <ul className="risk-flags positive">{selectedApartment.riskPositives?.map((item) => <li key={item}>{item}</li>)}</ul>
                  </div>
                )}
              </div>
              {selectedApartment.riskText !== null && selectedApartment.riskText !== undefined && (
                <p className="risk-text-note">
                  {(selectedApartment.riskTextEvidence ?? 1) < 0.5
                    ? "AI text analysis: too little text to judge, so Flatty assumes the average risk for the text part."
                    : `AI text analysis: ${selectedApartment.riskText}% scam-like wording. The other points above are added on top.`}
                </p>
              )}
            </div>
            <div className="risk-meter" aria-label={`${selectedApartment.risk}% risk`}>
              <span style={{ width: `${selectedApartment.risk}%` }} />
            </div>
          </section>

          <section className="next-actions">
            <div><span className="step-code">NEXT STEP</span><h2>Use this listing</h2></div>
            <button className={generated === "summary" ? "action-card active" : "action-card"} disabled={listingGone} onClick={() => generate("summary")} type="button"><span><Icon name="search" size={20} /></span><p><strong>Make a summary</strong><small>Key details in one view</small></p><Icon name="arrow" size={18} /></button>
            <button className={generated === "email" ? "action-card active" : "action-card"} disabled={listingGone} onClick={() => generate("email")} type="button"><span><Icon name="mail" size={20} /></span><p><strong>Draft an email</strong><small>Personalized application</small></p><Icon name="arrow" size={18} /></button>
          </section>

          {generated && (
            <section className="generated-card">
              <div className="generated-head">
                <span className="step-code">{generated === "summary" ? "LISTING SUMMARY" : "EMAIL DRAFT"}</span>
                <div className="generated-tools">
                  {generated === "email" && (
                    <div aria-label="Language of the e-mail" className="language-switch" role="group">
                      {EMAIL_LANGUAGES.map(([language, label]) => (
                        <button aria-pressed={emailLanguage === language} className={emailLanguage === language ? "active" : ""} key={language} onClick={() => { setEmailLanguage(language); setCopied(false); }} type="button">
                          {label}
                        </button>
                      ))}
                    </div>
                  )}
                  <button className="copy-button" disabled={writing} onClick={copyGenerated} type="button">{copied ? "Copied" : "Copy"}</button>
                </div>
              </div>
              <p>{writing ? "Writing with the local AI model…" : shownText}</p>
              {generated === "email" && (
                <small className="email-hint">
                  {selectedApartment.language === "German"
                    ? "This listing is written in German, so send the German version. The English one shows you what it says."
                    : "Both versions say the same. Send the one in the landlord’s language."}
                  {!fullName.trim() && " Add your name under “Edit profile” to sign the e-mail."}
                </small>
              )}
              {!writing && shownEngine && (
                <small className="engine-note">{shownEngine === "template" ? "Written from a template (local AI model not running)" : `Written by Flatty’s own AI model (${shownEngine}), not a cloud service`}</small>
              )}
            </section>
          )}
        </main>
      )}
      {showPreferences && (
        <PreferencesDrawer
          initial={profile}
          onApply={applyPreferences}
          onClose={() => setShowPreferences(false)}
          onRestartSetup={() => { setShowPreferences(false); setStep(1); setScreen("onboarding"); }}
          account={account ? (
            <>
              <p className="drawer-hint">Signed in as <strong>{account.email}</strong>. Flatty remembers this profile and your saved homes.</p>
              <div className="drawer-account">
                <button onClick={signOut} type="button">Log out</button>
                <button onClick={removeAccount} type="button">Delete account</button>
              </div>
            </>
          ) : (
            <>
              <p className="drawer-hint">Create an account and Flatty remembers this profile and the homes you save.</p>
              <div className="drawer-account">
                <button onClick={() => { setShowPreferences(false); setAuthBox({ mode: "register" }); }} type="button">Create an account</button>
                <button onClick={() => { setShowPreferences(false); setAuthBox({ mode: "login" }); }} type="button">Log in</button>
              </div>
            </>
          )}
        />
      )}
      {authBox && screen !== "welcome" && (
        <div className="drawer-layer auth-layer">
          <div aria-hidden="true" className="drawer-backdrop" onClick={closeAuthBox} />
          <div aria-label={authBox.mode === "register" ? "Create your account" : "Log in"} aria-modal="true" className="auth-dialog" role="dialog">
            <AuthBox initialMode={authBox.mode} key={authBox.mode} onCancel={closeAuthBox} onDone={onLoggedIn} reason={authBox.reason} session={session} />
          </div>
        </div>
      )}
      {notice && !showPreferences && !authBox && <div className="toast" role="status">{notice}</div>}
    </div>
  );
}
