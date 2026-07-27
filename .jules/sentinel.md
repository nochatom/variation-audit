# Sentinel's Journal - Critical Security Learnings Only

This journal contains only critical, unique security learnings from maintaining and securing the Variation Audit codebase.

## 2026-07-27 - [Hardened JWT Secret Validation]
**Vulnerability:** A weak JWT secret (e.g., short string) makes the signature vulnerable to offline brute-force attacks (HS256).
**Learning:** Enforcing a minimum length of 32 characters (256 bits) at startup protects against weak configuration.
**Prevention:** Use a pydantic validator to fail-fast at startup if `VA_JWT_SECRET` is too short.
