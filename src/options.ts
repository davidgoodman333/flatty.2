// Choices shared by the setup flow and the preferences panel, so both always offer the same options.
import type { IconName } from "./Icon";

export const MAIN_LANGUAGES = ["English", "German", "French", "Italian"];
export const OTHER_LANGUAGES = ["Arabic", "Dutch", "Hindi", "Japanese", "Korean", "Mandarin", "Polish", "Portuguese", "Russian", "Spanish", "Turkish", "Ukrainian"];

export const AREAS = ["Länggasse", "Breitenrain", "Mattenhof", "Old Town", "Anywhere"];
export const MAP_AREAS = ["Lorraine", "Monbijou"];

export const PRIORITIES: [string, IconName, string][] = [
  ["Public transport", "train", "Within 10 min"],
  ["Grocery stores", "shop", "Within 10 min"],
  ["Short commute", "work", "To your work or university"],
  ["Quiet area", "home", "Low street noise"],
  ["Green space", "map", "Park within 10 min"],
  ["Cafés & study", "shop", "Places to work nearby"],
];

export const COUNTRIES = ["Switzerland", "Germany", "France", "Italy", "Spain", "Portugal", "United Kingdom", "United States", "India", "China", "Ukraine", "Turkey", "Other"];

export const APARTMENT_TYPES: [string, string][] = [
  ["Shared apartment", "A room with flatmates"],
  ["Studio", "A compact place for one"],
  ["Proper flat", "Your own full apartment"],
  ["2-person flat", "Space for two people"],
  ["3-person flat", "Space for three people"],
];

export const SUPPORT_QUESTIONS: [key: "hasGuarantor" | "hasViewingPerson" | "hasSwissNumber" | "hasSwissBank" | "hasResidencePermit", label: string][] = [
  ["hasGuarantor", "Guarantor who lives in Switzerland"],
  ["hasViewingPerson", "Someone who can attend viewings for you"],
  ["hasSwissNumber", "Swiss phone number"],
  ["hasSwissBank", "Swiss bank account"],
  ["hasResidencePermit", "Residence permit"],
];

export const BUDGET_MIN = 400;
export const BUDGET_MAX = 3500;
