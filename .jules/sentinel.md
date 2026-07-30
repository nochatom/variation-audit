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

## 2026-07-30 - [Resilient Platform-Wide Admin Authorization]
**Vulnerability:** When a user is an administrator of multiple organizations, global or platform-wide admin check queries that look up the admin membership without filtering by a specific organization can crash with `sqlalchemy.exc.MultipleResultsFound` (HTTP 500) if they use `.scalar_one_or_none()`. This causes a Denial of Service (DoS) lockout for administrators belonging to multiple tenants.
**Learning:** `.scalar_one_or_none()` is only safe when the query is guaranteed to return at most one result (e.g. by a unique index or filtering on both user and company). When querying for *any* matching membership globally, any user with multiple matched memberships will cause a crash.
**Prevention:** For existential checks or to verify if at least one matching row exists, use `.limit(1)` and `.scalars().first()` instead of `.scalar_one_or_none()`.
