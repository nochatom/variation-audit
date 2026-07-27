// Maps backend auth errors (see backend app/errors.py's {"error":{"code",
// "message","fields"}} envelope) to friendly, user-facing copy. No call site
// should ever show a raw ApiError.message, a stack trace, or a bare
// "Failed" — this is the single place that decides what the user sees.
//
// Two flows deliberately do NOT reveal account existence, mirroring
// anti-enumeration choices already made server-side (see backend
// app/auth/router.py's docstrings on signup/login):
//   - Login's 401 covers "no such account", "wrong password", and
//     "account disabled" alike — the backend can't tell them apart on
//     purpose, so neither can this mapping.
//   - Signup always 202s even for an email that already has an account; if
//     the auto-login that follows then 401s, that means the account already
//     existed, but the message stays non-committal rather than declaring
//     "email already exists" (a differential message here would itself be
//     the enumeration oracle the backend was built to avoid).
import { ApiError } from "./api";

export type AuthErrorContext =
  | "login"
  | "signup"
  | "google"
  | "forgot-password"
  | "reset-password"
  | "invite-preview"
  | "invite-accept"
  | "invite-register";

const NETWORK_ERROR = "Network error. Please try again.";
const SERVER_ERROR = "Unexpected server error. Please try again.";

function fieldMessage(fields: ApiError["fields"]): string | null {
  if (!fields || fields.length === 0) return null;
  const field = fields[0].loc[fields[0].loc.length - 1];
  switch (field) {
    case "email":
      return "Please enter a valid email address.";
    case "password":
    case "new_password":
      return /at least/i.test(fields[0].message)
        ? "Password must be at least 8 characters."
        : "Please check your password and try again.";
    case "org_name":
      return "Please enter your organization name.";
    case "full_name":
      return "Please check the name you entered.";
    default:
      return "Please check your information and try again.";
  }
}

export function mapAuthError(err: unknown, context: AuthErrorContext): string {
  // fetch() itself threw (offline, DNS failure, CORS, timeout) — there was
  // never an HTTP response to read a message from.
  if (!(err instanceof ApiError)) return NETWORK_ERROR;

  if (err.status === 429 || err.code === "RATE_LIMITED") {
    return "Too many attempts. Please wait a moment and try again.";
  }
  if (err.status === 422 || err.code === "VALIDATION_ERROR") {
    return fieldMessage(err.fields) ?? "Please check your information and try again.";
  }
  if (err.status >= 500) {
    return SERVER_ERROR;
  }

  switch (context) {
    case "login":
      if (err.status === 401) return "Incorrect email or password.";
      break;

    case "signup":
      // The signup call itself only ever fails on validation/rate-limit
      // (handled above) — this branch covers the follow-up auto-login.
      if (err.status === 401) {
        return "We couldn't sign you in automatically. If you already have an account with this email, try logging in instead.";
      }
      break;

    case "google":
      if (err.status === 401) {
        if (/not verified/i.test(err.message)) return "Your Google account's email isn't verified.";
        if (/disabled/i.test(err.message)) return "This account has been disabled. Contact support.";
        return "Your Google sign-in session has expired. Please try again.";
      }
      if (err.status === 503) return "Google sign-in isn't available right now. Please try again later.";
      break;

    case "forgot-password":
      // /auth/forgot-password always 204s (even for an unknown email) — no
      // account-specific branch to add without becoming an enumeration oracle.
      break;

    case "reset-password":
      if (err.status === 400) return "This reset link is invalid or has expired. Request a new one.";
      break;

    case "invite-preview":
    case "invite-accept":
    case "invite-register":
      if (err.status === 410) return "This invitation has expired or is no longer valid.";
      if (err.status === 404) return "This invitation link isn't valid.";
      if (err.status === 403) return err.message; // curated "invitation is for X, not Y" — already user-safe
      if (err.status === 409) return "An account already exists for this email — log in to accept the invitation.";
      break;
  }

  return SERVER_ERROR;
}
