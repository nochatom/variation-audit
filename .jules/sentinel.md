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

## 2026-11-12 - [Hardened SQLAlchemy Query Robustness]
**Vulnerability:** Using SQLAlchemy's `scalar_one_or_none()` on query results that can legitimately contain multiple rows (such as query on non-unique fields like user memberships) will raise a `MultipleResultsFound` exception and cause a `500 Internal Server Error` (Denial of Service/Access) for administrative or platform users.
**Learning:** For check-exist or membership queries that verify a role or existence on non-unique columns, not capping the query results can lead to crashes if a user is associated with multiple organizations or roles.
**Prevention:** Always append `.limit(1)` to any SQLAlchemy query that uses `.scalar_one_or_none()` if there's any chance of multiple records returning, or use `.first()` / `scalars().first()` to secure and gracefully fetch the first matching record.
