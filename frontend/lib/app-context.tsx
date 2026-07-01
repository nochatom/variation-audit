"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  getToken,
  getCompanyId,
  setCompanyId as persistCompany,
  logout as apiLogout,
  Me,
} from "./api";

type Org = { id: string; name: string; role: string };
type Ctx = {
  me: Me | null;
  companyId: string | null;
  org: Org | null;
  isAdmin: boolean;
  setCompany: (id: string) => void;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
};

const AppContext = createContext<Ctx | null>(null);

export function useApp(): Ctx {
  const c = useContext(AppContext);
  if (!c) throw new Error("useApp must be used inside <AppProvider>");
  return c;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [companyId, setCid] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  async function reload() {
    const m = await api.me();
    setMe(m);
    let cid = getCompanyId();
    if (!cid || !m.organizations.some((o) => o.id === cid)) {
      cid = m.organizations[0]?.id ?? null;
      if (cid) persistCompany(cid);
    }
    setCid(cid);
  }

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    reload()
      .then(() => setReady(true))
      .catch(() => {
        apiLogout();
        router.replace("/login");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function setCompany(id: string) {
    persistCompany(id);
    setCid(id);
  }
  async function logout() {
    await api.logout(); // revokes the refresh token server-side, then clears local storage
    router.replace("/login");
  }

  const org = me?.organizations.find((o) => o.id === companyId) ?? me?.organizations[0] ?? null;
  const value: Ctx = {
    me,
    companyId,
    org,
    isAdmin: org?.role === "admin",
    setCompany,
    logout,
    reload,
  };

  if (!ready) {
    return <div className="grid min-h-screen place-items-center bg-ip-bg font-ip text-sm text-ip-ink-3">Loading workspace…</div>;
  }
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
