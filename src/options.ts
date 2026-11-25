// Choices shared by the setup flow and the preferences panel, so both always offer the same options.
import type { IconName } from "./Icon";

export const MAIN_LANGUAGES = ["English", "German", "French", "Italian"];
export const OTHER_LANGUAGES = [
  "Albanian", "Arabic", "Bengali", "Bosnian", "Bulgarian", "Croatian", "Czech", "Danish", "Dutch", "Finnish", "Greek",
  "Hebrew", "Hindi", "Hungarian", "Indonesian", "Japanese", "Korean", "Mandarin", "Norwegian", "Persian", "Polish",
  "Portuguese", "Romanian", "Russian", "Serbian", "Slovak", "Spanish", "Swedish", "Tamil", "Thai", "Turkish",
  "Ukrainian", "Urdu", "Vietnamese",
];

export const AREAS = ["Länggasse", "Breitenrain", "Lorraine", "Mattenhof", "Monbijou", "Kirchenfeld", "Old Town", "Wankdorf", "Bümpliz", "Anywhere"];

// Where students study. `name` is stored in the profile; the back-end has the same list
// (backend/app/geo.py: CAMPUSES) for the commute estimate and the e-mails. Keep both in sync.
// Coordinates come from OpenStreetMap (street address of each building).
export type Campus = {
  name: string;
  short: string; // for "Centre on …" on the map
  group: string;
  school: string; // as written in an English e-mail: "I study at …"
  schoolDe: string; // as written in a German e-mail: "Ich studiere …"
  lat: number;
  lng: number;
};

const UNI = { school: "the University of Bern", schoolDe: "an der Universität Bern" };
const BFH = { school: "the Bern University of Applied Sciences (BFH)", schoolDe: "an der Berner Fachhochschule (BFH)" };
const HKB = { school: "the Bern Academy of the Arts (HKB)", schoolDe: "an der Hochschule der Künste Bern (HKB)" };
const GENERAL = "Not sure which campus?";
const UNI_GROUP = "University of Bern";
const BFH_GROUP = "BFH (Bern University of Applied Sciences)";
const OTHER_GROUP = "PHBern and other schools";

export const CAMPUSES: Campus[] = [
  { group: GENERAL, name: "University of Bern", short: "Uni Bern", ...UNI, lat: 46.9506, lng: 7.4385 },
  { group: GENERAL, name: "BFH (Bern University of Applied Sciences)", short: "BFH", ...BFH, lat: 46.9513, lng: 7.4352 },

  { group: UNI_GROUP, name: "Uni Bern: Main building (Hochschulstrasse 4)", short: "Uni Bern main building", ...UNI, lat: 46.9506, lng: 7.4385 },
  { group: UNI_GROUP, name: "Uni Bern: UniS (Schanzeneckstrasse 1)", short: "UniS", ...UNI, lat: 46.9502, lng: 7.436 },
  { group: UNI_GROUP, name: "Uni Bern: ExWi, Exact Sciences (Sidlerstrasse 5)", short: "ExWi", ...UNI, lat: 46.9511, lng: 7.4389 },
  { group: UNI_GROUP, name: "Uni Bern: Unitobler (Lerchenweg 36)", short: "Unitobler", ...UNI, lat: 46.9538, lng: 7.4302 },
  { group: UNI_GROUP, name: "Uni Bern: vonRoll (Fabrikstrasse 8)", short: "vonRoll", ...UNI, lat: 46.9533, lng: 7.4232 },
  { group: UNI_GROUP, name: "Uni Bern: Uni Mittelstrasse (Mittelstrasse 43)", short: "Uni Mittelstrasse", ...UNI, lat: 46.9558, lng: 7.4356 },
  { group: UNI_GROUP, name: "Uni Bern: Uni Engehalde (Engehaldenstrasse 8)", short: "Uni Engehalde", ...UNI, lat: 46.9538, lng: 7.4396 },
  { group: UNI_GROUP, name: "Uni Bern: Bühlplatz, Chemistry and Life Sciences (Baltzerstrasse 4)", short: "Bühlplatz", ...UNI, lat: 46.9518, lng: 7.4285 },
  { group: UNI_GROUP, name: "Uni Bern: Insel campus, Medicine (Freiburgstrasse 18)", short: "Insel campus", ...UNI, lat: 46.9474, lng: 7.4258 },
  { group: UNI_GROUP, name: "Uni Bern: Tierspital, Vetsuisse (Länggassstrasse 120)", short: "Tierspital", ...UNI, lat: 46.9564, lng: 7.4268 },
  { group: UNI_GROUP, name: "Uni Bern: Sport Science, ZSSw (Bremgartenstrasse 145)", short: "ZSSw", ...UNI, lat: 46.9623, lng: 7.4318 },

  { group: BFH_GROUP, name: "BFH: Business (Brückenstrasse 73)", short: "BFH Business", ...BFH, lat: 46.9424, lng: 7.4406 },
  { group: BFH_GROUP, name: "BFH: Health (Murtenstrasse 10)", short: "BFH Health", ...BFH, lat: 46.9487, lng: 7.4273 },
  { group: BFH_GROUP, name: "BFH: Health (Schwarztorstrasse 48)", short: "BFH Health", ...BFH, lat: 46.9446, lng: 7.4324 },
  { group: BFH_GROUP, name: "BFH: Social Work (Hallerstrasse 10)", short: "BFH Social Work", ...BFH, lat: 46.9526, lng: 7.4353 },
  { group: BFH_GROUP, name: "BFH: Engineering and Computer Science, Bern (Wankdorffeldstrasse 102)", short: "BFH Wankdorf", ...BFH, lat: 46.9648, lng: 7.4562 },
  { group: BFH_GROUP, name: "BFH: HKB Arts, Bümpliz (Fellerstrasse 11)", short: "HKB Bümpliz", ...HKB, lat: 46.947, lng: 7.3915 },
  { group: BFH_GROUP, name: "BFH: HKB Music (Papiermühlestrasse 13a)", short: "HKB Music", ...HKB, lat: 46.9554, lng: 7.4605 },
  { group: BFH_GROUP, name: "BFH: HKB Music and Theatre (Ostermundigenstrasse 103)", short: "HKB Ostermundigenstrasse", ...HKB, lat: 46.9566, lng: 7.4726 },
  { group: BFH_GROUP, name: "BFH: HAFL Agriculture, Forest and Food Sciences (Zollikofen)", short: "BFH-HAFL Zollikofen", ...BFH, lat: 46.9918, lng: 7.468 },
  { group: BFH_GROUP, name: "BFH: Engineering and Computer Science, Biel/Bienne (Quellgasse 21)", short: "BFH Biel", ...BFH, lat: 47.1422, lng: 7.2448 },
  { group: BFH_GROUP, name: "BFH: Architecture, Wood and Civil Engineering, Biel/Bienne (Solothurnstrasse 102)", short: "BFH Biel", ...BFH, lat: 47.1586, lng: 7.2769 },
  { group: BFH_GROUP, name: "BFH: Burgdorf (Pestalozzistrasse 20)", short: "BFH Burgdorf", ...BFH, lat: 47.0574, lng: 7.6211 },

  { group: OTHER_GROUP, name: "PHBern, University of Teacher Education (Fabrikstrasse 8)", short: "PHBern", school: "PHBern, the University of Teacher Education", schoolDe: "an der PHBern", lat: 46.9533, lng: 7.4232 },
  { group: OTHER_GROUP, name: "gibb Berufsfachschule Bern (Lorrainestrasse 1)", short: "gibb", school: "gibb Berufsfachschule Bern", schoolDe: "an der gibb Berufsfachschule Bern", lat: 46.9548, lng: 7.4449 },
  { group: OTHER_GROUP, name: "BFF Bern (Monbijoustrasse 21)", short: "BFF Bern", school: "BFF Bern", schoolDe: "an der BFF Bern", lat: 46.9445, lng: 7.4365 },
  { group: OTHER_GROUP, name: "WKS KV Bildung (Effingerstrasse 70)", short: "WKS KV Bildung", school: "WKS KV Bildung in Bern", schoolDe: "an der WKS KV Bildung", lat: 46.9459, lng: 7.4283 },
  { group: OTHER_GROUP, name: "Bildungszentrum Pflege (Freiburgstrasse 133)", short: "BZ Pflege", school: "the Berner Bildungszentrum Pflege", schoolDe: "am Berner Bildungszentrum Pflege", lat: 46.9431, lng: 7.4088 },
  { group: OTHER_GROUP, name: "Feusi Bildungszentrum (Max-Daetwyler-Platz 1)", short: "Feusi", school: "Feusi Bildungszentrum in Bern", schoolDe: "am Feusi Bildungszentrum", lat: 46.9664, lng: 7.4655 },
];
export const CAMPUS_GROUPS = [GENERAL, UNI_GROUP, BFH_GROUP, OTHER_GROUP];
export const DEFAULT_CAMPUS = CAMPUSES[0];
export const findCampus = (name: string) => CAMPUSES.find((campus) => campus.name === name) ?? DEFAULT_CAMPUS;

export const PRIORITIES: [string, IconName, string][] = [
  ["Public transport", "train", "Within 10 min"],
  ["Grocery stores", "shop", "Within 10 min"],
  ["Short commute", "work", "To your campus"],
  ["Quiet area", "home", "Low street noise"],
  ["Green space", "map", "Park within 10 min"],
  ["Cafés & study", "shop", "Places to work nearby"],
];

// Switzerland first, then every country in alphabetical order.
export const COUNTRIES = [
  "Switzerland",
  "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Antigua and Barbuda", "Argentina", "Armenia", "Australia",
  "Austria", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin",
  "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria", "Burkina Faso", "Burundi",
  "Cambodia", "Cameroon", "Canada", "Cape Verde", "Central African Republic", "Chad", "Chile", "China", "Colombia",
  "Comoros", "Congo (Brazzaville)", "Congo (Kinshasa)", "Costa Rica", "Côte d’Ivoire", "Croatia", "Cuba", "Cyprus",
  "Czechia", "Denmark", "Djibouti", "Dominica", "Dominican Republic", "Ecuador", "Egypt", "El Salvador",
  "Equatorial Guinea", "Eritrea", "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland", "France", "Gabon", "Gambia",
  "Georgia", "Germany", "Ghana", "Greece", "Grenada", "Guatemala", "Guinea", "Guinea-Bissau", "Guyana", "Haiti",
  "Honduras", "Hong Kong", "Hungary", "Iceland", "India", "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy",
  "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya", "Kiribati", "Kosovo", "Kuwait", "Kyrgyzstan", "Laos", "Latvia",
  "Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Madagascar", "Malawi",
  "Malaysia", "Maldives", "Mali", "Malta", "Marshall Islands", "Mauritania", "Mauritius", "Mexico", "Micronesia",
  "Moldova", "Monaco", "Mongolia", "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia", "Nauru", "Nepal",
  "Netherlands", "New Zealand", "Nicaragua", "Niger", "Nigeria", "North Korea", "North Macedonia", "Norway", "Oman",
  "Pakistan", "Palau", "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland",
  "Portugal", "Qatar", "Romania", "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia",
  "Saint Vincent and the Grenadines", "Samoa", "San Marino", "São Tomé and Príncipe", "Saudi Arabia", "Senegal",
  "Serbia", "Seychelles", "Sierra Leone", "Singapore", "Slovakia", "Slovenia", "Solomon Islands", "Somalia",
  "South Africa", "South Korea", "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Sweden", "Syria", "Taiwan",
  "Tajikistan", "Tanzania", "Thailand", "Timor-Leste", "Togo", "Tonga", "Trinidad and Tobago", "Tunisia", "Turkey",
  "Turkmenistan", "Tuvalu", "Uganda", "Ukraine", "United Arab Emirates", "United Kingdom", "United States", "Uruguay",
  "Uzbekistan", "Vanuatu", "Vatican City", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe",
  "Other",
];

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
