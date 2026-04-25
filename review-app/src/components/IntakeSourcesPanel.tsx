import { useEffect, useState, type FormEvent } from "react";

import {
  type IntakeSourceConfiguration,
  type IntakeSourceCreateRequest,
  type IntakeSourceExecutionResponse,
  type IntakeSourceKind,
  type IntakeSourceRecord,
  type IntakeSourceUpdateRequest,
} from "../api/intakeSourcesApi";
import {
  StatusBadge,
  SurfaceCard,
  SurfaceDialog,
  SurfaceDrawer,
  SurfacePanel,
} from "./SurfacePrimitives";

type IntakeSourcesPanelProps = {
  deletingSourceId: string | null;
  errorMessage: string | null;
  executionSummary: IntakeSourceExecutionResponse | null;
  executingSourceId: string | null;
  isCreatingSource: boolean;
  isLoading: boolean;
  onCreateSource: (request: IntakeSourceCreateRequest) => Promise<boolean>;
  onDeleteSource: (sourceId: string) => Promise<boolean>;
  onExecuteSource: (sourceId: string) => void;
  onRefresh: () => void;
  onSetSourceEnablement: (
    sourceId: string,
    isEnabled: boolean,
  ) => Promise<boolean>;
  onUpdateSource: (
    sourceId: string,
    request: IntakeSourceUpdateRequest,
  ) => Promise<boolean>;
  savingSourceId: string | null;
  sources: IntakeSourceRecord[];
  successMessage: string | null;
  togglingSourceId: string | null;
};

type SourceFormMode = "create" | "edit";

type SourceDraft = {
  configured_folder_file_pattern: string;
  configured_folder_folder_path: string;
  configured_folder_recursive: boolean;
  credentials_reference: string;
  description: string;
  email_attachment_extension_allowlist: string;
  email_folder_path: string;
  email_mailbox_address: string;
  is_enabled: boolean;
  manual_upload_entry_point_name: string;
  manual_upload_max_documents_per_packet: string;
  owner_email: string;
  partner_auth_scheme: string;
  partner_partner_name: string;
  partner_relative_path: string;
  polling_interval_minutes: string;
  source_id: string;
  source_kind: IntakeSourceKind;
  source_name: string;
  watched_blob_blob_prefix: string;
  watched_blob_container_name: string;
  watched_blob_include_subdirectories: boolean;
  watched_blob_storage_account_name: string;
  watched_sftp_local_user_name: string;
  watched_sftp_path: string;
  watched_sftp_storage_account_name: string;
};

const executableSourceKinds: ReadonlySet<IntakeSourceKind> = new Set<IntakeSourceKind>([
  "configured_folder",
  "email_connector",
  "watched_blob_prefix",
  "watched_sftp_path",
]);

const sourceKindOptions: readonly { label: string; value: IntakeSourceKind }[] = [
  { label: "Watched Azure Blob prefix", value: "watched_blob_prefix" },
  { label: "Watched Azure SFTP path", value: "watched_sftp_path" },
  { label: "Email connector", value: "email_connector" },
  { label: "Partner API feed", value: "partner_api_feed" },
  { label: "Configured folder", value: "configured_folder" },
  { label: "Manual upload entry point", value: "manual_upload" },
];

function toLabel(value: string | null | undefined) {
  if (!value) {
    return "Unknown";
  }

  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "Not available";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function normalizeOptionalText(value: string) {
  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

function parseOptionalInteger(value: string, fieldLabel: string) {
  const normalized = value.trim();
  if (!normalized) {
    return null;
  }

  const parsed = Number.parseInt(normalized, 10);
  if (Number.isNaN(parsed) || parsed < 1) {
    throw new Error(`${fieldLabel} must be a whole number greater than zero.`);
  }

  return parsed;
}

function parseRequiredInteger(value: string, fieldLabel: string) {
  const parsed = parseOptionalInteger(value, fieldLabel);
  if (parsed === null) {
    throw new Error(`${fieldLabel} is required.`);
  }

  return parsed;
}

function parseExtensionAllowlist(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function canExecuteSource(kind: IntakeSourceKind) {
  return executableSourceKinds.has(kind);
}

function getRunUnavailableReason(kind: IntakeSourceKind) {
  if (kind === "manual_upload") {
    return "Manual upload sources stage packets through the intake dropzone instead of the run route.";
  }

  if (kind === "partner_api_feed") {
    return "Partner feeds ingest through the protected partner submission route instead of the run route.";
  }

  return null;
}

function buildConfigurationSummary(configuration: IntakeSourceConfiguration) {
  switch (configuration.source_kind) {
    case "manual_upload":
      return [
        `Entry point: ${configuration.entry_point_name}`,
        `Max documents per packet: ${configuration.max_documents_per_packet}`,
      ];
    case "watched_blob_prefix":
      return [
        `Storage: ${configuration.storage_account_name}`,
        `Container: ${configuration.container_name}`,
        `Prefix: ${configuration.blob_prefix}`,
        configuration.include_subdirectories
          ? "Includes subdirectories"
          : "Top-level blobs only",
      ];
    case "watched_sftp_path":
      return [
        `Storage: ${configuration.storage_account_name}`,
        `SFTP path: ${configuration.sftp_path}`,
        `Local user: ${configuration.local_user_name}`,
      ];
    case "email_connector":
      return [
        `Mailbox: ${configuration.mailbox_address}`,
        `Folder: ${configuration.folder_path}`,
        configuration.attachment_extension_allowlist.length > 0
          ? `Allowlist: ${configuration.attachment_extension_allowlist.join(", ")}`
          : "All attachment extensions allowed",
      ];
    case "partner_api_feed":
      return [
        `Partner: ${configuration.partner_name}`,
        `Relative path: ${configuration.relative_path}`,
        `Auth scheme: ${configuration.auth_scheme}`,
      ];
    case "configured_folder":
      return [
        `Folder: ${configuration.folder_path}`,
        `Pattern: ${configuration.file_pattern}`,
        configuration.recursive ? "Recursive scan enabled" : "Non-recursive scan",
      ];
  }
}

function buildEmptySourceDraft(): SourceDraft {
  return {
    configured_folder_file_pattern: "*.pdf",
    configured_folder_folder_path: "",
    configured_folder_recursive: true,
    credentials_reference: "",
    description: "",
    email_attachment_extension_allowlist: "pdf, tif, tiff, png, jpg",
    email_folder_path: "Inbox/Intake",
    email_mailbox_address: "",
    is_enabled: true,
    manual_upload_entry_point_name: "manual-intake",
    manual_upload_max_documents_per_packet: "25",
    owner_email: "",
    partner_auth_scheme: "api_key",
    partner_partner_name: "",
    partner_relative_path: "/intake",
    polling_interval_minutes: "",
    source_id: "",
    source_kind: "watched_blob_prefix",
    source_name: "",
    watched_blob_blob_prefix: "incoming/",
    watched_blob_container_name: "documents",
    watched_blob_include_subdirectories: true,
    watched_blob_storage_account_name: "",
    watched_sftp_local_user_name: "",
    watched_sftp_path: "/incoming",
    watched_sftp_storage_account_name: "",
  };
}

function buildDraftFromRecord(source: IntakeSourceRecord): SourceDraft {
  const draft = {
    ...buildEmptySourceDraft(),
    credentials_reference: source.credentials_reference || "",
    description: source.description || "",
    is_enabled: source.is_enabled,
    owner_email: source.owner_email || "",
    polling_interval_minutes: source.polling_interval_minutes
      ? String(source.polling_interval_minutes)
      : "",
    source_id: source.source_id,
    source_kind: source.configuration.source_kind,
    source_name: source.source_name,
  };

  switch (source.configuration.source_kind) {
    case "manual_upload":
      return {
        ...draft,
        manual_upload_entry_point_name: source.configuration.entry_point_name,
        manual_upload_max_documents_per_packet: String(
          source.configuration.max_documents_per_packet,
        ),
      };
    case "watched_blob_prefix":
      return {
        ...draft,
        watched_blob_blob_prefix: source.configuration.blob_prefix,
        watched_blob_container_name: source.configuration.container_name,
        watched_blob_include_subdirectories:
          source.configuration.include_subdirectories,
        watched_blob_storage_account_name:
          source.configuration.storage_account_name,
      };
    case "watched_sftp_path":
      return {
        ...draft,
        watched_sftp_local_user_name: source.configuration.local_user_name,
        watched_sftp_path: source.configuration.sftp_path,
        watched_sftp_storage_account_name:
          source.configuration.storage_account_name,
      };
    case "email_connector":
      return {
        ...draft,
        email_attachment_extension_allowlist:
          source.configuration.attachment_extension_allowlist.join(", "),
        email_folder_path: source.configuration.folder_path,
        email_mailbox_address: source.configuration.mailbox_address,
      };
    case "partner_api_feed":
      return {
        ...draft,
        partner_auth_scheme: source.configuration.auth_scheme,
        partner_partner_name: source.configuration.partner_name,
        partner_relative_path: source.configuration.relative_path,
      };
    case "configured_folder":
      return {
        ...draft,
        configured_folder_file_pattern: source.configuration.file_pattern,
        configured_folder_folder_path: source.configuration.folder_path,
        configured_folder_recursive: source.configuration.recursive,
      };
  }
}

function buildConfigurationFromDraft(draft: SourceDraft): IntakeSourceConfiguration {
  switch (draft.source_kind) {
    case "manual_upload":
      return {
        entry_point_name: draft.manual_upload_entry_point_name.trim(),
        max_documents_per_packet: parseRequiredInteger(
          draft.manual_upload_max_documents_per_packet,
          "Max documents per packet",
        ),
        source_kind: "manual_upload",
      };
    case "watched_blob_prefix":
      return {
        blob_prefix: draft.watched_blob_blob_prefix.trim(),
        container_name: draft.watched_blob_container_name.trim(),
        include_subdirectories: draft.watched_blob_include_subdirectories,
        source_kind: "watched_blob_prefix",
        storage_account_name: draft.watched_blob_storage_account_name.trim(),
      };
    case "watched_sftp_path":
      return {
        local_user_name: draft.watched_sftp_local_user_name.trim(),
        sftp_path: draft.watched_sftp_path.trim(),
        source_kind: "watched_sftp_path",
        storage_account_name: draft.watched_sftp_storage_account_name.trim(),
      };
    case "email_connector":
      return {
        attachment_extension_allowlist: parseExtensionAllowlist(
          draft.email_attachment_extension_allowlist,
        ),
        folder_path: draft.email_folder_path.trim(),
        mailbox_address: draft.email_mailbox_address.trim(),
        source_kind: "email_connector",
      };
    case "partner_api_feed":
      return {
        auth_scheme: draft.partner_auth_scheme.trim(),
        partner_name: draft.partner_partner_name.trim(),
        relative_path: draft.partner_relative_path.trim(),
        source_kind: "partner_api_feed",
      };
    case "configured_folder":
      return {
        file_pattern: draft.configured_folder_file_pattern.trim(),
        folder_path: draft.configured_folder_folder_path.trim(),
        recursive: draft.configured_folder_recursive,
        source_kind: "configured_folder",
      };
  }
}

function buildCreateRequest(draft: SourceDraft): IntakeSourceCreateRequest {
  return {
    configuration: buildConfigurationFromDraft(draft),
    credentials_reference: normalizeOptionalText(draft.credentials_reference),
    description: normalizeOptionalText(draft.description),
    is_enabled: draft.is_enabled,
    owner_email: normalizeOptionalText(draft.owner_email),
    polling_interval_minutes: parseOptionalInteger(
      draft.polling_interval_minutes,
      "Polling interval minutes",
    ),
    source_id: normalizeOptionalText(draft.source_id) || undefined,
    source_name: draft.source_name.trim(),
  };
}

function buildUpdateRequest(draft: SourceDraft): IntakeSourceUpdateRequest {
  return {
    configuration: buildConfigurationFromDraft(draft),
    credentials_reference: normalizeOptionalText(draft.credentials_reference),
    description: normalizeOptionalText(draft.description),
    is_enabled: draft.is_enabled,
    owner_email: normalizeOptionalText(draft.owner_email),
    polling_interval_minutes: parseOptionalInteger(
      draft.polling_interval_minutes,
      "Polling interval minutes",
    ),
    source_name: draft.source_name.trim(),
  };
}

type SourceConfigurationFieldsProps = {
  draft: SourceDraft;
  onBooleanChange: (field: keyof SourceDraft, value: boolean) => void;
  onTextChange: (field: keyof SourceDraft, value: string) => void;
};

function SourceConfigurationFields({
  draft,
  onBooleanChange,
  onTextChange,
}: SourceConfigurationFieldsProps) {
  switch (draft.source_kind) {
    case "manual_upload":
      return (
        <>
          <label className="filter-field">
            <span>Entry point name</span>
            <input
              onChange={(event) => {
                onTextChange("manual_upload_entry_point_name", event.target.value);
              }}
              required
              type="text"
              value={draft.manual_upload_entry_point_name}
            />
          </label>
          <label className="filter-field">
            <span>Max documents per packet</span>
            <input
              min="1"
              onChange={(event) => {
                onTextChange(
                  "manual_upload_max_documents_per_packet",
                  event.target.value,
                );
              }}
              required
              step="1"
              type="number"
              value={draft.manual_upload_max_documents_per_packet}
            />
          </label>
        </>
      );
    case "watched_blob_prefix":
      return (
        <>
          <label className="filter-field">
            <span>Storage account</span>
            <input
              onChange={(event) => {
                onTextChange("watched_blob_storage_account_name", event.target.value);
              }}
              required
              type="text"
              value={draft.watched_blob_storage_account_name}
            />
          </label>
          <label className="filter-field">
            <span>Container</span>
            <input
              onChange={(event) => {
                onTextChange("watched_blob_container_name", event.target.value);
              }}
              required
              type="text"
              value={draft.watched_blob_container_name}
            />
          </label>
          <label className="filter-field">
            <span>Blob prefix</span>
            <input
              onChange={(event) => {
                onTextChange("watched_blob_blob_prefix", event.target.value);
              }}
              required
              type="text"
              value={draft.watched_blob_blob_prefix}
            />
          </label>
          <label className="filter-field">
            <span>Include subdirectories</span>
            <select
              onChange={(event) => {
                onBooleanChange(
                  "watched_blob_include_subdirectories",
                  event.target.value === "true",
                );
              }}
              value={String(draft.watched_blob_include_subdirectories)}
            >
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          </label>
        </>
      );
    case "watched_sftp_path":
      return (
        <>
          <label className="filter-field">
            <span>Storage account</span>
            <input
              onChange={(event) => {
                onTextChange("watched_sftp_storage_account_name", event.target.value);
              }}
              required
              type="text"
              value={draft.watched_sftp_storage_account_name}
            />
          </label>
          <label className="filter-field">
            <span>Local user name</span>
            <input
              onChange={(event) => {
                onTextChange("watched_sftp_local_user_name", event.target.value);
              }}
              required
              type="text"
              value={draft.watched_sftp_local_user_name}
            />
          </label>
          <label className="filter-field source-form-grid-span-2">
            <span>SFTP path</span>
            <input
              onChange={(event) => {
                onTextChange("watched_sftp_path", event.target.value);
              }}
              required
              type="text"
              value={draft.watched_sftp_path}
            />
          </label>
        </>
      );
    case "email_connector":
      return (
        <>
          <label className="filter-field">
            <span>Mailbox address</span>
            <input
              onChange={(event) => {
                onTextChange("email_mailbox_address", event.target.value);
              }}
              required
              type="email"
              value={draft.email_mailbox_address}
            />
          </label>
          <label className="filter-field">
            <span>Folder path</span>
            <input
              onChange={(event) => {
                onTextChange("email_folder_path", event.target.value);
              }}
              required
              type="text"
              value={draft.email_folder_path}
            />
          </label>
          <label className="filter-field source-form-grid-span-2">
            <span>Attachment allowlist</span>
            <textarea
              onChange={(event) => {
                onTextChange(
                  "email_attachment_extension_allowlist",
                  event.target.value,
                );
              }}
              placeholder="pdf, tif, tiff"
              value={draft.email_attachment_extension_allowlist}
            />
          </label>
        </>
      );
    case "partner_api_feed":
      return (
        <>
          <label className="filter-field">
            <span>Partner name</span>
            <input
              onChange={(event) => {
                onTextChange("partner_partner_name", event.target.value);
              }}
              required
              type="text"
              value={draft.partner_partner_name}
            />
          </label>
          <label className="filter-field">
            <span>Auth scheme</span>
            <input
              onChange={(event) => {
                onTextChange("partner_auth_scheme", event.target.value);
              }}
              required
              type="text"
              value={draft.partner_auth_scheme}
            />
          </label>
          <label className="filter-field source-form-grid-span-2">
            <span>Relative path</span>
            <input
              onChange={(event) => {
                onTextChange("partner_relative_path", event.target.value);
              }}
              required
              type="text"
              value={draft.partner_relative_path}
            />
          </label>
        </>
      );
    case "configured_folder":
      return (
        <>
          <label className="filter-field source-form-grid-span-2">
            <span>Folder path</span>
            <input
              onChange={(event) => {
                onTextChange("configured_folder_folder_path", event.target.value);
              }}
              required
              type="text"
              value={draft.configured_folder_folder_path}
            />
          </label>
          <label className="filter-field">
            <span>File pattern</span>
            <input
              onChange={(event) => {
                onTextChange("configured_folder_file_pattern", event.target.value);
              }}
              required
              type="text"
              value={draft.configured_folder_file_pattern}
            />
          </label>
          <label className="filter-field">
            <span>Recursive scan</span>
            <select
              onChange={(event) => {
                onBooleanChange(
                  "configured_folder_recursive",
                  event.target.value === "true",
                );
              }}
              value={String(draft.configured_folder_recursive)}
            >
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          </label>
        </>
      );
  }
}

export function IntakeSourcesPanel({
  deletingSourceId,
  errorMessage,
  executionSummary,
  executingSourceId,
  isCreatingSource,
  isLoading,
  onCreateSource,
  onDeleteSource,
  onExecuteSource,
  onRefresh,
  onSetSourceEnablement,
  onUpdateSource,
  savingSourceId,
  sources,
  successMessage,
  togglingSourceId,
}: IntakeSourcesPanelProps) {
  const [formMode, setFormMode] = useState<SourceFormMode>("create");
  const [draft, setDraft] = useState<SourceDraft>(() => buildEmptySourceDraft());
  const [formValidationMessage, setFormValidationMessage] = useState<string | null>(
    null,
  );
  const [sourcePendingDeletion, setSourcePendingDeletion] =
    useState<IntakeSourceRecord | null>(null);

  useEffect(() => {
    if (formMode !== "edit") {
      return;
    }

    const editingSourceStillExists = sources.some(
      (source) => source.source_id === draft.source_id,
    );
    if (!editingSourceStillExists) {
      setFormMode("create");
      setDraft(buildEmptySourceDraft());
      setFormValidationMessage(null);
    }
  }, [draft.source_id, formMode, sources]);

  useEffect(() => {
    if (!sourcePendingDeletion) {
      return;
    }

    const pendingSourceStillExists = sources.some(
      (source) => source.source_id === sourcePendingDeletion.source_id,
    );
    if (!pendingSourceStillExists) {
      setSourcePendingDeletion(null);
    }
  }, [sourcePendingDeletion, sources]);

  const isFormPending =
    isCreatingSource || (formMode === "edit" && savingSourceId === draft.source_id);

  const updateDraftField = <K extends keyof SourceDraft>(
    field: K,
    value: SourceDraft[K],
  ) => {
    setDraft((currentDraft) => ({
      ...currentDraft,
      [field]: value,
    }));
  };

  const resetForm = () => {
    setFormMode("create");
    setDraft(buildEmptySourceDraft());
    setFormValidationMessage(null);
  };

  const beginEditing = (source: IntakeSourceRecord) => {
    setFormMode("edit");
    setDraft(buildDraftFromRecord(source));
    setFormValidationMessage(null);
  };

  const requestDeleteSource = (source: IntakeSourceRecord) => {
    setSourcePendingDeletion(source);
  };

  const cancelDeleteSource = () => {
    setSourcePendingDeletion(null);
  };

  const submitSourceDefinition = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormValidationMessage(null);

    try {
      if (formMode === "create") {
        const created = await onCreateSource(buildCreateRequest(draft));
        if (created) {
          resetForm();
        }
        return;
      }

      await onUpdateSource(draft.source_id, buildUpdateRequest(draft));
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to prepare the intake source definition.";
      setFormValidationMessage(message);
    }
  };

  const toggleEnablement = async (source: IntakeSourceRecord) => {
    await onSetSourceEnablement(source.source_id, !source.is_enabled);
  };

  const deleteSourceDefinition = async () => {
    if (!sourcePendingDeletion) {
      return;
    }

    const deleted = await onDeleteSource(sourcePendingDeletion.source_id);
    if (
      deleted &&
      formMode === "edit" &&
      draft.source_id === sourcePendingDeletion.source_id
    ) {
      resetForm();
    }

    if (deleted) {
      setSourcePendingDeletion(null);
    }
  };

  return (
    <SurfacePanel className="queue-surface">
      <div className="section-heading section-heading-row">
        <div>
          <h2>Managed intake sources</h2>
          <p>
            Review the configured Blob, SFTP, mailbox, partner-feed, and folder
            sources, then trigger or maintain source definitions without dropping
            into scripts.
          </p>
        </div>
        <button className="ghost-button" disabled={isLoading} onClick={onRefresh} type="button">
          Refresh sources
        </button>
      </div>

      {successMessage ? (
        <div className="status-banner status-success">{successMessage}</div>
      ) : null}

      {executionSummary ? (
        <div className="status-banner status-success">
          {executionSummary.source_name} ran at {formatDateTime(executionSummary.executed_at_utc)}.
          Seen {executionSummary.seen_blob_count}, processed {executionSummary.processed_blob_count}, reused {executionSummary.reused_packet_count}, failed {executionSummary.failed_blob_count}.
        </div>
      ) : null}

      {formValidationMessage ? (
        <div className="status-banner status-error">{formValidationMessage}</div>
      ) : null}

      {!formValidationMessage && errorMessage ? (
        <div className="status-banner status-error">{errorMessage}</div>
      ) : null}

      {sourcePendingDeletion ? (
        <SurfaceDialog
          actions={
            <div className="surface-dialog-button-group">
              <button className="ghost-button" onClick={cancelDeleteSource} type="button">
                Cancel
              </button>
              <button
                className="danger-button"
                disabled={deletingSourceId === sourcePendingDeletion.source_id}
                onClick={() => {
                  void deleteSourceDefinition();
                }}
                type="button"
              >
                {deletingSourceId === sourcePendingDeletion.source_id
                  ? "Deleting..."
                  : "Delete source"}
              </button>
            </div>
          }
          badge={<StatusBadge tone="danger">Delete source definition</StatusBadge>}
          className="source-delete-dialog"
          description="Existing packet lineage remains intact, but the managed source definition stops future runs immediately once deleted."
          title={sourcePendingDeletion.source_name}
        >
          <dl className="detail-list compact-detail-list">
            <div>
              <dt>Source id</dt>
              <dd>{sourcePendingDeletion.source_id}</dd>
            </div>
            <div>
              <dt>Kind</dt>
              <dd>{toLabel(sourcePendingDeletion.configuration.source_kind)}</dd>
            </div>
            <div>
              <dt>Owner</dt>
              <dd>{sourcePendingDeletion.owner_email || "Unassigned"}</dd>
            </div>
            <div>
              <dt>Delete impact</dt>
              <dd>Existing packet lineage stays available in the workspace.</dd>
            </div>
          </dl>
        </SurfaceDialog>
      ) : null}

      <SurfaceDrawer as="article" className="source-form-card">
        <div className="section-heading section-heading-row compact-section-heading">
          <div>
            <h3>
              {formMode === "edit"
                ? `Edit source ${draft.source_name || draft.source_id}`
                : "Create source definition"}
            </h3>
            <p>
              Durable source definitions now live in Azure SQL and feed the same protected
              operator APIs that the workspace shell uses.
            </p>
          </div>
          {formMode === "edit" ? (
            <button className="ghost-button" onClick={resetForm} type="button">
              Create new definition
            </button>
          ) : null}
        </div>

        <form className="source-form-shell" onSubmit={submitSourceDefinition}>
          <div className="source-form-grid">
            <label className="filter-field">
              <span>Source id</span>
              <input
                disabled={formMode === "edit"}
                onChange={(event) => {
                  updateDraftField("source_id", event.target.value);
                }}
                placeholder="src_ops_blob"
                type="text"
                value={draft.source_id}
              />
            </label>
            <label className="filter-field">
              <span>Source name</span>
              <input
                onChange={(event) => {
                  updateDraftField("source_name", event.target.value);
                }}
                required
                type="text"
                value={draft.source_name}
              />
            </label>
            <label className="filter-field source-form-grid-span-2">
              <span>Description</span>
              <textarea
                onChange={(event) => {
                  updateDraftField("description", event.target.value);
                }}
                placeholder="What this source stages and who owns it."
                value={draft.description}
              />
            </label>
            <label className="filter-field">
              <span>Source kind</span>
              <select
                onChange={(event) => {
                  updateDraftField("source_kind", event.target.value as IntakeSourceKind);
                }}
                value={draft.source_kind}
              >
                {sourceKindOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="filter-field">
              <span>Status</span>
              <select
                onChange={(event) => {
                  updateDraftField("is_enabled", event.target.value === "true");
                }}
                value={String(draft.is_enabled)}
              >
                <option value="true">Enabled</option>
                <option value="false">Paused</option>
              </select>
            </label>
            <label className="filter-field">
              <span>Owner email</span>
              <input
                onChange={(event) => {
                  updateDraftField("owner_email", event.target.value);
                }}
                placeholder="ops@example.com"
                type="email"
                value={draft.owner_email}
              />
            </label>
            <label className="filter-field">
              <span>Polling interval minutes</span>
              <input
                min="1"
                onChange={(event) => {
                  updateDraftField("polling_interval_minutes", event.target.value);
                }}
                placeholder="15"
                step="1"
                type="number"
                value={draft.polling_interval_minutes}
              />
            </label>
            <label className="filter-field source-form-grid-span-2">
              <span>Credentials reference</span>
              <input
                onChange={(event) => {
                  updateDraftField("credentials_reference", event.target.value);
                }}
                placeholder="kv://storage/ops-watcher"
                type="text"
                value={draft.credentials_reference}
              />
            </label>
          </div>

          <div className="section-heading compact-section-heading">
            <h3>Configuration</h3>
            <p>
              Only the fields for the selected source kind are sent to the Functions API.
            </p>
          </div>

          <div className="source-form-grid">
            <SourceConfigurationFields
              draft={draft}
              onBooleanChange={(field, value) => {
                updateDraftField(field, value as SourceDraft[typeof field]);
              }}
              onTextChange={(field, value) => {
                updateDraftField(field, value as SourceDraft[typeof field]);
              }}
            />
          </div>

          <p className="workspace-copy">
            Leave source id blank to let the API generate a durable identifier for new sources.
          </p>

          <div className="queue-filter-actions">
            <button disabled={isFormPending} type="submit">
              {formMode === "edit"
                ? savingSourceId === draft.source_id
                  ? "Saving source..."
                  : "Save source"
                : isCreatingSource
                  ? "Creating source..."
                  : "Create source"}
            </button>
            <button className="ghost-button" onClick={resetForm} type="button">
              Reset form
            </button>
          </div>
        </form>
      </SurfaceDrawer>

      {isLoading ? (
        <div className="status-panel">Loading intake sources from the protected Functions API...</div>
      ) : sources.length === 0 ? (
        <div className="status-panel">No intake sources are configured yet.</div>
      ) : (
        <div className="source-monitor-grid">
          {sources.map((source) => {
            const configurationSummary = buildConfigurationSummary(source.configuration);
            const latestExecutionMatches = executionSummary?.source_id === source.source_id;
            const runUnavailableReason = getRunUnavailableReason(
              source.configuration.source_kind,
            );
            const isRunDisabled =
              executingSourceId === source.source_id ||
              !source.is_enabled ||
              !canExecuteSource(source.configuration.source_kind);

            return (
              <SurfaceCard key={source.source_id}>
                <div className="queue-card-header">
                  <div className="queue-card-heading">
                    <span className="queue-card-label">
                      {source.is_enabled ? "Enabled" : "Paused"}
                    </span>
                    <h3>{source.source_name}</h3>
                  </div>
                  <span className="workspace-inline-chip">
                    {toLabel(source.configuration.source_kind)}
                  </span>
                </div>

                {source.description ? (
                  <p className="workspace-copy">{source.description}</p>
                ) : null}

                <dl className="detail-list compact-detail-list">
                  <div>
                    <dt>Owner</dt>
                    <dd>{source.owner_email || "Unassigned"}</dd>
                  </div>
                  <div>
                    <dt>Polling</dt>
                    <dd>
                      {source.polling_interval_minutes
                        ? `${source.polling_interval_minutes} minutes`
                        : "Manual run"}
                    </dd>
                  </div>
                  <div>
                    <dt>Last success</dt>
                    <dd>{formatDateTime(source.last_success_at_utc)}</dd>
                  </div>
                  <div>
                    <dt>Last seen</dt>
                    <dd>{formatDateTime(source.last_seen_at_utc)}</dd>
                  </div>
                </dl>

                <ul className="operations-list compact-rule-list">
                  {configurationSummary.map((summaryLine) => (
                    <li key={`${source.source_id}:${summaryLine}`}>{summaryLine}</li>
                  ))}
                </ul>

                {source.credentials_reference ? (
                  <p className="workspace-copy">
                    Credentials reference: {source.credentials_reference}
                  </p>
                ) : null}

                {source.last_error_message ? (
                  <div className="status-banner status-error">
                    Last error at {formatDateTime(source.last_error_at_utc)}: {source.last_error_message}
                  </div>
                ) : null}

                {latestExecutionMatches && executionSummary ? (
                  <div className="status-panel workspace-status-panel">
                    <p className="workspace-copy">
                      Latest run created or reused {executionSummary.packet_results.length} packet entries.
                    </p>
                    {executionSummary.packet_results.length > 0 ? (
                      <ul className="chip-list stack-chip-list">
                        {executionSummary.packet_results.slice(0, 3).map((packetResult) => (
                          <li className="match-pill" key={packetResult.packet_id}>
                            {packetResult.packet_name} · {toLabel(packetResult.status)}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : null}

                <div className="queue-card-footer">
                  <div>
                    <span className="queue-card-label">Source id</span>
                    <p className="workspace-copy">{source.source_id}</p>
                  </div>
                  <div className="queue-card-actions">
                    <button
                      className="ghost-button"
                      disabled={savingSourceId === source.source_id || deletingSourceId === source.source_id}
                      onClick={() => {
                        beginEditing(source);
                      }}
                      type="button"
                    >
                      Edit
                    </button>
                    <button
                      className="secondary-button"
                      disabled={togglingSourceId === source.source_id || deletingSourceId === source.source_id}
                      onClick={() => {
                        void toggleEnablement(source);
                      }}
                      type="button"
                    >
                      {togglingSourceId === source.source_id
                        ? source.is_enabled
                          ? "Pausing..."
                          : "Resuming..."
                        : source.is_enabled
                          ? "Pause"
                          : "Resume"}
                    </button>
                    <button
                      disabled={isRunDisabled}
                      onClick={() => {
                        onExecuteSource(source.source_id);
                      }}
                      type="button"
                    >
                      {executingSourceId === source.source_id ? "Running source..." : "Run source"}
                    </button>
                    <button
                      className="danger-button"
                      disabled={deletingSourceId === source.source_id}
                      onClick={() => {
                        requestDeleteSource(source);
                      }}
                      type="button"
                    >
                      {deletingSourceId === source.source_id ? "Deleting..." : "Delete"}
                    </button>
                  </div>
                </div>

                {runUnavailableReason ? (
                  <p className="queue-card-note">{runUnavailableReason}</p>
                ) : null}
              </SurfaceCard>
            );
          })}
        </div>
      )}
    </SurfacePanel>
  );
}