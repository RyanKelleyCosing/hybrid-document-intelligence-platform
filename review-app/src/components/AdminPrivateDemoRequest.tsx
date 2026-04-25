import { useMemo, useState } from "react";

import { HOME_PATH } from "../appRoutes";
import { ProtectedSiteLayout } from "./ProtectedSiteLayout";
import { SectionHeading, SurfaceCard, SurfacePanel } from "./SurfacePrimitives";

const CONTACT_EMAIL =
  import.meta.env.VITE_PUBLIC_CONTACT_EMAIL?.trim() || "demo@ryancodes.online";

type FormState = {
  company: string;
  email: string;
  monthlyVolume: string;
  name: string;
  notes: string;
  useCase: string;
};

const initialFormState: FormState = {
  company: "",
  email: "",
  monthlyVolume: "",
  name: "",
  notes: "",
  useCase: "",
};

function buildMailtoHref(form: FormState): string {
  const subject = `Private demo request — ${form.company || form.name || "Hybrid Document Intelligence"}`;
  const lines = [
    `Name: ${form.name || "(not provided)"}`,
    `Company: ${form.company || "(not provided)"}`,
    `Email: ${form.email || "(not provided)"}`,
    `Primary use case: ${form.useCase || "(not provided)"}`,
    `Estimated monthly document volume: ${form.monthlyVolume || "(not provided)"}`,
    "",
    "Notes:",
    form.notes || "(none)",
  ];
  const body = lines.join("\n");
  return `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

export function AdminPrivateDemoRequest() {
  const [form, setForm] = useState<FormState>(initialFormState);
  const [submitted, setSubmitted] = useState(false);

  const mailtoHref = useMemo(() => buildMailtoHref(form), [form]);

  const handleChange = (
    field: keyof FormState,
  ): React.ChangeEventHandler<HTMLInputElement | HTMLTextAreaElement> => {
    return (event) => {
      setForm((current) => ({ ...current, [field]: event.target.value }));
    };
  };

  const handleSubmit: React.FormEventHandler<HTMLFormElement> = (event) => {
    event.preventDefault();
    if (typeof window !== "undefined") {
      window.location.href = mailtoHref;
    }
    setSubmitted(true);
  };

  return (
    <ProtectedSiteLayout
      navigation={
        <aside
          aria-label="Simulation admin entry"
          className="admin-loading-nav"
        >
          <p className="eyebrow">Simulation mode</p>
          <p className="workspace-copy">
            The protected operator workbench is reserved for invited reviewers.
            Use the form on the right to request a private walkthrough; you
            will get a calendar reply within one business day.
          </p>
          <p className="workspace-copy">
            <a className="button-link" href={HOME_PATH}>
              ← Back to public landing
            </a>
          </p>
        </aside>
      }
    >
      <SurfacePanel as="section" id="admin-private-demo-request">
        <SectionHeading
          description="The live admin workbench requires Microsoft Easy Auth and an explicit operator allowlist. Tell us a little about your team and we will reach out with private credentials and a scheduled walkthrough."
          title="Request a private admin demo"
        />
        <form
          aria-label="Request a private admin demo"
          className="private-demo-form"
          onSubmit={handleSubmit}
        >
          <div className="private-demo-form-grid">
            <label className="private-demo-field">
              <span>Your name</span>
              <input
                autoComplete="name"
                onChange={handleChange("name")}
                required
                type="text"
                value={form.name}
              />
            </label>
            <label className="private-demo-field">
              <span>Work email</span>
              <input
                autoComplete="email"
                onChange={handleChange("email")}
                required
                type="email"
                value={form.email}
              />
            </label>
            <label className="private-demo-field">
              <span>Company / team</span>
              <input
                autoComplete="organization"
                onChange={handleChange("company")}
                type="text"
                value={form.company}
              />
            </label>
            <label className="private-demo-field">
              <span>Primary use case</span>
              <input
                onChange={handleChange("useCase")}
                placeholder="Loan packets, claims intake, vendor invoices..."
                type="text"
                value={form.useCase}
              />
            </label>
            <label className="private-demo-field">
              <span>Estimated monthly document volume</span>
              <input
                inputMode="numeric"
                onChange={handleChange("monthlyVolume")}
                placeholder="e.g. 5,000"
                type="text"
                value={form.monthlyVolume}
              />
            </label>
          </div>
          <label className="private-demo-field private-demo-field--full">
            <span>Anything else we should know? (optional)</span>
            <textarea
              onChange={handleChange("notes")}
              rows={4}
              value={form.notes}
            />
          </label>
          <div className="private-demo-actions">
            <button className="button-primary" type="submit">
              Send private demo request
            </button>
            <a className="button-link secondary-link" href={mailtoHref}>
              Or open in your mail client
            </a>
            <a className="button-link secondary-link" href={HOME_PATH}>
              Back to public landing
            </a>
          </div>
          <p className="workspace-caption">
            Submitting opens your default mail client with the request
            pre-filled to {CONTACT_EMAIL}. Nothing is sent from the browser
            itself, so no fields are persisted on this page.
          </p>
          {submitted ? (
            <SurfaceCard
              as="div"
              className="private-demo-confirmation"
              role="status"
            >
              Thanks — your mail client should now be open. We will reply with
              a calendar invite and private operator credentials.
            </SurfaceCard>
          ) : null}
        </form>
      </SurfacePanel>
    </ProtectedSiteLayout>
  );
}
