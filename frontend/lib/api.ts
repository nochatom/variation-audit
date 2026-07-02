"use client";

// Thin client for the Variation Audit product API. Stores the access +
// refresh JWT pair and active company in localStorage, attaches the bearer
// token on every request, and transparently rotates the access token via
// /auth/refresh on a 401 (retrying the original request once).

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const TOKEN_KEY = "va_token";
const REFRESH_KEY = "va_refresh_token";
const COMPANY_KEY = "va_company_id";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string) {
  window.localStorage.setItem(TOKEN_KEY, t);
}
export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}
export function setRefreshToken(t: string) {
  window.localStorage.setItem(REFRESH_KEY, t);
}
export function getCompanyId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(COMPANY_KEY);
}
export function setCompanyId(id: string) {
  window.localStorage.setItem(COMPANY_KEY, id);
}
/** Store both halves of a token pair (login/signup/refresh response). */
export function storeTokens(t: { access_token: string; refresh_token: string }) {
  setToken(t.access_token);
  setRefreshToken(t.refresh_token);
}
/** Local-only clear (no server call) — used as the fallback path. */
export function logout() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
  window.localStorage.removeItem(COMPANY_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Endpoints that must never trigger the auto-refresh-and-retry loop below.
const NO_REFRESH_PATHS = ["/auth/login", "/auth/signup", "/auth/refresh"];

// De-dupes concurrent refresh attempts: if several requests 401 at once (a
// just-expired access token), only ONE /auth/refresh call should fire. Every
// refresh token is single-use (rotated) — a second concurrent call reusing
// the same stale token would be misread server-side as token theft and
// revoke every session.
let refreshInFlight: Promise<{ access_token: string; refresh_token: string }> | null = null;

async function doRefresh(): Promise<{ access_token: string; refresh_token: string }> {
  const rt = getRefreshToken();
  if (!rt) throw new ApiError(401, "no refresh token");
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: rt }),
  });
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

async function parseErrorDetail(res: Response): Promise<string> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    detail = body.detail || body.error?.message || detail;
  } catch {
    /* non-JSON error */
  }
  return detail;
}

async function request<T>(path: string, opts: RequestInit = {}, _retried = false): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}${path}`, { ...opts, headers: { ...headers, ...(opts.headers || {}) } });

  if (res.status === 401 && !_retried && !NO_REFRESH_PATHS.includes(path) && getRefreshToken()) {
    try {
      await refreshOnce();
    } catch {
      logout();
      throw new ApiError(401, await parseErrorDetail(res));
    }
    return request<T>(path, opts, true); // retry exactly once with the new access token
  }

  if (!res.ok) {
    throw new ApiError(res.status, await parseErrorDetail(res));
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
  const res = await fetch(`${BASE}${path}`, { method: "POST", headers, body: fd });

  if (res.status === 401 && !_retried && getRefreshToken()) {
    try {
      await refreshOnce();
    } catch {
      logout();
      throw new ApiError(401, await parseErrorDetail(res));
    }
    return upload<T>(path, file, field, true);
  }

  if (!res.ok) {
    throw new ApiError(res.status, await parseErrorDetail(res));
  }
  return (await res.json()) as T;
}

// ---- auth ----------------------------------------------------------------
export type TokenResponse = { access_token: string; refresh_token: string; user_id: string; email: string };
export type Me = {
  user_id: string;
  email: string;
  full_name: string | null;
  organizations: { id: string; name: string; role: string }[];
};

export const api = {
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  signup: (email: string, password: string, org_name: string, full_name?: string) =>
    request<TokenResponse>("/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password, org_name, full_name }),
    }),
  me: () => request<Me>("/auth/me"),

  /** Revoke this session's refresh token server-side, then clear local storage. */
  async logout(): Promise<void> {
    const rt = getRefreshToken();
    if (rt) {
      try {
        await fetch(`${BASE}/auth/logout`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: rt }),
        });
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

  // organization members
  orgMembers: (companyId: string) => request<MemberOut[]>(`/orgs/${companyId}/members`),
  addMember: (companyId: string, email: string, role: "admin" | "member") =>
    request<MemberOut>(`/orgs/${companyId}/members`, { method: "POST", body: JSON.stringify({ email, role }) }),
  setMemberRole: (companyId: string, userId: string, role: "admin" | "member") =>
    request<MemberOut>(`/orgs/${companyId}/members/${userId}`, { method: "PATCH", body: JSON.stringify({ role }) }),
  removeMember: (companyId: string, userId: string) =>
    request<void>(`/orgs/${companyId}/members/${userId}`, { method: "DELETE" }),

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
  markAllNotificationsRead: () => request<{ updated: number }>("/notifications/read-all", { method: "POST" }),

  // reports — PDF fetched as a blob so we can attach the bearer token
  async reportPdf(projectId: string): Promise<Blob> {
    const res = await fetch(`${BASE}/projects/${projectId}/report.pdf`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (!res.ok) throw new ApiError(res.status, "report failed");
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
  latest_job: { id: string; status: string; recoverable_total: number | null } | null;
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
export type MemberOut = { user_id: string; email: string; full_name: string | null; role: string };
export type AuditEntry = {
  id: string;
  actor_user_id: string | null;
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
