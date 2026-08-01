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

## 2026-10-25 - [Preventing Server Denial of Service on Multi-Org Auth Checks]
**Vulnerability:** In multi-tenant environments, query methods checking for a user's multi-organization administrative presence (such as `require_any_org_admin`) can raise `MultipleResultsFound` when using SQLAlchemy's `scalar_one_or_none()` on unconstrained queries. This crashes the server with a 500 error, resulting in a denial of service for administrative functions.
**Learning:** Checking for "at least one" matching record must explicitly use query bounds (like `.limit(1)`) or `.first()` rather than calling `.scalar_one_or_none()` on queries that are not uniquely constrained.
**Prevention:** Always append `.limit(1)` to SQLAlchemy select queries that verify existence across multiple possible rows before calling `.scalar_one_or_none()`.
