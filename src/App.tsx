import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError, ApiUnavailable, checkLink, checkListingOnline, demoApartments, emptyFilters, fetchSources, generateText, matchListings,
  PAGE_SIZE, type Apartment, type Filters, type ListingStatus, type Profile, type Reason, type SortKey, type SourceInfo,
} from "./api";
import Icon from "./Icon";
import { APARTMENT_TYPES, AREAS, BUDGET_MAX, BUDGET_MIN, COUNTRIES, MAIN_LANGUAGES, OTHER_LANGUAGES, PRIORITIES } from "./options";
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
const MAIN_FEATURE_COUNT = 3; // Furnished, balcony and pets are shown first; the rest behind "Show more"
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
// Filters inside the "More filters" panel (type, price and must-haves are always visible).
const countActiveFilters = (filters: Filters) =>
  [filters.roomsMin, filters.surfaceMin, filters.maxRisk, filters.availableBy].filter((value) => value !== null).length
  + (filters.rental !== "any" ? 1 : 0) + (filters.withPhotos ? 1 : 0) + (filters.sources.length ? 1 : 0);
// Type and maximum price are preferences, so "Reset filters" leaves them alone.
const hasAnyFilter = (filters: Filters) =>
  countActiveFilters(filters) > 0 || filters.priceMin !== null || filters.features.length > 0 || filters.areaLat !== null;

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
  const [showLogin, setShowLogin] = useState(false);
  const [step, setStep] = useState(1);
  const [languages, setLanguages] = useState(["English"]);
  const [showOtherLanguage, setShowOtherLanguage] = useState(false);
  const [budget, setBudget] = useState(1800);
  const [areas, setAreas] = useState(["Länggasse"]);
  const [showOtherArea, setShowOtherArea] = useState(false);
  const [otherArea, setOtherArea] = useState("");
  const [showMap, setShowMap] = useState(false);
  const [destination, setDestination] = useState("University of Bern");
  const [priorities, setPriorities] = useState(["Public transport", "Grocery stores"]);
  const [country, setCountry] = useState("Switzerland");
  const [hasGuarantor, setHasGuarantor] = useState<"yes" | "no" | "">("");
  const [hasViewingPerson, setHasViewingPerson] = useState<"yes" | "no" | "">("");
  const [hasSwissNumber, setHasSwissNumber] = useState<"yes" | "no" | "">("");
  const [hasSwissBank, setHasSwissBank] = useState<"yes" | "no" | "">("");
  const [hasResidencePermit, setHasResidencePermit] = useState<"yes" | "no" | "">("");
  const [apartmentTypes, setApartmentTypes] = useState(["Studio"]);
  const [activeTab, setActiveTab] = useState<"search" | "link">("search");
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
  const [showFilters, setShowFilters] = useState(false);
  const [showAllFeatures, setShowAllFeatures] = useState(false);
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
  const generateRequest = useRef(0);

  const progress = `${step * (100 / 6)}%`;
  const preferenceText = useMemo(() => `${areas.join(", ")} · up to CHF ${budget.toLocaleString("de-CH")}`, [areas, budget]);
  const profile: Profile = {
    languages, budget, areas, destination, priorities, country, hasGuarantor, hasViewingPerson,
    hasSwissNumber, hasSwissBank, hasResidencePermit, apartmentTypes,
  };

  type YesNo = "yes" | "no" | "";
  const applyPreferences = (next: Profile) => {
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
      if (request === listingRequest.current) setListingError(error instanceof Error ? error.message : "Couldn’t load listings.");
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

  const finishOnboarding = () => {
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

  const fallbackText = (kind: "summary" | "email") => {
    if (kind === "summary") {
      return `${selectedApartment.title} in ${selectedApartment.area}. ${selectedApartment.meta} for ${selectedApartment.rent} per month. ${[...(selectedApartment.notes ?? []), ...selectedApartment.reasons].map((reason) => reason.title).join(", ")}.`;
    }
    return [
      "Hello,",
      "",
      `I’m interested in the ${selectedApartment.title.toLowerCase()} in ${selectedApartment.area}. I’m from ${country} and currently study or work at ${destination}. The location would be a great fit for my commute and my preference for ${naturalList(priorities.map((item) => item.toLowerCase()))}.`,
      "",
      `I’m looking for ${naturalList(apartmentTypes.map((item) => item.toLowerCase()))} and I speak ${naturalList(languages)}.`
        + (hasGuarantor === "yes" ? " I have a guarantor who lives in Switzerland." : "")
        + (hasViewingPerson === "yes" ? " I also have someone who can attend a viewing on my behalf." : "")
        + " I would be happy to provide any required documents.",
      "",
      "Kind regards",
    ].join("\n");
  };

  const generate = async (kind: "summary" | "email") => {
    const request = ++generateRequest.current;
    setGenerated(kind);
    setGenerating(true);
    setCopied(false);
    let text: string, engine: string;
    try {
      ({ text, engine } = await generateText(kind, selectedApartment, profile));
    } catch (error) {
      if (error instanceof ApiError && error.code === "listing_inactive") {
        setListingStatus({ available: false, message: error.message });
        setGenerated(null);
        setGenerating(false);
        return;
      }
      [text, engine] = [fallbackText(kind), "template"];
    }
    if (request !== generateRequest.current) return; // a newer request replaced this one
    setGeneratedText(text);
    setGeneratedEngine(engine);
    setGenerating(false);
  };

  const copyGenerated = async () => {
    await navigator.clipboard.writeText(generatedText);
    setCopied(true);
  };

  return (
    <div className="app-shell">
      {screen !== "welcome" && (
        <header className="topbar">
          <button className="brand" onClick={() => { setScreen("welcome"); setShowLogin(false); }} type="button">
            <span className="brand-mark"><Icon name="home" size={16} /></span>
            <span>Flatty</span>
          </button>
          {screen === "browse" && <span className="header-pref">{preferenceText}</span>}
          {(screen === "browse" || screen === "result") && (
            <button aria-haspopup="dialog" className="edit-button" onClick={() => setShowPreferences(true)} type="button">
              Edit profile
            </button>
          )}
          {screen === "about" && (
            <>
              <span className="header-pref">How Flatty works</span>
              <button className="edit-button" onClick={() => { setStep(1); setScreen("onboarding"); }} type="button">
                Start a search
              </button>
            </>
          )}
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

            {!showLogin ? (
              <div className="welcome-actions">
                <button
                  className="welcome-primary"
                  onClick={() => { setStep(1); setScreen("onboarding"); }}
                  type="button"
                >
                  Start a new search <Icon name="arrow" size={19} />
                </button>
                <button className="login-trigger" onClick={() => setShowLogin(true)} type="button">
                  Log in
                </button>
                <button className="info-trigger" onClick={() => setScreen("about")} type="button">
                  How it works
                </button>
              </div>
            ) : (
              <form
                className="login-box"
                onSubmit={(event) => {
                  event.preventDefault();
                  setScreen("browse");
                }}
              >
                <div className="login-heading">
                  <strong>Welcome back</strong>
                  <button onClick={() => setShowLogin(false)} type="button">Cancel</button>
                </div>
                <label>
                  <span>Email</span>
                  <input type="email" placeholder="you@email.com" required />
                </label>
                <label>
                  <span>Password</span>
                  <input type="password" placeholder="••••••••" required />
                </label>
                <button className="login-submit" type="submit">
                  Log in <Icon name="arrow" size={17} />
                </button>
              </form>
            )}
          </section>
        </main>
      )}

      {screen === "about" && (
        <main className="about-page">
          <header className="about-intro">
            <span className="step-code">HOW FLATTY WORKS</span>
            <h1>Your search stays<br />with you.</h1>
            <p>
              Flatty uses a locally trained AI model to check listings and find the homes that fit you best.
              Your personal data is not sent to someone else’s server.
            </p>
          </header>

          <section className="process-tree" aria-label="Flatty process">
            <div className="tree-root">
              <span className="tree-icon local-ai"><i /><i /><i /><i /></span>
              <div>
                <span className="tree-number">01</span>
                <h2>Local AI model</h2>
                <p>Runs locally. Your data stays private.</p>
              </div>
            </div>

            <div className="shape-path" aria-hidden="true"><i /><i /><i /><i /><i /></div>

            <div className="tree-branches">
              <article className="tree-card">
                <span className="tree-number">02</span>
                <span className="tree-card-icon">?</span>
                <h3>Risk prediction</h3>
                <p>The model gives every listing a risk score. Flatty warns you—it never silently removes a home.</p>
              </article>
              <article className="tree-card">
                <span className="tree-number">03</span>
                <span className="tree-card-icon"><Icon name="check" size={21} /></span>
                <h3>Your preferences</h3>
                <p>Your budget and filters decide which listings you see.</p>
              </article>
              <article className="tree-card">
                <span className="tree-number">04</span>
                <span className="tree-card-icon"><Icon name="link" size={21} /></span>
                <h3>Any listing</h3>
                <p>Found a place yourself? Paste the link and Flatty checks the page.</p>
              </article>
            </div>

            <div className="shape-path reverse" aria-hidden="true"><i /><i /><i /></div>

            <div className="tree-result">
              <span className="tree-result-score">92%</span>
              <div>
                <span className="tree-number">05</span>
                <h2>Your best chances</h2>
                <p>See how likely each landlord is to reply to you.</p>
              </div>
              <button onClick={() => { setStep(1); setScreen("onboarding"); }} type="button">
                Start matching <Icon name="arrow" size={18} />
              </button>
            </div>
          </section>

          <aside className="local-note">
            <strong>LOCAL MEANS LOCAL</strong>
            <span>Your preferences stay on your device and are used only to improve your Flatty results.</span>
          </aside>
        </main>
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
                  {MAIN_LANGUAGES.map((language) => (
                    <button className={languages.includes(language) ? "chip active" : "chip"} key={language} onClick={() => toggle(language, languages, setLanguages)} type="button">
                      {languages.includes(language) && <Icon name="check" size={14} />}{language}
                    </button>
                  ))}
                  <button className={showOtherLanguage ? "chip active" : "chip"} onClick={() => setShowOtherLanguage((value) => !value)} type="button">
                    Other <Icon name="chevron" size={14} />
                  </button>
                </div>
                {showOtherLanguage && (
                  <select
                    aria-label="Choose another language"
                    autoFocus
                    className="option-select"
                    defaultValue=""
                    onChange={(event) => {
                      if (event.target.value && !languages.includes(event.target.value)) {
                        setLanguages([...languages, event.target.value]);
                      }
                      setShowOtherLanguage(false);
                    }}
                  >
                    <option value="" disabled>Choose another language</option>
                    {OTHER_LANGUAGES.map((language) => <option key={language}>{language}</option>)}
                  </select>
                )}
                {languages.some((language) => !MAIN_LANGUAGES.includes(language)) && (
                  <div className="selected-extras">
                    {languages.filter((language) => !MAIN_LANGUAGES.includes(language)).map((language) => (
                      <button key={language} onClick={() => setLanguages(languages.filter((item) => item !== language))} type="button">{language} ×</button>
                    ))}
                  </div>
                )}
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
              <p>Pick one or more areas.</p>
              <div className="question">
                <label>Preferred areas</label>
                <div className="chips">
                  {AREAS.map((area) => (
                    <button className={areas.includes(area) ? "chip active" : "chip"} key={area} onClick={() => toggle(area, areas, setAreas)} type="button">
                      {areas.includes(area) && <Icon name="check" size={14} />}{area}
                    </button>
                  ))}
                  <button className={showOtherArea ? "chip active" : "chip"} onClick={() => setShowOtherArea((value) => !value)} type="button">Other</button>
                  <button className={showMap ? "chip active" : "chip"} onClick={() => setShowMap((value) => !value)} type="button"><Icon name="map" size={15} /> Choose on map</button>
                </div>
                {showOtherArea && (
                  <div className="text-input extra-input">
                    <Icon name="map" size={18} />
                    <input value={otherArea} onChange={(event) => setOtherArea(event.target.value)} placeholder="Enter a town or neighborhood" />
                    <button onClick={() => { if (otherArea.trim() && !areas.includes(otherArea.trim())) setAreas([...areas, otherArea.trim()]); setOtherArea(""); }} type="button">Add</button>
                  </div>
                )}
                {showMap && (
                  <div className="mini-map">
                    <span className="map-road road-one" /><span className="map-road road-two" /><span className="map-river" />
                    <button className="map-pin pin-one" onClick={() => !areas.includes("Lorraine") && setAreas([...areas, "Lorraine"])} type="button"><Icon name="map" size={14} /> Lorraine</button>
                    <button className="map-pin pin-two" onClick={() => !areas.includes("Monbijou") && setAreas([...areas, "Monbijou"])} type="button"><Icon name="map" size={14} /> Monbijou</button>
                  </div>
                )}
              </div>
              <div className="question">
                <label htmlFor="destination">Work or university</label>
                <div className="text-input"><Icon name="work" size={18} /><input id="destination" value={destination} onChange={(event) => setDestination(event.target.value)} placeholder="Enter a destination" /></div>
                <span className="input-note">We’ll calculate the commute.</span>
              </div>
            </section>
          )}

          {step === 3 && (
            <section className="step-content">
              <h1>What matters nearby?</h1>
              <p>Select your everyday essentials.</p>
              <div className="priority-grid">
                {PRIORITIES.map(([name, icon, defaultNote]) => [name, icon, name === "Short commute" ? `To ${destination || "work"}` : defaultNote] as const).map(([name, icon, note]) => (
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
              <h1>Where are you from?</h1>
              <p>This helps personalize your application.</p>
              <div className="question">
                <label htmlFor="country">Country</label>
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
          </div>

          {activeTab === "search" ? (
            <section className="listings">
              <div className="filter-box">
                <div className="quick-filters">
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
                    <div className="filter-group">
                      <span>Must have</span>
                      <div className="chips">
                        {FEATURE_FILTERS.filter((feature, index) => showAllFeatures || index < MAIN_FEATURE_COUNT || filters.features.includes(feature)).map((feature) => (
                          <button aria-pressed={filters.features.includes(feature)} className={filters.features.includes(feature) ? "chip active" : "chip"} key={feature} onClick={() => updateFilters({ features: filters.features.includes(feature) ? filters.features.filter((item) => item !== feature) : [...filters.features, feature] })} type="button">
                            {filters.features.includes(feature) && <Icon name="check" size={14} />}{feature}
                          </button>
                        ))}
                        <button aria-expanded={showAllFeatures} className="show-more-chips" onClick={() => setShowAllFeatures((value) => !value)} type="button">
                          {showAllFeatures ? "Show less" : `Show ${FEATURE_FILTERS.slice(MAIN_FEATURE_COUNT).filter((feature) => !filters.features.includes(feature)).length} more`}
                        </button>
                      </div>
                    </div>
                  </div>
                  <MapRadius
                    area={filters.areaLat !== null && filters.areaLng !== null ? { lat: filters.areaLat, lng: filters.areaLng } : null}
                    colorFor={replyColor}
                    listings={apartments}
                    onAreaChange={(area, radiusKm) => updateFilters({ areaLat: area?.lat ?? null, areaLng: area?.lng ?? null, radiusKm })}
                    onSelect={checkApartment}
                    radiusKm={filters.radiusKm}
                  />
                </div>
                {showFilters && (
                  <div className="filter-panel">
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
                    <label className="filter-field">
                      <span>Move in by</span>
                      <input onChange={(event) => updateFilters({ availableBy: event.target.value || null })} type="date" value={filters.availableBy ?? ""} />
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
                    More filters{countActiveFilters(filters) > 0 && ` (${countActiveFilters(filters)})`} <span className={showFilters ? "chevron open" : "chevron"}><Icon name="chevron" size={14} /></span>
                  </button>
                  {hasAnyFilter(filters) && (
                    <button className="reset-filters" onClick={() => setFilters(emptyFilters)} type="button">Reset filters</button>
                  )}
                </div>
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
                {apartments.map((apartment, index) => (
                  <article className="apartment-card" key={apartment.id}>
                    <div className={`apartment-visual visual-${(index % 3) + 1}`}>
                      {apartment.images[0] ? (
                        <img alt="" className="apartment-photo" loading="lazy" referrerPolicy="no-referrer" src={apartment.images[0].thumb} />
                      ) : (
                        <div className="pixel-windows"><i /><i /><i /><i /></div>
                      )}
                      <span className={`reply-badge ${apartment.replyLevel}`}>Reply {apartment.replyLabel.toLowerCase()}</span>
                      <span className={`risk-badge ${riskLevel(apartment.risk).tone}`}>{apartment.risk}% risk</span>
                    </div>
                    <div className="apartment-info">
                      <span className="area-label"><Icon name="map" size={13} /> {apartment.area}<em>· {apartment.sourceName}</em></span>
                      <h2>{apartment.title}</h2>
                      <p>{apartment.meta}</p>
                      <div className="mini-tags">{apartment.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
                    </div>
                    <div className="apartment-action"><strong>{apartment.rent}<small>/month</small></strong><button onClick={() => checkApartment(apartment)} type="button">Check listing <Icon name="arrow" size={16} /></button></div>
                  </article>
                ))}
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
          <button className="back-link" onClick={() => setScreen("browse")} type="button"><Icon name="back" size={17} /> Back to results</button>
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
            <h1>{selectedApartment.title}</h1>
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
                <button disabled={generating} onClick={copyGenerated} type="button">{copied ? "Copied" : "Copy"}</button>
              </div>
              <p>{generating ? "Writing with the local AI model…" : generatedText}</p>
              {!generating && generatedEngine && (
                <small className="engine-note">{generatedEngine === "template" ? "Written from a template (local AI model not running)" : `Written on this device by ${generatedEngine}`}</small>
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
        />
      )}
      {notice && !showPreferences && <div className="toast" role="status">{notice}</div>}
    </div>
  );
}
