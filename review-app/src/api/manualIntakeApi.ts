type ApiErrorPayload = {
  details?: unknown;
  message?: string;
  status?: string;
};

export type ManualPacketUploadResponse = {
  document_count: number;
  packet_id: string;
  packet_name: string;
  source: string;
  source_uri: string;
};

export type ManualPacketUploadInput = {
  files: File[];
  packetName: string;
  submittedBy?: string | null;
};

type ManualPacketDocumentInputPayload = {
  content_type: string;
  document_content_base64: string;
  file_name: string;
};

const defaultApiBaseUrl = import.meta.env.DEV ? "http://localhost:7071/api" : "/api";

const apiBaseUrl =
  import.meta.env.VITE_REVIEW_API_BASE_URL?.replace(/\/$/, "") ||
  defaultApiBaseUrl;

const fallbackContentTypes: Record<string, string> = {
  ".doc": "application/msword",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".gif": "image/gif",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".pdf": "application/pdf",
  ".png": "image/png",
  ".ppt": "application/vnd.ms-powerpoint",
  ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  ".tif": "image/tiff",
  ".tiff": "image/tiff",
  ".webp": "image/webp",
  ".xls": "application/vnd.ms-excel",
  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ".zip": "application/zip",
};

function buildApiUrl(path: string): URL {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const target = `${apiBaseUrl}${normalizedPath}`;

  if (/^https?:\/\//i.test(target)) {
    return new URL(target);
  }

  return new URL(target, window.location.origin);
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T;
  }

  let errorMessage = `Request failed with status ${response.status}`;

  try {
    const payload = (await response.json()) as ApiErrorPayload;
    if (typeof payload.message === "string" && payload.message.length > 0) {
      errorMessage = payload.message;
    } else if (
      typeof payload.details === "string" &&
      payload.details.length > 0
    ) {
      errorMessage = payload.details;
    }
  } catch {
    // Keep the fallback error message.
  }

  throw new Error(errorMessage);
}

function resolveFileContentType(file: File): string {
  if (file.type.trim().length > 0) {
    return file.type;
  }

  const fileName = file.name.toLowerCase();
  const matchedExtension = Object.keys(fallbackContentTypes).find((extension) =>
    fileName.endsWith(extension),
  );

  if (matchedExtension) {
    return fallbackContentTypes[matchedExtension];
  }

  return "application/octet-stream";
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => {
      reject(new Error(`Unable to read '${file.name}'.`));
    };
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error(`Unable to read '${file.name}'.`));
        return;
      }

      const [, base64Payload = ""] = result.split(",", 2);
      if (!base64Payload) {
        reject(new Error(`Unable to encode '${file.name}'.`));
        return;
      }

      resolve(base64Payload);
    };
    reader.readAsDataURL(file);
  });
}

async function buildDocumentPayload(
  file: File,
): Promise<ManualPacketDocumentInputPayload> {
  return {
    content_type: resolveFileContentType(file),
    document_content_base64: await readFileAsBase64(file),
    file_name: file.name,
  };
}

export async function submitManualPacketUpload(
  input: ManualPacketUploadInput,
): Promise<ManualPacketUploadResponse> {
  if (input.files.length === 0) {
    throw new Error("Select at least one document before submitting the packet.");
  }

  const packetName = input.packetName.trim();
  if (!packetName) {
    throw new Error("Packet name is required.");
  }

  const documents = await Promise.all(
    input.files.map((file) => buildDocumentPayload(file)),
  );

  const response = await fetch(buildApiUrl("/packets/manual-intake"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({
      documents,
      packet_name: packetName,
      source: "scanned_upload",
      submitted_by: input.submittedBy ?? undefined,
    }),
  });

  return parseJsonResponse<ManualPacketUploadResponse>(response);
}