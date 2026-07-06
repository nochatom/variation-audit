"use client";

import { useCallback, useEffect, useState } from "react";
import { billingApi, Features, Invoice, Seats, Subscription, Usage } from "./api";

type AsyncState<T> = { data: T | null; error: string | null; loading: boolean };

function useBillingResource<T>(companyId: string | null, fetcher: (companyId: string) => Promise<T>) {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: true });

  const reload = useCallback(async () => {
    if (!companyId) return;
    setState((s) => ({ ...s, loading: true }));
    try {
      const data = await fetcher(companyId);
      setState({ data, error: null, loading: false });
    } catch (e: any) {
      setState({ data: null, error: e.message, loading: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { ...state, reload };
}

export function useSubscription(companyId: string | null) {
  return useBillingResource<Subscription>(companyId, billingApi.getSubscription);
}

export function useUsage(companyId: string | null) {
  return useBillingResource<Usage>(companyId, billingApi.getUsage);
}

export function useInvoices(companyId: string | null) {
  return useBillingResource<Invoice[]>(companyId, billingApi.listInvoices);
}

export function useSeats(companyId: string | null) {
  return useBillingResource<Seats>(companyId, billingApi.getSeats);
}

/** Plan capability flags — components should gate features on this rather
 * than hardcoding their own plan → capability logic. */
export function useFeatures(companyId: string | null) {
  return useBillingResource<Features>(companyId, billingApi.getFeatures);
}
