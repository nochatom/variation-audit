"use client";

// Thin client for the Variation Audit product API. Stores the access +
// refresh JWT pair and active company in localStorage, attaches the bearer
// token on every request, and transparently rotates the access token via
// /auth/refresh on a 401 (retrying the original request once).

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
// Same origin the JSON client targets — exported so the SSE progress stream
// (EventSource) can build its URL against the identical backend.
export const API_BASE = BASE;

// fetch() has no default timeout. If the API host accepts the TCP connection
// but never answers (backend wedged mid-request, laptop resumed from sleep,
// proxy black-holing the socket), the promise never settles — so callers'
// `finally` blocks never run and any spinner tied to them spins forever. A
// refused connection rejects immediately and was always handled; this covers
// the stalled case, rejecting so the UI shows the network error it already
// knows how to render (mapAuthError's non-ApiError branch).
const REQUEST_TIMEOUT_MS = 30_000;
// Uploads stream real files through the same client, so the 30s budget above
// would abort legitimate large transfers. They get their own, longer one.
const UPLOAD_TIMEOUT_MS = 5 * 60_000;

/** fetch() + an abort-based deadline, preserving any caller-supplied signal. */
async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const external = init.signal;
  if (external) {
    if (external.aborted) controller.abort();
    else external.addEventListener("abort", () => controller.abort(), { once: true });
  }
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

const TOKEN_KEY = "va_token";
const REFRESH_KEY = "va_refresh_token";
const COMPANY_KEY = "va_company_id";
const REMEMBER_KEY = "va_remember";

// "Remember me" unchecked -> tokens live in sessionStorage (cleared when the
// browser closes) instead of localStorage. The flag itself is always in
// localStorage (it's not sensitive) so every tab/reload agrees on which
// storage to read from.
function rememberEnabled(): boolean {
  if (typeof window === "undefined") return true;
  return window.localStorage.getItem(REMEMBER_KEY) !== "0";
}
function tokenStorage(): Storage {
  return rememberEnabled() ? window.localStorage : window.sessionStorage;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return tokenStorage().getItem(TOKEN_KEY);
}
export function setToken(t: string) {
  tokenStorage().setItem(TOKEN_KEY, t);
}
export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return tokenStorage().getItem(REFRESH_KEY);
}
export function setRefreshToken(t: string) {
  tokenStorage().setItem(REFRESH_KEY, t);
}
export function getCompanyId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(COMPANY_KEY);
}
export function setCompanyId(id: string) {
  window.localStorage.setItem(COMPANY_KEY, id);
}
/** Store both halves of a token pair (login/signup/refresh/invitation
 * response). `remember` only matters on the initial sign-in (it decides
 * localStorage vs sessionStorage); omit it on refresh so the original choice
 * sticks for the rest of the session. */
export function storeTokens(t: { access_token: string; refresh_token: string }, remember?: boolean) {
  if (remember !== undefined) {
    window.localStorage.setItem(REMEMBER_KEY, remember ? "1" : "0");
  }
  setToken(t.access_token);
  setRefreshToken(t.refresh_token);
}
/** Local-only clear (no server call) — used as the fallback path. */
export function logout() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
  window.localStorage.removeItem(COMPANY_KEY);
  window.localStorage.removeItem(REMEMBER_KEY);
  window.sessionStorage.removeItem(TOKEN_KEY);
  window.sessionStorage.removeItem(REFRESH_KEY);
}

export class ApiError extends Error {
  status: number;
  /** Machine-readable error code from the backend's {"error":{"code",...}}
   * envelope (see backend app/errors.py), e.g. "UNAUTHORIZED",
   * "VALIDATION_ERROR", "RATE_LIMITED". Undefined for responses that don't
   * use the envelope (rare — kept optional rather than widening every call
   * site). */
  code?: string;
  /** Field-level validation errors (422 VALIDATION_ERROR only) — {loc,
   * message} pairs straight from FastAPI's RequestValidationError, e.g.
   * {loc: ["body", "email"], message: "value is not a valid email address"}. */
  fields?: { loc: string[]; message: string }[];
  constructor(status: number, message: string, code?: string, fields?: { loc: string[]; message: string }[]) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

// Endpoints that must never trigger the auto-refresh-and-retry loop below.
const NO_REFRESH_PATHS = ["/auth/login", "/auth/signup", "/auth/refresh", "/auth/google"];

// De-dupes concurrent refresh attempts: if several requests 401 at once (a
// just-expired access token), only ONE /auth/refresh call should fire. Every
// refresh token is single-use (rotated) — a second concurrent call reusing
// the same stale token would be misread server-side as token theft and
// revoke every session.
let refreshInFlight: Promise<{ access_token: string; refresh_token: string }> | null = null;

async function doRefresh(): Promise<{ access_token: string; refresh_token: string }> {
  const rt = getRefreshToken();
  if (!rt) throw new ApiError(401, "no refresh token");
  const res = await fetchWithTimeout(
    `${BASE}/auth/refresh`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: rt }),
    },
    REQUEST_TIMEOUT_MS,
  );
  if (!res.ok) throw new ApiError(res.status, "session expired");
  const body = await res.json();
  storeTokens(body);
  return body;
}

async function refreshOnce(): Promise<{ access_token: string; refresh_token: string }> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

type ErrorBody = { message: string; code?: string; fields?: { loc: string[]; message: string }[] };

/** Parses the backend's standard {"error":{"code","message","fields"?}}
 * envelope (app/errors.py). Also tolerates two non-standard shapes seen in
 * practice: slowapi's own rate-limit handler, which responds with a bare
 * {"error": "Rate limit exceeded: ..."} string instead of the envelope; and
 * a legacy {"detail": "..."} body. Never surfaces anything beyond what the
 * backend put in the body — no stack traces reach the client either way. */
async function parseErrorBody(res: Response): Promise<ErrorBody> {
  let message = res.statusText || "Request failed.";
  let code: string | undefined;
  let fields: { loc: string[]; message: string }[] | undefined;
  try {
    const body = await res.json();
    if (body && typeof body === "object") {
      if (body.error && typeof body.error === "object") {
        if (typeof body.error.message === "string") message = body.error.message;
        if (typeof body.error.code === "string") code = body.error.code;
        if (Array.isArray(body.error.fields)) fields = body.error.fields;
      } else if (typeof body.error === "string") {
        message = body.error;
        code = "RATE_LIMITED";
      } else if (typeof body.detail === "string") {
        message = body.detail;
      }
    }
  } catch {
    /* non-JSON error body */
  }
  return { message, code, fields };
}

export async function request<T>(path: string, opts: RequestInit = {}, _retried = false): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetchWithTimeout(
    `${BASE}${path}`,
    { ...opts, headers: { ...headers, ...(opts.headers || {}) } },
    REQUEST_TIMEOUT_MS,
  );

  if (res.status === 401 && !_retried && !NO_REFRESH_PATHS.includes(path) && getRefreshToken()) {
    try {
      await refreshOnce();
    } catch {
      logout();
      const { message, code, fields } = await parseErrorBody(res);
      throw new ApiError(401, message, code, fields);
    }
    return request<T>(path, opts, true); // retry exactly once with the new access token
  }

  if (!res.ok) {
    const { message, code, fields } = await parseErrorBody(res);
    throw new ApiError(res.status, message, code, fields);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// multipart upload (bearer token, no JSON content-type)
async function upload<T>(path: string, file: File, field = "file", _retried = false): Promise<T> {
  const fd = new FormData();
  fd.append(field, file);
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetchWithTimeout(`${BASE}${path}`, { method: "POST", headers, body: fd }, UPLOAD_TIMEOUT_MS);

  if (res.status === 401 && !_retried && getRefreshToken()) {
    try {
      await refreshOnce();
    } catch {
      logout();
      const { message, code, fields } = await parseErrorBody(res);
      throw new ApiError(401, message, code, fields);
    }
    return upload<T>(path, file, field, true);
  }

  if (!res.ok) {
    const { message, code, fields } = await parseErrorBody(res);
    throw new ApiError(res.status, message, code, fields);
  }
  return (await res.json()) as T;
}

// ---- auth ----------------------------------------------------------------
export type Org = { id: string; name: string; role: string };
// `organizations` lets a post-login/signup redirect read the default
// company_id straight off this response instead of an extra GET /auth/me
// round trip made purely to learn it (see login-latency fix).
export type TokenResponse = {
  access_token: string; refresh_token: string; user_id: string; email: string; organizations: Org[];
};
export type Me = {
  user_id: string;
  email: string;
  full_name: string | null;
  organizations: Org[];
};

export const api = {
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  /** Non-enumerating: always resolves with a generic message, whether or not
   * the email already has an account (the backend emails the owner in that
   * case). Callers obtain tokens with a follow-up login() using the same
   * credentials — it fails with the generic "invalid credentials" if the
   * account already existed. */
  signup: (email: string, password: string, org_name: string, full_name?: string) =>
    request<{ message: string }>("/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password, org_name, full_name }),
    }),
  me: () => request<Me>("/auth/me"),
  /** Update the current user's own editable profile fields (full name).
   * Returns the same Me shape as me() so the caller can refresh its cache. */
  updateMe: (full_name: string | null) =>
    request<Me>("/auth/me", { method: "PATCH", body: JSON.stringify({ full_name }) }),
  /** Exchanges a Supabase Google-login session for this app's own token pair
   * — an additional entry point into the existing session system, not a
   * separate one. Same TokenResponse shape as login/signup. */
  googleLogin: (supabaseAccessToken: string) =>
    request<TokenResponse>("/auth/google", {
      method: "POST",
      body: JSON.stringify({ supabase_access_token: supabaseAccessToken }),
    }),
  /** Always resolves (backend responds 204 regardless of whether the email exists). */
  forgotPassword: (email: string) =>
    request<void>("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }),
  resetPassword: (token: string, new_password: string) =>
    request<void>("/auth/reset-password", { method: "POST", body: JSON.stringify({ token, new_password }) }),

  /** Revoke this session's refresh token server-side, then clear local storage. */
  async logout(): Promise<void> {
    const rt = getRefreshToken();
    if (rt) {
      try {
        await fetchWithTimeout(
          `${BASE}/auth/logout`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: rt }),
          },
          REQUEST_TIMEOUT_MS,
        );
      } catch {
        /* best-effort — still clear local state even if the network call fails */
      }
    }
    logout();
  },
  /** Revoke every refresh token for the current user — signs out all devices. */
  logoutAll: () => request<void>("/auth/logout-all", { method: "POST" }),

  // dashboard
  orgDashboard: (companyId: string) => request<OrgDashboard>(`/dashboard?company_id=${companyId}`),
  projectDashboard: (projectId: string) => request<ProjectDashboard>(`/projects/${projectId}/dashboard`),

  // projects
  createProject: (companyId: string, name: string, contract_text?: string, state?: string) =>
    request<{ id: string }>("/projects", {
      method: "POST",
      body: JSON.stringify({ company_id: companyId, name, contract_text, state }),
    }),
  analyze: (projectId: string) =>
    request<{ job_id: string; status: string }>(`/projects/${projectId}/analyze`, { method: "POST" }),
  /** Stop a queued/running analysis. Returns the job's new status
   * ("cancelled" if queued, still "running" if the worker must terminalize it). */
  cancelAnalysis: (projectId: string, jobId: string) =>
    request<{ job_id: string; status: string }>(
      `/projects/${projectId}/analysis/${jobId}/cancel`, { method: "POST" }),

  // review
  reviewQueue: (projectId: string, companyId: string, status = "pending") =>
    request<VariationSummary[]>(
      `/projects/${projectId}/review-queue?company_id=${companyId}&review_status=${status}`,
    ),
  variation: (id: string) => request<VariationDetail>(`/variations/${id}`),
  review: (id: string, status: "confirmed" | "rejected" | "pending") =>
    request<VariationSummary>(`/variations/${id}/review`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),
  addComment: (id: string, body: string) =>
    request<Comment>(`/variations/${id}/comments`, { method: "POST", body: JSON.stringify({ body }) }),

  // projects (list + ingestion)
  listProjects: (companyId: string, archived = false) =>
    request<ProjectOut[]>(`/projects?company_id=${companyId}&archived=${archived}`),
  getProject: (projectId: string) => request<ProjectOut>(`/projects/${projectId}`),
  archiveProject: (projectId: string) =>
    request<ProjectOut>(`/projects/${projectId}/archive`, { method: "POST" }),
  unarchiveProject: (projectId: string) =>
    request<ProjectOut>(`/projects/${projectId}/unarchive`, { method: "POST" }),
  deleteProject: (projectId: string) =>
    request<void>(`/projects/${projectId}`, { method: "DELETE" }),
  uploadContract: (projectId: string, file: File, isScope = false) =>
    upload<ProjectOut>(`/projects/${projectId}/contract?is_scope=${isScope}`, file),
  uploadDocs: (
    projectId: string,
    kind: "comms" | "rfis" | "site-instructions" | "meeting-minutes",
    file: File,
  ) => upload<UploadResult>(`/projects/${projectId}/${kind}`, file),
  /** Single arbitrary supporting document (PDF/text) — source_type=document. */
  uploadDocument: (projectId: string, file: File) =>
    upload<DocumentOut>(`/projects/${projectId}/documents`, file),

  // organization profile + offices (0017)
  getOrganization: (companyId: string) => request<OrganizationOut>(`/orgs/${companyId}`),
  updateOrganization: (companyId: string, changes: Partial<OrganizationUpdate>) =>
    request<OrganizationOut>(`/orgs/${companyId}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  listOffices: (companyId: string) => request<OfficeOut[]>(`/orgs/${companyId}/offices`),
  createOffice: (companyId: string, office: OfficeInput) =>
    request<OfficeOut>(`/orgs/${companyId}/offices`, {
      method: "POST",
      body: JSON.stringify(office),
    }),
  updateOffice: (companyId: string, officeId: string, changes: Partial<OfficeInput>) =>
    request<OfficeOut>(`/orgs/${companyId}/offices/${officeId}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  deleteOffice: (companyId: string, officeId: string) =>
    request<void>(`/orgs/${companyId}/offices/${officeId}`, { method: "DELETE" }),

  // organization members
  orgMembers: (companyId: string) => request<MemberOut[]>(`/orgs/${companyId}/members`),
  setMemberRole: (companyId: string, userId: string, role: "admin" | "member") =>
    request<MemberOut>(`/orgs/${companyId}/members/${userId}`, { method: "PATCH", body: JSON.stringify({ role }) }),
  removeMember: (companyId: string, userId: string) =>
    request<void>(`/orgs/${companyId}/members/${userId}`, { method: "DELETE" }),

  // organization invitations — never requires the invited email to already
  // have an account; a pending invitation is created either way.
  orgInvitations: (companyId: string) => request<InvitationOut[]>(`/orgs/${companyId}/invitations`),
  createInvitation: (companyId: string, email: string, role: "admin" | "member") =>
    request<InvitationOut>(`/orgs/${companyId}/invitations`, {
      method: "POST",
      body: JSON.stringify({ email, role }),
    }),
  revokeInvitation: (companyId: string, invitationId: string) =>
    request<void>(`/orgs/${companyId}/invitations/${invitationId}`, { method: "DELETE" }),

  // accept-invite flow (public token lookup + accept/register)
  previewInvitation: (token: string) => request<InvitationPreview>(`/invitations/${token}`),
  acceptInvitation: (token: string) =>
    request<{ company_id: string; role: string }>(`/invitations/${token}/accept`, { method: "POST" }),
  registerViaInvitation: (token: string, password: string, full_name?: string) =>
    request<TokenResponse>(`/invitations/${token}/register`, {
      method: "POST",
      body: JSON.stringify({ password, full_name }),
    }),

  // audit & evidence
  auditLog: (companyId: string, entityType?: string, limit = 100) =>
    request<AuditEntry[]>(
      `/audit?company_id=${companyId}${entityType ? `&entity_type=${entityType}` : ""}&limit=${limit}`,
    ),
  variationAudit: (id: string) => request<AuditEntry[]>(`/variations/${id}/audit`),
  variationEvidence: (id: string) => request<EvidenceContext[]>(`/variations/${id}/evidence`),

  // notifications
  notifications: (unread = false) => request<NotificationItem[]>(`/notifications?unread=${unread}`),
  unreadCount: () => request<{ count: number }>("/notifications/unread-count"),
  markNotificationRead: (id: string) =>
    request<NotificationItem>(`/notifications/${id}/read`, { method: "POST" }),
  // Backend returns {"marked": n} (routers/notifications.py) — not {"updated"}.
  markAllNotificationsRead: () => request<{ marked: number }>("/notifications/read-all", { method: "POST" }),

  // reports — PDF fetched as a blob so we can attach the bearer token
  async reportPdf(projectId: string, reviewStatus: "confirmed" | "pending" | "rejected" = "confirmed"): Promise<Blob> {
    // PDF generation is server-side rendering work over a whole project, so
    // it gets the upload-sized budget rather than the 30s interactive one.
    const res = await fetchWithTimeout(
      `${BASE}/projects/${projectId}/report.pdf?review_status=${reviewStatus}`,
      { headers: { Authorization: `Bearer ${getToken()}` } },
      UPLOAD_TIMEOUT_MS,
    );
    if (!res.ok) {
      // Surface the REAL backend error (e.g. the 403 "the 'exports' feature
      // isn't available on your current plan — upgrade to access it", or a
      // 500's detail) instead of a generic "report failed". The body carries
      // the actionable message — parseErrorBody reads {error:{message}}.
      const { message, code, fields } = await parseErrorBody(res);
      throw new ApiError(res.status, message, code, fields);
    }
    return res.blob();
  },
};

// ---- types ---------------------------------------------------------------
export type Counts = { pending: number; confirmed: number; rejected: number; total: number };
export type OrgDashboard = {
  totals: { projects: number; pending: number; confirmed: number; recoverable_confirmed: number; currency: string };
  projects: {
    id: string;
    name: string;
    status: string;
    has_contract: boolean;
    counts: Counts;
    recoverable_confirmed: number;
    time_bar_at_risk: number;
  }[];
};
export type ProjectDashboard = {
  project: { id: string; name: string; state: string | null; status: string; has_contract: boolean };
  counts: Counts;
  recoverable_confirmed: number;
  time_bar_at_risk: number;
  document_count: number;
  latest_job: {
    id: string;
    status: string;
    recoverable_total: number | null;
    error_code?: string | null;
    error_message?: string | null;
    error_retryable?: boolean | null;
  } | null;
};
export type VariationSummary = {
  id: string;
  title: string;
  confidence_score: number;
  confidence_band: string | null;
  time_bar_risk: boolean;
  review_status: string;
  amount: number | null;
};
export type Comment = { id: string; body: string; author_user_id: string | null; created_at: string };
export type VariationDetail = VariationSummary & {
  description: string | null;
  evidence: { type: string; reference: string | null; quote: string | null }[];
  value: { amount: number | null; estimate_low: number | null; estimate_high: number | null; basis_quality: string | null } | null;
  comments: Comment[];
};
export type ProjectOut = {
  id: string;
  company_id: string;
  name: string;
  state: string | null;
  status: string;
  has_contract: boolean;
  archived_at: string | null;
};
export type UploadResult = { project_id: string; documents_added: number };
export type DocumentOut = {
  id: string;
  project_id: string;
  source_type: string;
  storage_key: string;
  size_bytes: number;
};
export type OrganizationOut = {
  id: string;
  name: string;
  legal_name: string | null;
  abn: string | null;
  acn: string | null;
  website: string | null;
  phone: string | null;
  logo_key: string | null;
  primary_state: string | null;
};
/** Writable subset — logo_key is set by the upload route, not by PATCH. */
export type OrganizationUpdate = Omit<OrganizationOut, "id" | "logo_key">;
export type OfficeOut = {
  id: string;
  label: string;
  address: string | null;
  suburb: string | null;
  state: string | null;
  postcode: string | null;
  phone: string | null;
  is_primary: boolean;
};
export type OfficeInput = Omit<OfficeOut, "id">;
export type MemberOut = { user_id: string; email: string; full_name: string | null; role: string };
export type InvitationOut = {
  id: string;
  email: string;
  role: string;
  status: string;
  invited_by: string | null;
  created_at: string;
  expires_at: string;
  accept_url: string | null;
  email_sent: boolean | null;
};
export type InvitationPreview = { email: string; org_name: string; role: string; account_exists: boolean };
export type AuditEntry = {
  id: string;
  actor_user_id: string | null;
  /** Resolved server-side. Null for system-generated events, or when the actor
   *  no longer exists — fall back to the id, never render a bare UUID as if it
   *  were a name. */
  actor_name: string | null;
  /** Resolved server-side from entity_type + entity_id. Null when the entity has
   *  since been deleted, which is expected in an append-only log. */
  entity_label: string | null;
  entity_type: string;
  entity_id: string;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
};
export type EvidenceContext = {
  type: string;
  reference: string | null;
  quote: string | null;
  source_document: { id: string; source_type: string; source: string | null; doc_timestamp: string | null } | null;
};
export type NotificationItem = {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  read: boolean;
  created_at: string;
};
