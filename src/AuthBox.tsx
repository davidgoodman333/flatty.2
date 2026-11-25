import { useState } from "react";
import { ApiError, logIn, register, type Account, type Session } from "./api";
import Icon from "./Icon";

export type AuthMode = "login" | "register";

type Props = {
  session: Session;
  initialMode: AuthMode;
  /** Why the box opened, for example "Log in to save this home." */
  reason?: string;
  onCancel: () => void;
  onDone: (account: Account) => void;
};

// Log-in and sign-up in one box. The password never leaves this form except to the Flatty back-end.
export default function AuthBox({ session, initialMode, reason, onCancel, onDone }: Props) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const creating = mode === "register";

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      onDone(creating ? await register(email, password, inviteCode) : await logIn(email, password));
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : "Flatty’s server can’t be reached right now. Please try again.");
      setBusy(false);
    }
  };

  const switchMode = () => {
    setMode(creating ? "login" : "register");
    setError("");
  };

  return (
    <form className="login-box" onSubmit={submit}>
      <div className="login-heading">
        <strong>{creating ? "Create your account" : "Welcome back"}</strong>
        <button onClick={onCancel} type="button">Cancel</button>
      </div>
      {reason && <p className="login-note">{reason}</p>}
      {creating && (
        <p className="login-note">
          {session.private
            ? "Flatty is in a private test. You need an invitation to create an account."
            : "With an account Flatty remembers your profile and the homes you save."}
        </p>
      )}
      {!session.available && (
        <p className="login-error" role="alert">Accounts need the Flatty back-end, which isn’t running here. You can still try the demo.</p>
      )}
      <label>
        <span>Email</span>
        <input autoComplete="email" maxLength={254} onChange={(event) => setEmail(event.target.value)} placeholder="you@email.com" required type="email" value={email} />
      </label>
      <label>
        <span>Password</span>
        <input
          autoComplete={creating ? "new-password" : "current-password"} maxLength={200} minLength={creating ? 8 : undefined}
          onChange={(event) => setPassword(event.target.value)} placeholder={creating ? "At least 8 characters" : "••••••••"} required type="password" value={password}
        />
      </label>
      {creating && session.inviteRequired && (
        <label>
          <span>Invite code</span>
          <input autoComplete="off" maxLength={200} onChange={(event) => setInviteCode(event.target.value)} placeholder="From your invitation" required value={inviteCode} />
        </label>
      )}
      {error && <p className="login-error" role="alert">{error}</p>}
      <button className="login-submit" disabled={busy || !session.available} type="submit">
        {busy ? "One moment…" : creating ? "Create account" : "Log in"} <Icon name="arrow" size={17} />
      </button>
      <p className="login-switch">
        {creating ? "Already have an account?" : "New to Flatty?"}{" "}
        <button onClick={switchMode} type="button">{creating ? "Log in" : "Create an account"}</button>
      </p>
    </form>
  );
}
