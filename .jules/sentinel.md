# Sentinel's Journal - Critical Security Learnings Only

This journal contains only critical, unique security learnings from maintaining and securing the Variation Audit codebase.

## 2026-07-27 - [Hardened JWT Secret Validation]
**Vulnerability:** A weak JWT secret (e.g., short string) makes the signature vulnerable to offline brute-force attacks (HS256).
**Learning:** Enforcing a minimum length of 32 characters (256 bits) at startup protects against weak configuration.
**Prevention:** Use a pydantic validator to fail-fast at startup if `VA_JWT_SECRET` is too short.

## 2026-10-24 - [Robust OAuth JWT Email Verification]
**Vulnerability:** Social/OAuth logins (e.g. Google via Supabase Auth) do not place the `email_verified` boolean claim in the JWT top-level payload, but rather nest it inside `user_metadata.email_verified`. If the backend only looks for `email_verified` at the top level, it would mistakenly treat verified OAuth users as unverified, creating a risk where developers might bypass verification checks to restore login functionality.
**Learning:** Supabase GoTrue maps provider-specific verification status under `user_metadata` inside the JWT claims. To avoid either breaking social login or accidentally failing-open on unverified claims, we must robustly look for `email_verified` in both the top-level payload and nested metadata.
**Prevention:** Always parse `email_verified` with a fallback chain checking top-level first, then nested `user_metadata`, before failing-closed to `False`.

## 2026-11-12 - [Constant-Time Authentication Parity]
**Vulnerability:** User enumeration via login timing attacks. If login queries for invalid/inactive/passwordless users return instantly while valid password-based login spends 90ms on bcrypt hashing, an attacker can determine registered emails.
**Learning:** Returning early on missing, inactive, or passwordless users skips the expensive cryptographic verification, making login timing highly diagnostic of user existence.
**Prevention:** Execute a dummy bcrypt verification against a pre-computed valid cost-10 hash whenever the user lookup fails, the user is inactive, or has no password hash, ensuring constant-time authentication across all branches.

## 2026-08-05 - [FastAPI Dependency vs. SlowAPI Execution Order]
**Vulnerability:** Bypassed rate limiting on authentication-dependent routes during unauthenticated scanning/brute-force. If a route requires `Depends(get_current_user)`, FastAPI runs dependencies before executing the rate limit decorator. Unauthenticated requests fail-early with a 401, entirely bypassing the rate limiter count.
**Learning:** Slowapi rate-limit decorators apply at the handler function level, meaning they do not count requests that abort early inside FastAPI's dependency injection chain. This makes endpoints requiring authentication vulnerable to rapid unauthorized requests/scanning/DoS without triggering rate limiting, unless the dependency checks themselves are handled carefully or rate limits are applied globally/at middleware level.
**Prevention:** To thoroughly test rate limits in unit tests on endpoints that depend on authenticated users, mock/override dependencies using `app.dependency_overrides` so the request can enter the endpoint handler and trigger the rate limiter. Be aware that unauthenticated requests to authenticated routes bypass slowapi rate counters.
