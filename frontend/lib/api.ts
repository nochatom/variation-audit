"use client";

// Thin client for the Variation Audit product API. Stores the JWT + active
// company in localStorage and attaches the bearer token on every request.

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const TOKEN_KEY = "va_token";
const COMPANY_KEY = "va_company_id";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string) {
  window.localStorage.setItem(TOKEN_KEY, t);
}
export function getCompanyId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(COMPANY_KEY);
}
export function setCompanyId(id: string) {
  window.localStorage.setItem(COMPANY_KEY, id);
}
export function logout() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(COMPANY_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}${path}`, { ...opts, headers: { ...headers, ...(opts.headers || {}) } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || body.error?.message || detail;
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---- auth ----------------------------------------------------------------
export type TokenResponse = { access_token: string; user_id: string; email: string };
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
