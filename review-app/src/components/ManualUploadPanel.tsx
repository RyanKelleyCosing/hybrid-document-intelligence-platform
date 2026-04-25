import { useRef, useState, type ChangeEvent } from "react";

import {
  submitManualPacketUpload,
  type ManualPacketUploadResponse,
} from "../api/manualIntakeApi";
import { SurfaceCard, SurfaceDrawer } from "./SurfacePrimitives";

type ManualUploadPanelProps = {
  reviewerEmail?: string | null;
};

const acceptedFileTypes =
  ".pdf,.png,.jpg,.jpeg,.gif,.webp,.tif,.tiff,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip";

function buildFileSignature(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function mergeFiles(existingFiles: File[], incomingFiles: File[]): File[] {
  const filesBySignature = new Map(
    existingFiles.map((file) => [buildFileSignature(file), file]),
  );

  for (const file of incomingFiles) {
    filesBySignature.set(buildFileSignature(file), file);
  }

  return Array.from(filesBySignature.values()).sort((left, right) =>
    left.name.localeCompare(right.name),
  );
}

function buildDefaultPacketName(files: File[]): string {
  if (files.length === 0) {
    return "";
  }

  if (files.length === 1) {
    return files[0].name;
  }

  const firstFileStem = files[0].name.replace(/\.[^.]+$/, "") || "upload";
  return `${firstFileStem}-batch-${files.length}-files`;
}

function formatFileSize(sizeInBytes: number): string {
  if (sizeInBytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(sizeInBytes / 1024))} KB`;
  }

  return `${(sizeInBytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ManualUploadPanel({ reviewerEmail }: ManualUploadPanelProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const cameraInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [packetName, setPacketName] = useState("");
  const [packetNameWasEdited, setPacketNameWasEdited] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successResponse, setSuccessResponse] =
    useState<ManualPacketUploadResponse | null>(null);

  const applyFiles = (incomingFiles: File[]) => {
    if (incomingFiles.length === 0) {
      return;
    }

    setSelectedFiles((currentFiles) => {
      const mergedFiles = mergeFiles(currentFiles, incomingFiles);
      if (!packetNameWasEdited || currentFiles.length === 0) {
        setPacketName(buildDefaultPacketName(mergedFiles));
      }

      return mergedFiles;
    });
    setErrorMessage(null);
    setSuccessResponse(null);
  };

  const removeFile = (fileToRemove: File) => {
    setSelectedFiles((currentFiles) => {
      const remainingFiles = currentFiles.filter(
        (file) => buildFileSignature(file) !== buildFileSignature(fileToRemove),
      );
      if (!packetNameWasEdited) {
        setPacketName(buildDefaultPacketName(remainingFiles));
      }

      return remainingFiles;
    });
    setSuccessResponse(null);
  };

  const handleFileSelection = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    applyFiles(files);
    event.target.value = "";
  };

  const handleSubmit = async () => {
    setErrorMessage(null);
    setSuccessResponse(null);
    setIsSubmitting(true);

    try {
      const response = await submitManualPacketUpload({
        files: selectedFiles,
        packetName,
        submittedBy: reviewerEmail,
      });
      setSuccessResponse(response);
      setSelectedFiles([]);
      setPacketName("");
      setPacketNameWasEdited(false);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Unable to submit the packet upload.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SurfaceDrawer as="section" className="intake-panel">
      <div className="section-heading section-heading-row">
        <div>
          <h2>Manual intake</h2>
          <p>
            Drag multiple files into one packet and stage them through the same
            protected packet-intake route the backend already persists.
          </p>
        </div>
        <button
          className="secondary-button"
          onClick={() => {
            fileInputRef.current?.click();
          }}
          type="button"
        >
          Browse files
        </button>
        <button
          className="secondary-button"
          onClick={() => {
            cameraInputRef.current?.click();
          }}
          title="Open the device camera to scan a document directly"
          type="button"
        >
          Scan with camera
        </button>
      </div>

      <input
        accept={acceptedFileTypes}
        className="visually-hidden"
        multiple
        onChange={handleFileSelection}
        ref={fileInputRef}
        type="file"
      />

      <input
        accept="image/*"
        capture="environment"
        className="visually-hidden"
        onChange={handleFileSelection}
        ref={cameraInputRef}
        type="file"
      />

      <div
        className={`upload-dropzone ${isDragActive ? "upload-dropzone-active" : ""}`}
        onDragEnter={(event) => {
          event.preventDefault();
          setIsDragActive(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          if (event.currentTarget === event.target) {
            setIsDragActive(false);
          }
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragActive(true);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragActive(false);
          applyFiles(Array.from(event.dataTransfer.files));
        }}
        role="presentation"
      >
        <p className="eyebrow">Multi-file drag and drop</p>
        <h3>Drop a packet here or browse from disk.</h3>
        <p className="upload-dropzone-copy">
          Supported types: PDF, images, Office files, and ZIP archives. Each
          document still goes through the backend 15 MB validation limit.
        </p>
      </div>

      <label className="intake-field">
        <span className="queue-card-section-label">Packet name</span>
        <input
          onChange={(event) => {
            setPacketName(event.target.value);
            setPacketNameWasEdited(true);
          }}
          placeholder="borrower-hardship-batch"
          type="text"
          value={packetName}
        />
      </label>

      {selectedFiles.length === 0 ? (
        <div className="status-panel">
          No files selected yet. Drop a packet or browse to start a staged manual
          upload.
        </div>
      ) : (
        <SurfaceCard as="div" className="selected-files-panel">
          <div className="section-heading section-heading-row compact-section-heading">
            <div>
              <h3>Selected documents</h3>
              <p>{selectedFiles.length} files will be staged into one packet.</p>
            </div>
            <span className="confidence-pill upload-count-pill">
              {selectedFiles.length} docs
            </span>
          </div>

          <ul className="selected-file-list">
            {selectedFiles.map((file) => (
              <li className="selected-file-row" key={buildFileSignature(file)}>
                <div>
                  <strong>{file.name}</strong>
                  <p>{formatFileSize(file.size)}</p>
                </div>
                <button
                  className="ghost-button"
                  onClick={() => {
                    removeFile(file);
                  }}
                  type="button"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </SurfaceCard>
      )}

      {errorMessage ? (
        <p className="status-banner status-error">{errorMessage}</p>
      ) : null}

      {successResponse ? (
        <p className="status-banner status-success">
          Created packet {successResponse.packet_id} with {successResponse.document_count}{" "}
          documents.
        </p>
      ) : null}

      <div className="upload-actions-row">
        <p className="upload-helper-copy">
          The upload is posted to the protected same-origin admin proxy and lands
          in the packet model as a staged scanned-upload batch.
        </p>
        <button
          disabled={isSubmitting || selectedFiles.length === 0}
          onClick={() => {
            void handleSubmit();
          }}
          type="button"
        >
          {isSubmitting ? "Submitting packet..." : "Submit packet"}
        </button>
      </div>
    </SurfaceDrawer>
  );
}