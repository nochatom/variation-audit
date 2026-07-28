# Sentinel's Journal - Critical Security Learnings Only

This journal contains only critical, unique security learnings from maintaining and securing the Variation Audit codebase.

## 2026-07-27 - [Hardened JWT Secret Validation]
**Vulnerability:** A weak JWT secret (e.g., short string) makes the signature vulnerable to offline brute-force attacks (HS256).
**Learning:** Enforcing a minimum length of 32 characters (256 bits) at startup protects against weak configuration.
**Prevention:** Use a pydantic validator to fail-fast at startup if `VA_JWT_SECRET` is too short.

## 2026-07-28 - [Mock Result Exhaustion in Multiple API Assertions]
**Vulnerability:** Not a direct application vulnerability, but a testing pitfall. Writing multi-step assertions on a single test client instance can lead to silent auth failures (404/403) due to fake DB session exhaustion.
**Learning:** `FakeSession` consumes mock query results sequentially across API requests. Making consecutive calls (e.g., testing multiple input validation failures) on the same client consumes mock membership results, resulting in subsequent requests failing auth checks with `404 Not Found` rather than hitting input validation.
**Prevention:** Always re-instantiate or supply fresh client/project fixtures (e.g. calling `_project_client()`) for each consecutive API test call to reset the mock DB session results.
