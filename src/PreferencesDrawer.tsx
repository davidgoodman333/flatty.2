import { useEffect, useRef, useState } from "react";
import type { Profile } from "./api";
import Icon from "./Icon";
import {
  APARTMENT_TYPES, AREAS, BUDGET_MAX, BUDGET_MIN, COUNTRIES, MAIN_LANGUAGES, MAP_AREAS, OTHER_LANGUAGES, PRIORITIES,
  SUPPORT_QUESTIONS,
} from "./options";

type Props = {
  initial: Profile;
  onApply: (profile: Profile) => void;
  onClose: () => void;
  onRestartSetup: () => void;
};

const toggled = (values: string[], value: string) =>
  values.includes(value) ? values.filter((item) => item !== value) : [...values, value];

// Edits a copy of the preferences; nothing changes until "Apply changes", so Cancel, Esc and
// clicking outside always leave the search as it was.
export default function PreferencesDrawer({ initial, onApply, onClose, onRestartSetup }: Props) {
  const [draft, setDraft] = useState<Profile>(initial);
  const [newArea, setNewArea] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const changed = JSON.stringify(draft) !== JSON.stringify(initial);
  const update = (patch: Partial<Profile>) => setDraft((current) => ({ ...current, ...patch }));

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden"; // keep the page behind the panel still
    heading.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && closeRef.current();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, []); // once per opening; the latest onClose is read from the ref

  const extraLanguages = draft.languages.filter((language) => !MAIN_LANGUAGES.includes(language));
  const extraAreas = draft.areas.filter((area) => !AREAS.includes(area) && !MAP_AREAS.includes(area));

  const addArea = () => {
    const area = newArea.trim();
    if (area && !draft.areas.includes(area)) update({ areas: [...draft.areas, area] });
    setNewArea("");
  };

  return (
    <div className="drawer-layer">
      <div aria-hidden="true" className="drawer-backdrop" onClick={onClose} />
      <aside aria-labelledby="preferences-title" aria-modal="true" className="drawer" role="dialog">
        <header className="drawer-head">
          <div>
            <span className="step-code">YOUR SEARCH</span>
            <h2 id="preferences-title" ref={heading} tabIndex={-1}>Edit preferences</h2>
          </div>
          <button aria-label="Close without saving" className="drawer-close" onClick={onClose} type="button">
            <Icon name="close" size={20} />
          </button>
        </header>

        <div className="drawer-body">
          <section className="drawer-section">
            <h3>Budget</h3>
            <div className="label-row">
              <label htmlFor="drawer-budget">Maximum monthly rent</label>
              <strong>CHF {draft.budget.toLocaleString("de-CH")}</strong>
            </div>
            <input
              className="range-input" id="drawer-budget" max={BUDGET_MAX} min={BUDGET_MIN} step="50" type="range"
              value={draft.budget} onChange={(event) => update({ budget: Number(event.target.value) })}
            />
          </section>

          <section className="drawer-section">
            <h3>Where</h3>
            <div className="chips">
              {[...AREAS, ...MAP_AREAS, ...extraAreas].map((area) => (
                <button className={draft.areas.includes(area) ? "chip active" : "chip"} key={area} onClick={() => update({ areas: toggled(draft.areas, area) })} type="button">
                  {draft.areas.includes(area) && <Icon name="check" size={14} />}{area}
                </button>
              ))}
            </div>
            <div className="text-input drawer-input">
              <Icon name="map" size={17} />
              <input
                aria-label="Add a town or neighbourhood" onChange={(event) => setNewArea(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && addArea()} placeholder="Add a town or neighbourhood" value={newArea}
              />
              <button disabled={!newArea.trim()} onClick={addArea} type="button">Add</button>
            </div>
            <label className="drawer-label" htmlFor="drawer-destination">Work or university</label>
            <div className="text-input drawer-input">
              <Icon name="work" size={17} />
              <input id="drawer-destination" onChange={(event) => update({ destination: event.target.value })} placeholder="Enter a destination" value={draft.destination} />
            </div>
          </section>

          <section className="drawer-section">
            <h3>Type of home</h3>
            <div className="chips">
              {APARTMENT_TYPES.map(([type, note]) => (
                <button className={draft.apartmentTypes.includes(type) ? "chip active" : "chip"} key={type} onClick={() => update({ apartmentTypes: toggled(draft.apartmentTypes, type) })} title={note} type="button">
                  {draft.apartmentTypes.includes(type) && <Icon name="check" size={14} />}{type}
                </button>
              ))}
            </div>
          </section>

          <section className="drawer-section">
            <h3>Nearby</h3>
            <div className="chips">
              {PRIORITIES.map(([name, icon, note]) => (
                <button className={draft.priorities.includes(name) ? "chip active" : "chip"} key={name} onClick={() => update({ priorities: toggled(draft.priorities, name) })} title={note} type="button">
                  <Icon name={draft.priorities.includes(name) ? "check" : icon} size={14} />{name}
                </button>
              ))}
            </div>
          </section>

          <section className="drawer-section">
            <h3>Languages</h3>
            <div className="chips">
              {[...MAIN_LANGUAGES, ...extraLanguages].map((language) => (
                <button className={draft.languages.includes(language) ? "chip active" : "chip"} key={language} onClick={() => update({ languages: toggled(draft.languages, language) })} type="button">
                  {draft.languages.includes(language) && <Icon name="check" size={14} />}{language}
                </button>
              ))}
            </div>
            <select
              aria-label="Add another language" className="option-select" value=""
              onChange={(event) => event.target.value && update({ languages: [...draft.languages, event.target.value] })}
            >
              <option value="">Add another language…</option>
              {OTHER_LANGUAGES.filter((language) => !draft.languages.includes(language)).map((language) => <option key={language}>{language}</option>)}
            </select>
          </section>

          <section className="drawer-section">
            <h3>About you</h3>
            <label className="drawer-label" htmlFor="drawer-country">Country</label>
            <select className="option-select" id="drawer-country" onChange={(event) => update({ country: event.target.value })} value={draft.country}>
              {COUNTRIES.map((country) => <option key={country}>{country}</option>)}
            </select>
            <p className="drawer-hint">These answers help Flatty estimate your reply chances and write your application.</p>
            {SUPPORT_QUESTIONS.map(([key, label]) => (
              <div className="drawer-question" key={key}>
                <span>{label}</span>
                <div className="binary-row" role="group" aria-label={label}>
                  {(["yes", "no"] as const).map((answer) => (
                    <button aria-pressed={draft[key] === answer} className={draft[key] === answer ? "binary-choice active" : "binary-choice"} key={answer} onClick={() => update({ [key]: answer })} type="button">
                      {answer === "yes" ? "Yes" : "No"}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </section>

          <button className="drawer-restart" onClick={onRestartSetup} type="button">Go through the full setup again instead</button>
        </div>

        <footer className="drawer-foot">
          <span className="drawer-status">{changed ? "Unsaved changes" : "No changes yet"}</span>
          <button className="back-button" onClick={onClose} type="button">Cancel</button>
          <button className="primary-button" disabled={!changed} onClick={() => onApply(draft)} type="button">
            Apply changes <Icon name="arrow" size={17} />
          </button>
        </footer>
      </aside>
    </div>
  );
}
