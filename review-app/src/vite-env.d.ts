/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_MODE?: string;
  readonly VITE_PUBLIC_CONTACT_EMAIL?: string;
  readonly VITE_PUBLIC_GITHUB_URL?: string;
  readonly VITE_PUBLIC_LINKEDIN_URL?: string;
  readonly VITE_PUBLIC_SECURITY_ENRICHMENT_ENABLED?: string;
  readonly VITE_PUBLIC_SECURITY_GLOBE_ENABLED?: string;
  readonly VITE_PUBLIC_TRAFFIC_API_BASE_URL?: string;
  readonly VITE_REVIEW_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}