"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Building2, MapPin, Plus, Trash2 } from "lucide-react";
import { api, OfficeInput, OfficeOut, OrganizationOut } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, Card, Chip, ErrorNote, InfoNote, Spinner } from "@/components/ui";

const AU_STATES = ["NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"] as const;

type Profile = {
  name: string;
  legal_name: string;
  abn: string;
  acn: string;
  website: string;
  phone: string;
  primary_state: string;
};

const EMPTY_OFFICE: OfficeInput = {
  label: "",
  address: "",
  suburb: "",
  state: "",
  postcode: "",
  phone: "",
  is_primary: false,
};

const toForm = (o: OrganizationOut): Profile => ({
  name: o.name ?? "",
  legal_name: o.legal_name ?? "",
  abn: o.abn ?? "",
  acn: o.acn ?? "",
  website: o.website ?? "",
  phone: o.phone ?? "",
  primary_state: o.primary_state ?? "",
});

/** ABNs are read aloud and cross-checked in 2-3-3-3 grouping. */
const formatAbn = (abn: string) =>
  abn.length === 11 ? `${abn.slice(0, 2)} ${abn.slice(2, 5)} ${abn.slice(5, 8)} ${abn.slice(8)}` : abn;

export default function OrganisationPage() {
  const { companyId, isAdmin } = useApp();
  const [org, setOrg] = useState<OrganizationOut | null>(null);
  const [offices, setOffices] = useState<OfficeOut[] | null>(null);
  const [form, setForm] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!companyId) return;
    const [o, of] = await Promise.all([api.getOrganization(companyId), api.listOffices(companyId)]);
    setOrg(o);
    setForm(toForm(o));
    setOffices(of);
  }, [companyId]);

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load]);

  // Only changed fields are sent — a PATCH that echoes every value back would
  // overwrite concurrent edits with stale data it never actually touched.
  const changes = useMemo(() => {
    if (!org || !form) return {};
    const base = toForm(org);
    const out: Record<string, string | null> = {};
    (Object.keys(base) as (keyof Profile)[]).forEach((k) => {
      if (form[k] !== base[k]) out[k] = form[k].trim() === "" ? null : form[k].trim();
    });
    return out;
  }, [org, form]);

  const dirty = Object.keys(changes).length > 0;

  async function save() {
    if (!companyId || !dirty) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await api.updateOrganization(companyId, changes);
      setOrg(updated);
      setForm(toForm(updated));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!org || !form || !offices) {
    return (
      <div>
        <PageHeader title="Organisation" description="Your company details, as they appear on a claim." />
        {error ? <ErrorNote message={error} /> : <Spinner />}
      </div>
    );
  }

  const set = (k: keyof Profile) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: e.target.value });

  return (
    <div>
      <PageHeader
        title="Organisation"
        description="Your company details, as they appear on a claim."
        actions={
          isAdmin ? (
            <button onClick={save} disabled={!dirty || busy} className="btn-orange">
              {busy ? "Saving…" : saved ? "Saved" : "Save changes"}
            </button>
          ) : undefined
        }
      />

      {error && <ErrorNote message={error} />}
      {!isAdmin && (
        <div className="mb-6">
          <InfoNote>These details are managed by an organisation admin.</InfoNote>
        </div>
      )}

      {/* ---- Protagonist: the contracting entity. The legal name and ABN are
           what appear on a claim, so they lead; contact details support. ---- */}
      <section className="ip-card-lg mb-8">
        <div className="flex flex-wrap items-start gap-4 border-b border-ip-line p-6 sm:p-8">
          <Building2 className="mt-1 h-5 w-5 shrink-0 text-ip-navy" aria-hidden />
          <div className="min-w-0 flex-1">
            <h2 className="ip-label">Registered entity</h2>
            <div className="mt-2 text-[26px] font-bold leading-tight tracking-display text-ip-ink sm:text-[32px]">
              {form.legal_name.trim() || form.name.trim() || "Unnamed organisation"}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-ip-ink-2">
              {form.abn.trim() ? (
                <span className="tabular-nums">ABN {formatAbn(form.abn.trim())}</span>
              ) : (
                <span className="font-semibold text-ip-orange-2">No ABN recorded</span>
              )}
              {form.primary_state && <Chip tone="navy">{form.primary_state}</Chip>}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-x-6 gap-y-5 p-6 sm:grid-cols-2 sm:p-8">
          <Field id="org-name" label="Display name" hint="Shown in the app sidebar and switcher.">
            <input id="org-name" className="ip-input" value={form.name} onChange={set("name")} disabled={!isAdmin} maxLength={200} />
          </Field>

          <Field id="org-legal" label="Legal entity name" hint="The full registered name used on claims.">
            <input id="org-legal" className="ip-input" value={form.legal_name} onChange={set("legal_name")} disabled={!isAdmin} maxLength={200} placeholder="e.g. Example Constructions Pty Ltd" />
          </Field>

          <Field id="org-abn" label="ABN" hint="11 digits. Verified against the ATO checksum on save.">
            <input id="org-abn" className="ip-input tabular-nums" value={form.abn} onChange={set("abn")} disabled={!isAdmin} inputMode="numeric" maxLength={20} placeholder="12 345 678 901" />
          </Field>

          <Field id="org-acn" label="ACN" hint="9 digits. Optional for sole traders and partnerships.">
            <input id="org-acn" className="ip-input tabular-nums" value={form.acn} onChange={set("acn")} disabled={!isAdmin} inputMode="numeric" maxLength={20} />
          </Field>

          <Field
            id="org-state"
            label="Primary jurisdiction"
            hint="Default state for new projects. Security-of-payment time bars differ by state."
          >
            <select id="org-state" className="ip-input capitalize" value={form.primary_state} onChange={set("primary_state")} disabled={!isAdmin}>
              <option value="">Not set</option>
              {AU_STATES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </Field>

          <Field id="org-phone" label="Phone">
            <input id="org-phone" className="ip-input" value={form.phone} onChange={set("phone")} disabled={!isAdmin} maxLength={50} placeholder="+61 2 9000 0000" />
          </Field>

          <Field id="org-website" label="Website">
            <input id="org-website" className="ip-input" value={form.website} onChange={set("website")} disabled={!isAdmin} maxLength={300} placeholder="https://example.com.au" />
          </Field>
        </div>

        {dirty && isAdmin && (
          <div className="flex flex-wrap items-center gap-3 border-t border-ip-line bg-ip-card-2 px-6 py-3 sm:px-8">
            <span className="flex-1 text-[13px] text-ip-ink-2">
              {Object.keys(changes).length} unsaved{" "}
              {Object.keys(changes).length === 1 ? "change" : "changes"}.
            </span>
            <button onClick={() => setForm(toForm(org))} className="btn-ghost" disabled={busy}>
              Discard
            </button>
            <button onClick={save} className="btn-navy" disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        )}
      </section>

      <Offices
        companyId={companyId!}
        isAdmin={isAdmin}
        offices={offices}
        onChanged={() => load().catch((e) => setError(e.message))}
        onError={setError}
      />
    </div>
  );
}

function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="ip-label mb-1.5 block">{label}</label>
      {children}
      {hint && <p className="mt-1.5 text-[12px] leading-relaxed text-ip-ink-3">{hint}</p>}
    </div>
  );
}

function Offices({
  companyId,
  isAdmin,
  offices,
  onChanged,
  onError,
}: {
  companyId: string;
  isAdmin: boolean;
  offices: OfficeOut[];
  onChanged: () => void;
  onError: (m: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<OfficeInput>(EMPTY_OFFICE);
  const [busy, setBusy] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.label.trim()) return;
    setBusy(true);
    try {
      await api.createOffice(companyId, draft);
      setDraft(EMPTY_OFFICE);
      setAdding(false);
      onChanged();
    } catch (e: any) {
      onError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function makePrimary(id: string) {
    try {
      await api.updateOffice(companyId, id, { is_primary: true });
      onChanged();
    } catch (e: any) {
      onError(e.message);
    }
  }

  async function remove(id: string) {
    setConfirmId(null);
    try {
      await api.deleteOffice(companyId, id);
      onChanged();
    } catch (e: any) {
      onError(e.message);
    }
  }

  return (
    <section>
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="ip-label">Offices ({offices.length})</h2>
        {isAdmin && (
          <button onClick={() => setAdding((v) => !v)} className="btn-ghost">
            {adding ? "Cancel" : <><Plus className="h-3.5 w-3.5" aria-hidden />Add office</>}
          </button>
        )}
      </div>

      {adding && (
        <Card className="mb-4 p-5">
          <form onSubmit={create} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field id="office-label" label="Office name">
              <input id="office-label" className="ip-input" value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.target.value })} required maxLength={120} placeholder="e.g. Sydney head office" />
            </Field>
            <Field id="office-address" label="Street address">
              <input id="office-address" className="ip-input" value={draft.address ?? ""} onChange={(e) => setDraft({ ...draft, address: e.target.value })} maxLength={300} />
            </Field>
            <Field id="office-suburb" label="Suburb">
              <input id="office-suburb" className="ip-input" value={draft.suburb ?? ""} onChange={(e) => setDraft({ ...draft, suburb: e.target.value })} maxLength={120} />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field id="office-state" label="State">
                <select id="office-state" className="ip-input" value={draft.state ?? ""} onChange={(e) => setDraft({ ...draft, state: e.target.value })}>
                  <option value="">—</option>
                  {AU_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field id="office-postcode" label="Postcode">
                <input id="office-postcode" className="ip-input tabular-nums" value={draft.postcode ?? ""} onChange={(e) => setDraft({ ...draft, postcode: e.target.value })} inputMode="numeric" maxLength={4} />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <button className="btn-navy" disabled={busy}>{busy ? "Adding…" : "Add office"}</button>
              {offices.length === 0 && (
                <span className="ml-3 text-[12px] text-ip-ink-3">
                  Your first office becomes the primary one.
                </span>
              )}
            </div>
          </form>
        </Card>
      )}

      {offices.length === 0 && !adding ? (
        <Card className="px-6 py-10 text-center">
          <MapPin className="mx-auto h-5 w-5 text-ip-ink-3" aria-hidden />
          <div className="mt-3 text-sm font-semibold text-ip-ink">No offices recorded</div>
          <p className="mx-auto mt-1 max-w-sm text-[13px] text-ip-ink-2">
            Add the office an entity operates from — the jurisdiction affects how time bars are
            calculated.
          </p>
        </Card>
      ) : (
        <Card className="divide-y divide-ip-line">
          {offices.map((o) => (
            <div key={o.id} className="flex flex-wrap items-center gap-4 px-4 py-3.5">
              <MapPin
                className={`h-4 w-4 shrink-0 ${o.is_primary ? "text-ip-navy" : "text-ip-ink-3"}`}
                aria-hidden
              />
              <div className="min-w-[180px] flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-[14px] font-semibold text-ip-ink">{o.label}</span>
                  {o.is_primary && <Chip tone="navy">Primary</Chip>}
                </div>
                <div className="mt-0.5 text-[12px] text-ip-ink-3">
                  {[o.address, o.suburb, o.state, o.postcode].filter(Boolean).join(", ") ||
                    "No address recorded"}
                </div>
              </div>

              {isAdmin && (
                <div className="flex shrink-0 items-center gap-2">
                  {!o.is_primary && (
                    <button onClick={() => makePrimary(o.id)} className="btn-ghost px-2.5 py-1 text-xs">
                      Make primary
                    </button>
                  )}
                  {confirmId === o.id ? (
                    <>
                      <button
                        onClick={() => remove(o.id)}
                        className="rounded-md bg-ip-risk/10 px-2.5 py-1 text-xs font-semibold text-ip-risk transition-colors hover:bg-ip-risk/20"
                      >
                        Confirm
                      </button>
                      <button onClick={() => setConfirmId(null)} className="btn-ghost px-2.5 py-1 text-xs">
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => setConfirmId(o.id)}
                      aria-label={`Delete ${o.label}`}
                      className="rounded-md p-1.5 text-ip-ink-3 transition-colors hover:bg-ip-risk/10 hover:text-ip-risk"
                    >
                      <Trash2 className="h-4 w-4" aria-hidden />
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
        </Card>
      )}

      <p className="mt-4 text-[12px] text-ip-ink-3">
        Team access is managed on the{" "}
        <Link href="/app/team" className="font-semibold text-ip-navy hover:underline">Team</Link>{" "}
        page, and your plan on{" "}
        <Link href="/app/settings/billing" className="font-semibold text-ip-navy hover:underline">Billing</Link>.
      </p>
    </section>
  );
}
