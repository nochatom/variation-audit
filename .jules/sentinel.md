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

## 2026-10-25 - [SQLAlchemy `.scalar_one_or_none()` on Non-Unique Queries]
**Vulnerability:** Using `.scalar_one_or_none()` on database queries where a user can logically possess multiple matching records (such as checking if a user is an admin of any organization) triggers a `MultipleResultsFound` exception, crashing the API endpoint with a 500 Internal Server Error. This exposes the platform endpoints to denial-of-service (DoS).
**Learning:** In multi-tenant environments with roles scoped per-tenant, queries confirming a platform-wide role (e.g. "is an admin of *any* organization") must not assume a single result. Using `scalar_one_or_none()` causes an unhandled exception once a user becomes an admin of multiple tenants.
**Prevention:** Use `.scalars().first()` or `.limit(1)` to safely query role presence when multiple roles/memberships can logically exist for a single user.
