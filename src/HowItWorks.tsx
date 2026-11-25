import { useEffect, useRef, useState } from "react";
import Icon from "./Icon";

type Props = {
  /** "Start matching" for newcomers, "Back to your search" once a search exists. */
  ctaLabel: string;
  onStart: () => void;
};

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

type RevealProps = {
  as?: "div" | "article" | "header" | "aside";
  className?: string;
  /** Milliseconds to wait, so neighbours appear one after the other. */
  delay?: number;
  children: React.ReactNode | ((shown: boolean) => React.ReactNode);
};

// Fades and rises into place the first time it scrolls into view.
function Reveal({ as = "div", className = "", delay = 0, children }: RevealProps) {
  const Tag = as as "div";
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setShown(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      setShown(true);
      observer.disconnect();
    }, { threshold: 0.2 });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return (
    <Tag className={`${className} reveal${shown ? " in" : ""}`} ref={ref} style={{ "--delay": `${delay}ms` } as React.CSSProperties}>
      {typeof children === "function" ? children(shown) : children}
    </Tag>
  );
}

// Counts from 0 to `to` once `start` is true.
function CountUp({ to, start }: { to: number; start: boolean }) {
  const [value, setValue] = useState(() => (reducedMotion() ? to : 0));
  useEffect(() => {
    if (!start || reducedMotion()) return;
    const began = performance.now();
    let frame = requestAnimationFrame(function step(now) {
      const progress = Math.min(1, (now - began) / 1300);
      setValue(Math.round(to * (1 - (1 - progress) ** 3)));
      if (progress < 1) frame = requestAnimationFrame(step);
    });
    return () => cancelAnimationFrame(frame);
  }, [start, to]);
  return <>{value}</>;
}

// The little demos below replay what the real screens show.
const PROFILE_CHIPS = ["CHF 1,800", "Uni Bern", "Studio", "Public transport"];
const SOURCES = ["Flatfox", "Uni Bern housing board", "studentlodge"];
const RISKS = [
  { tone: "low", label: "Low risk", score: 8, why: "No warning signals found" },
  { tone: "medium", label: "Medium risk", score: 27, why: "Pushes contact off the platform" },
  { tone: "high", label: "High risk", score: 68, why: "Asks for a deposit before a viewing" },
];
const REPLIES = [
  { level: "likely", label: "Reply likely", score: 78, reasons: [["+", "Private landlord"], ["+", "Student-friendly"]] },
  { level: "unlikely", label: "Reply unlikely", score: 31, reasons: [["−", "Cheap for the area"], ["−", "Listing written in German"]] },
];
const SEARCHES = [
  { types: ["Studio"], from: 12, to: 52, rent: "CHF 700 – 1,400", found: 41 },
  { types: ["Room", "Studio"], from: 4, to: 40, rent: "CHF 500 – 1,150", found: 87 },
  { types: ["Apartment"], from: 30, to: 74, rent: "CHF 1,250 – 2,100", found: 29 },
];
const EMAILS = [
  { key: "English", label: "English", greeting: "Hello,", closing: "Kind regards" },
  { key: "German", label: "Deutsch", greeting: "Guten Tag", closing: "Freundliche Grüsse" },
];

export default function HowItWorks({ ctaLabel, onStart }: Props) {
  // One clock drives every demo. With "reduce motion" switched on, the demos stand still.
  const [still] = useState(reducedMotion);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (still) return;
    const timer = window.setInterval(() => setTick((value) => value + 1), 1500);
    return () => window.clearInterval(timer);
  }, [still]);

  const chipsOn = still ? PROFILE_CHIPS.length : tick % (PROFILE_CHIPS.length + 2);
  const sourcesDone = still ? SOURCES.length : tick % (SOURCES.length + 2);
  const risk = RISKS[still ? 1 : Math.floor(tick / 2) % RISKS.length];
  const reply = REPLIES[still ? 0 : Math.floor(tick / 3) % REPLIES.length];
  const search = SEARCHES[still ? 0 : Math.floor(tick / 2) % SEARCHES.length];
  const liked = still || tick % 4 >= 2;
  const email = EMAILS[still ? 0 : Math.floor(tick / 4) % EMAILS.length];

  return (
    <main className="about-page">
      <Reveal as="header" className="about-intro">
        <span className="step-code">HOW FLATTY WORKS</span>
        <h1>From your needs<br />to a reply.</h1>
        <p>
          Flatty collects student housing around Bern, checks every listing with its own AI models and shows you where a
          landlord is most likely to answer. No cloud AI service is involved.
        </p>
      </Reveal>

      <section className="process-tree" aria-label="How Flatty works, step by step">
        <Reveal className="tree-root">
          <span className="tree-icon local-ai" aria-hidden="true"><i /><i /><i /><i /></span>
          <div>
            <span className="tree-number">01</span>
            <h2>Tell Flatty what you need</h2>
            <p>Six short steps: budget, where you study, what matters nearby and your situation.</p>
          </div>
          <div className="tree-demo demo-chips" aria-hidden="true">
            {PROFILE_CHIPS.map((chip, index) => (
              <span className={index < chipsOn ? "demo-chip on" : "demo-chip"} key={chip}>
                {index < chipsOn && <Icon name="check" size={12} />}{chip}
              </span>
            ))}
          </div>
        </Reveal>

        <div className="shape-path" aria-hidden="true"><i /><i /><i /><i /><i /></div>

        <span className="tree-label">WHAT FLATTY DOES</span>
        <div className="tree-branches">
          <Reveal as="article" className="tree-card">
            <span className="tree-number">02</span>
            <span className="tree-card-icon"><Icon name="search" size={21} /></span>
            <h3>Collects listings every day</h3>
            <p>Only from websites whose terms allow it. Homes that go offline disappear from your results.</p>
            <ul className="tree-demo demo-sources" aria-hidden="true">
              {SOURCES.map((source, index) => (
                <li className={index < sourcesDone ? "on" : ""} key={source}>
                  <span className="pixel-check">{index < sourcesDone && <Icon name="check" size={11} />}</span>{source}
                </li>
              ))}
            </ul>
          </Reveal>
          <Reveal as="article" className="tree-card" delay={120}>
            <span className="tree-number">03</span>
            <span className="tree-card-icon">?</span>
            <h3>Checks the scam risk</h3>
            <p>A model gives every listing a risk score and says why. Flatty warns you. It never hides a home.</p>
            <div className={`tree-demo demo-risk ${risk.tone}`} aria-hidden="true">
              <div><span className="demo-status">{risk.label}</span><strong>{risk.score}%</strong></div>
              <div className="demo-meter"><span style={{ width: `${risk.score}%` }} /></div>
              <small key={risk.why}>{risk.why}</small>
            </div>
          </Reveal>
          <Reveal as="article" className="tree-card" delay={240}>
            <span className="tree-number">04</span>
            <span className="tree-card-icon"><Icon name="mail" size={21} /></span>
            <h3>Estimates your reply chance</h3>
            <p>Who is renting, what the listing says and your own situation show how likely an answer is.</p>
            <div className={`tree-demo demo-reply ${reply.level}`} aria-hidden="true" key={reply.level}>
              <div><span className="demo-status">{reply.label}</span><strong>{reply.score}%</strong></div>
              <ul>{reply.reasons.map(([sign, text]) => <li key={text}><b>{sign}</b>{text}</li>)}</ul>
            </div>
          </Reveal>
        </div>

        <div className="shape-path reverse" aria-hidden="true"><i /><i /><i /></div>

        <span className="tree-label">WHAT YOU DO</span>
        <div className="tree-branches">
          <Reveal as="article" className="tree-card">
            <span className="tree-number">05</span>
            <span className="tree-card-icon"><Icon name="map" size={21} /></span>
            <h3>Narrow it down</h3>
            <p>Filter by type, rent, dates and a radius on the map. Found a place elsewhere? Paste its link or text.</p>
            <div className="tree-demo demo-filter" aria-hidden="true">
              <div className="demo-chips">
                {["Room", "Studio", "Apartment"].map((type) => (
                  <span className={search.types.includes(type) ? "demo-chip on" : "demo-chip"} key={type}>{type}</span>
                ))}
              </div>
              <div className="demo-range" style={{ "--from": `${search.from}%`, "--to": `${search.to}%` } as React.CSSProperties}><i /><i /></div>
              <small><span>{search.rent}</span><span key={search.found}>{search.found} homes</span></small>
            </div>
          </Reveal>
          <Reveal as="article" className="tree-card" delay={120}>
            <span className="tree-number">06</span>
            <span className="tree-card-icon"><Icon name="heart" size={21} /></span>
            <h3>Save the ones you like</h3>
            <p>With an account, one tap keeps a home on your Saved list. Your profile is there when you come back.</p>
            <div className="tree-demo demo-save" aria-hidden="true">
              <span className="demo-photo"><i /><i /><i /><i /></span>
              <span className="demo-lines"><i /><i /></span>
              <span className={liked ? "save-button saved" : "save-button"}><Icon name="heart" size={16} /></span>
              <small>Saved <b key={String(liked)}>{liked ? 3 : 2}</b></small>
            </div>
          </Reveal>
          <Reveal as="article" className="tree-card" delay={240}>
            <span className="tree-number">07</span>
            <span className="tree-card-icon"><Icon name="mail" size={21} /></span>
            <h3>Write to the landlord</h3>
            <p>Flatty drafts your application e-mail in English and German, and a short summary of the listing.</p>
            <div className="tree-demo demo-email" aria-hidden="true">
              <div className="demo-switch">
                {EMAILS.map((item) => <span className={item.key === email.key ? "on" : ""} key={item.key}>{item.label}</span>)}
              </div>
              <div className="demo-letter" key={email.key}>
                <b>{email.greeting}</b><i /><i /><i /><b>{email.closing}</b>
              </div>
            </div>
          </Reveal>
        </div>

        <div className="shape-path reverse" aria-hidden="true"><i /><i /><i /></div>

        <Reveal className="tree-result">
          {(shown) => (
            <>
              <span className="tree-result-score"><CountUp start={shown} to={78} />%</span>
              <div>
                <span className="tree-number">08</span>
                <h2>Your best chances first</h2>
                <p>Results are sorted by how likely each landlord is to reply to you.</p>
              </div>
              <button onClick={onStart} type="button">
                {ctaLabel} <Icon name="arrow" size={18} />
              </button>
            </>
          )}
        </Reveal>
      </section>

      <aside className="local-note">
        <strong>WHERE YOUR DATA GOES</strong>
        <span>
          The models run on Flatty’s own computer, not at a cloud AI provider. With an account, your e-mail address, profile and saved
          homes are stored there so Flatty can remember you. You can delete the account at any time under “Edit profile”.
        </span>
      </aside>
    </main>
  );
}
