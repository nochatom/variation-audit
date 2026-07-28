import type { Metadata } from "next";
import { Nav, SiteFooter } from "@/components/home/sections";
import { InfoNote } from "@/components/ui";

export const metadata: Metadata = {
  title: "Privacy Policy — VariationiQ",
  description: "How VariationiQ collects, stores, and processes data.",
};

export default function PrivacyPage() {
  return (
    <div className="relative min-h-screen bg-ip-bg font-ip text-ip-ink">
      <Nav />
      <main className="mx-auto max-w-[720px] px-6 py-20 sm:px-12 lg:px-16">
        <p className="ip-label text-ip-ink-3">Privacy Policy</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-ip-ink">Privacy Policy</h1>
        <p className="mt-2 text-[13px] text-ip-ink-3">Last updated: {new Date().getFullYear()}</p>

        <div className="mt-6 rounded-md border border-ip-orange/30 bg-ip-orange/12 px-4 py-3 text-[13px] leading-relaxed text-ip-ink-2">
          <strong className="text-ip-ink">Draft — pending legal review.</strong> This page describes our current
          data practices in plain terms but has not yet been reviewed by a lawyer. Don&apos;t treat it as a finalized
          legal document until this notice is removed.
        </div>

        <div className="mt-8 space-y-6 text-[15px] leading-relaxed text-ip-ink-2">
          <section>
            <h2 className="text-lg font-semibold text-ip-ink">What we collect</h2>
            <p className="mt-2">
              Account details (name, email, organization), and the project documents you upload for analysis —
              contracts, RFIs, emails, site instructions, meeting minutes, and similar records. We also keep an
              audit log of actions taken on your account (who reviewed or confirmed a variation, and when) for
              traceability.
            </p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-ip-ink">How we use it</h2>
            <p className="mt-2">
              Uploaded documents are processed to identify potential variations, estimate recoverable value, and
              flag time-bar risk. Account data is used to authenticate you, enforce organization-level access
              control, and send notifications about your own analysis jobs. We don&apos;t sell your data, and we
              don&apos;t use your project documents to train models for other customers.
            </p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-ip-ink">Where it&apos;s stored</h2>
            <p className="mt-2">
              Data is stored in Australian-region infrastructure. Access is scoped per organization — members of
              one company account cannot see another company&apos;s projects or documents.
            </p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-ip-ink">Your rights</h2>
            <p className="mt-2">
              You can request a copy of your data or request deletion of your account and associated project data
              at any time by contacting us at{" "}
              <a href="mailto:hello@variationiq.com" className="text-ip-navy underline">hello@variationiq.com</a>.
            </p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-ip-ink">Data retention</h2>
            <p className="mt-2">
              We keep account and project data for as long as your organization has an active account, plus a
              limited period afterwards to allow account recovery and to meet our own record-keeping obligations.
              When you request deletion, we remove your account, project documents, and associated variation data
              from active systems; residual copies in backups are purged on our normal backup rotation cycle
              rather than instantly. Audit log entries (who reviewed or confirmed a variation, and when) may be
              retained for a longer period where needed for security, dispute-resolution, or accounting purposes,
              consistent with typical recordkeeping practice for commercial software — the specific retention
              period is still being finalized and will be confirmed here once set.
            </p>
            <p className="mt-2">
              We&apos;re not aware of any Australian legal requirement that specifically mandates a minimum
              retention period for the kind of data VariationiQ holds, but if your organization&apos;s own
              contractual or regulatory obligations (e.g. under a head contract) require longer retention of
              project records, that is your responsibility to manage separately — we don&apos;t delete data
              against your organization&apos;s wishes while your account remains active.
            </p>
          </section>
          <section>
            <h2 className="text-lg font-semibold text-ip-ink">Security &amp; data handling</h2>
            <p className="mt-2">
              The controls described below are actively enforced in the current production system. This section
              reflects present-state functionality, not future intentions.
            </p>

            <h3 className="ip-label mt-5">1. Authentication &amp; session security</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              <li>Passwords are hashed using bcrypt before storage. Plaintext passwords are never stored, logged,
                or retrievable by VariationiQ personnel.</li>
              <li>Authentication is performed using signed JWT access tokens with short expiry, supported by
                rotating refresh tokens to limit the impact of a compromised token.</li>
              <li>Users may revoke sessions at any time, including signing out of all active devices, and sessions
                are automatically revoked on password reset.</li>
            </ul>

            <h3 className="ip-label mt-5">2. Data isolation &amp; access control</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              <li>Organizational data is isolated at the database query level — access is scoped so a user can
                retrieve only data belonging to their own organization.</li>
              <li>Role-based access control (RBAC) governs permissions within an organization: admins may manage
                members, roles, and organization-wide settings; members operate under restricted,
                role-appropriate permissions.</li>
            </ul>

            <h3 className="ip-label mt-5">3. Audit logging</h3>
            <p className="mt-2">
              An audit log records key actions for traceability and accountability, including review, approval,
              or rejection of variation findings, together with the identity of the acting user and a timestamp
              for each recorded action. Audit records are immutable once created and are not editable through the
              application.
            </p>

            <h3 className="ip-label mt-5">4. Transport &amp; application security</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              <li>All traffic is encrypted in transit via HTTPS/TLS.</li>
              <li>HTTP Strict Transport Security (HSTS) is enforced in production.</li>
              <li>A restrictive Content Security Policy (CSP) is applied to reduce the risk of cross-site
                scripting (XSS) and related injection attacks.</li>
            </ul>

            <h3 className="ip-label mt-5">5. Compliance status</h3>
            <p className="mt-2">
              VariationiQ does not currently hold formal third-party security certifications such as SOC 2 or
              ISO/IEC 27001, and no such claims are made. Our data handling practices are designed to operate
              consistently with the Australian Privacy Principles (APPs) under the <em>Privacy Act 1988</em>{" "}
              (Cth) — including purpose limitation, data security, and access/correction rights — without
              representing formal certified compliance. Controls are proportionate to the current scale and
              sensitivity of data processed and are reviewed as the platform matures. This section will be
              updated if formal certifications are obtained.
            </p>

            <h3 className="ip-label mt-5">6. Third-party service providers</h3>
            <p className="mt-2">
              We use a limited set of service providers necessary to operate VariationiQ. We do not sell personal
              information, and data is disclosed to these providers solely to the extent required for the
              functions described below.
            </p>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              <li><strong className="text-ip-ink">Anthropic</strong> — uploaded project documents are transmitted
                to Anthropic&apos;s API to perform variation detection, value estimation, and risk assessment.
                Data is processed for inference purposes only; Anthropic is not permitted to use customer data to
                train its models.</li>
              <li><strong className="text-ip-ink">Sentry</strong> — used for application error monitoring and
                debugging. May capture limited technical context (e.g. page URL, error stack trace); does not
                perform full session recording.</li>
              <li><strong className="text-ip-ink">Amazon Web Services (AWS)</strong> — uploaded documents are
                stored in Amazon S3, in the Sydney (ap-southeast-2) region.</li>
              <li><strong className="text-ip-ink">PostgreSQL</strong> — primary database for account,
                organization, and variation metadata.</li>
              <li><strong className="text-ip-ink">Email delivery</strong> — transactional email (invitations,
                password resets) is sent via SMTP. A named provider has not yet been finalized; this section will
                be updated once one is selected.</li>
            </ul>

            <h3 className="ip-label mt-5">7. Cookies &amp; authentication tokens</h3>
            <p className="mt-2">
              VariationiQ does not use advertising or behavioral tracking cookies. Authentication relies on JWT
              tokens rather than session cookies: stored in{" "}
              <code className="rounded bg-ip-card-2 px-1 py-0.5 text-[13px]">localStorage</code> if
              &quot;Remember me&quot; is selected, or in{" "}
              <code className="rounded bg-ip-card-2 px-1 py-0.5 text-[13px]">sessionStorage</code> otherwise
              (cleared when the browser session ends). Tokens are transmitted with each request solely to
              authenticate the user — not used for tracking, profiling, or analytics.
            </p>

            <h3 className="ip-label mt-5">8. Data residency &amp; international transfers</h3>
            <p className="mt-2">
              Account, project, and document data is primarily stored in AWS&apos;s Sydney (ap-southeast-2)
              region. Limited cross-border transfers occur as a function of the third-party services above:
              document content sent to Anthropic (a US-based provider) for AI-assisted analysis, and
              error-monitoring data sent to Sentry, processed in Sentry&apos;s EU data region. These transfers
              occur only as necessary to provide the service and are subject to each provider&apos;s own standard
              terms; we do not currently maintain bespoke data processing agreements beyond those terms.
              Organizations with specific data residency, regulatory, or contractual requirements should contact
              us before uploading sensitive project data, so we can advise whether current arrangements meet
              those requirements.
            </p>

            <div className="mt-5">
              <InfoNote>
                <strong className="text-ip-ink">Note for enterprise users: </strong>
                VariationiQ supports operational analysis of construction project documents. It does not
                constitute legal, contractual, or financial advice, and outputs — including AI-generated
                variation candidates — should be independently reviewed by qualified personnel before being
                relied upon.
              </InfoNote>
            </div>
          </section>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
