"use client";

import { useState } from "react";
import { Modal } from "./Modal";

export function CancelModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void;
  onConfirm: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Cancel subscription" onClose={onClose}>
      <p className="text-[14px] text-ip-ink-2">
        Your plan will remain active until the end of the current billing period, then move to the Free plan.
      </p>
      <div className="mt-3 rounded-md border border-ip-risk/30 bg-ip-risk-bg px-3 py-2 text-[13px] text-ip-risk">
        <strong>Data retention impact:</strong> moving to the Free plan applies Free-tier usage limits going
        forward. Existing projects, documents, and variation history are not deleted — see our{" "}
        <a href="/privacy" target="_blank" rel="noreferrer" className="underline">Privacy Policy</a>{" "}
        for how long data is retained if you later close the account entirely.
      </div>
      {error && <p className="mt-3 text-[13px] text-ip-risk">{error}</p>}
      <div className="mt-5 flex justify-end gap-2">
        <button className="btn-ghost" onClick={onClose} disabled={busy}>Keep subscription</button>
        <button
          onClick={confirm}
          disabled={busy}
          className="rounded-md bg-ip-risk px-3 py-2 text-sm font-semibold text-white hover:bg-ip-risk/90"
        >
          {busy ? "Cancelling…" : "Confirm cancellation"}
        </button>
      </div>
    </Modal>
  );
}
