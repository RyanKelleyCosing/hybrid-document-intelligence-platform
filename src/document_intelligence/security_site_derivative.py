"""Extraction helpers for the public security-site derivative package."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from textwrap import dedent

from .repo_boundary import RepoBoundaryManifest

DEFAULT_SECURITY_SITE_DERIVATIVE_OUTPUT = Path(
    "public-derivatives/security-posture-site"
)
_SECURITY_POSTURE_SUBTREE_ARTIFACT_PATH = "public-subtrees/security-posture-platform"
_SECURITY_POSTURE_PUBLIC_REPO_ARTIFACT_PATH = (
  "public-repo-staging/security-posture-platform"
)
_PUBLIC_MANIFEST_REFERENCE = "private repo boundary manifest"
_SECURITY_SITE_DERIVATIVE_ARTIFACT_PATHS = {
  DEFAULT_SECURITY_SITE_DERIVATIVE_OUTPUT.as_posix(),
  _SECURITY_POSTURE_SUBTREE_ARTIFACT_PATH,
  _SECURITY_POSTURE_PUBLIC_REPO_ARTIFACT_PATH,
}

_SECURITY_SITE_SOURCE_DESTINATIONS = {
    "docs/ryancodes-security-online-concept.md": (
        "docs/ryancodes-security-online-concept.md"
    ),
    "review-app/src/api/publicTrafficApi.ts": "src/api/publicTrafficApi.ts",
    "review-app/src/components/SecurityPostureSite.test.tsx": (
        "src/components/SecurityPostureSite.test.tsx"
    ),
    "review-app/src/components/SecurityPostureSite.tsx": (
        "src/components/SecurityPostureSite.tsx"
    ),
    "review-app/src/data/securitySiteContent.ts": (
        "src/data/securitySiteContent.ts"
    ),
}


@dataclass(frozen=True)
class SecuritySiteDerivativeCopy:
    """One manifest-approved file copied into the public derivative package."""

    destination_relative_path: str
    source_relative_path: str


@dataclass(frozen=True)
class SecuritySiteDerivativePlan:
    """Resolved extraction plan for the public security-site derivative."""

    copied_files: tuple[SecuritySiteDerivativeCopy, ...]
    deferred_candidate_sources: tuple[str, ...]


def build_security_site_derivative_plan(
    manifest: RepoBoundaryManifest,
) -> SecuritySiteDerivativePlan:
    """Build the first public derivative plan for the security posture site."""

    candidate_entries = {
        entry.relative_path: entry
        for entry in manifest.entries
        if entry.exposure == "public_derivative_candidate"
    }

    copied_files: list[SecuritySiteDerivativeCopy] = []
    for source_relative_path, destination_relative_path in (
        _SECURITY_SITE_SOURCE_DESTINATIONS.items()
    ):
        if source_relative_path not in candidate_entries:
            raise ValueError(
                "Security-site derivative source path is not classified as a "
                f"public derivative candidate: '{source_relative_path}'."
            )

        copied_files.append(
            SecuritySiteDerivativeCopy(
                destination_relative_path=destination_relative_path,
                source_relative_path=source_relative_path,
            )
        )

    deferred_candidate_sources = tuple(
        sorted(
            relative_path
            for relative_path in candidate_entries
        if relative_path not in _SECURITY_SITE_SOURCE_DESTINATIONS
        and relative_path not in _SECURITY_SITE_DERIVATIVE_ARTIFACT_PATHS
        )
    )
    return SecuritySiteDerivativePlan(
        copied_files=tuple(copied_files),
        deferred_candidate_sources=deferred_candidate_sources,
    )


def extract_security_site_derivative_package(
    repo_root: Path,
    output_directory: Path,
    manifest: RepoBoundaryManifest,
    manifest_path: Path,
) -> SecuritySiteDerivativePlan:
    """Extract the standalone public security-site derivative package."""

    plan = build_security_site_derivative_plan(manifest)
    output_directory.mkdir(parents=True, exist_ok=True)

    for copied_file in plan.copied_files:
        source_path = repo_root / copied_file.source_relative_path
        destination_path = output_directory / copied_file.destination_relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(
            source_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    del manifest_path

    for relative_path, content in _build_scaffold_files(plan=plan).items():
        destination_path = output_directory / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(content, encoding="utf-8")

    return plan


def _build_scaffold_files(
    plan: SecuritySiteDerivativePlan,
) -> dict[str, str]:
    package_name = "ryan-security-posture-site"
    derivative_sources_payload = {
        "package_name": package_name,
    "manifest_reference": _PUBLIC_MANIFEST_REFERENCE,
    "package_purpose": "public_demonstration_only",
    "copied_files": [
      item.destination_relative_path for item in plan.copied_files
    ],
        "generated_files": sorted(
            [
                ".env.example",
                ".gitignore",
                "README.md",
                "index.html",
                "package.json",
                "public/favicon.svg",
                "src/App.tsx",
                "src/main.tsx",
                "src/styles.css",
                "src/test/setup.ts",
                "src/vite-env.d.ts",
                "tsconfig.json",
                "tsconfig.node.json",
                "vite.config.ts",
                "vitest.config.ts",
            ]
        ),
    }

    return {
        ".env.example": _build_env_example(),
        ".gitignore": "dist/\nnode_modules/\ncoverage/\n",
      "README.md": _build_readme(plan=plan),
        "derivative-sources.json": json.dumps(
            derivative_sources_payload,
            indent=2,
        )
        + "\n",
        "index.html": _build_index_html(),
        "package.json": _build_package_json(),
        "public/favicon.svg": _build_favicon_svg(),
        "src/App.tsx": _build_app_tsx(),
        "src/main.tsx": _build_main_tsx(),
        "src/styles.css": _build_styles_css(),
        "src/test/setup.ts": 'import "@testing-library/jest-dom/vitest";\n',
        "src/vite-env.d.ts": '/// <reference types="vite/client" />\n',
        "tsconfig.json": _build_tsconfig_json(),
        "tsconfig.node.json": _build_tsconfig_node_json(),
        "vite.config.ts": _build_vite_config_ts(),
        "vitest.config.ts": _build_vitest_config_ts(),
    }


def _build_readme(
    plan: SecuritySiteDerivativePlan,
) -> str:
    package_file_lines = "\n".join(
    f"- `{item.destination_relative_path}`" for item in plan.copied_files
    )
    return "\n".join(
        [
            "# Ryan Security Posture Site",
            "",
            "This directory is the first real public derivative package extracted from the",
            "private `hybrid-document-intelligence-platform` repo.",
            "",
    "It is intended for public demonstration only. The private repo remains the",
    "live operational source of truth.",
    "",
            "It keeps the employer-facing `#/security` experience in a standalone Vite app,",
            "while the private operator shell, live deployment wiring, SMTP provisioning,",
            "and backend-only routes stay in the private operational codebase.",
            "",
            "## Source Of Truth",
            "",
    "The extraction plan is derived from the private repo boundary manifest.",
    "Machine-specific paths, local settings, and secrets are intentionally excluded",
    "from this public package.",
            "",
            "Rebuild this package from the repo root with:",
            "",
            "```powershell",
            "python scripts/extract_public_security_site_package.py",
            "```",
            "",
    "## Included Package Files",
            "",
    package_file_lines,
            "",
            "## Environment Variables",
            "",
            "- `VITE_PUBLIC_TRAFFIC_API_BASE_URL`: optional base URL for the public-safe",
            "  request-context and aggregate telemetry APIs.",
            "- `VITE_PUBLIC_GITHUB_URL`: optional GitHub profile or repo link.",
            "- `VITE_PUBLIC_LINKEDIN_URL`: optional LinkedIn profile link.",
            "",
            "## Validation",
            "",
            "```powershell",
            "npm install",
            "npm test",
            "npm run build",
            "```",
            "",
        ]
    )


def _build_env_example() -> str:
    return dedent(
        """
        VITE_PUBLIC_TRAFFIC_API_BASE_URL=
        VITE_PUBLIC_GITHUB_URL=https://github.com/RyanKelleyCosing
        VITE_PUBLIC_LINKEDIN_URL=
        """
    ).lstrip()


def _build_package_json() -> str:
    return dedent(
        """
        {
          "name": "ryan-security-posture-site",
          "private": true,
          "version": "0.1.0",
          "type": "module",
          "scripts": {
            "dev": "vite",
            "build": "tsc -b && vite build",
            "preview": "vite preview",
            "test": "vitest run"
          },
          "dependencies": {
            "react": "^19.0.0",
            "react-dom": "^19.0.0"
          },
          "devDependencies": {
            "@testing-library/jest-dom": "^6.6.3",
            "@testing-library/react": "^16.1.0",
            "@types/node": "^22.10.2",
            "@types/react": "^19.0.2",
            "@types/react-dom": "^19.0.2",
            "@vitejs/plugin-react": "^6.0.1",
            "jsdom": "^25.0.1",
            "typescript": "^5.7.2",
            "vite": "^8.0.8",
            "vitest": "^4.1.4"
          }
        }
        """
    ).lstrip()


def _build_tsconfig_json() -> str:
    return dedent(
        """
        {
          "compilerOptions": {
            "target": "ES2021",
            "useDefineForClassFields": true,
            "lib": ["DOM", "DOM.Iterable", "ES2021"],
            "allowJs": false,
            "skipLibCheck": true,
            "esModuleInterop": true,
            "allowSyntheticDefaultImports": true,
            "strict": true,
            "forceConsistentCasingInFileNames": true,
            "module": "ESNext",
            "moduleResolution": "Bundler",
            "resolveJsonModule": true,
            "isolatedModules": true,
            "noEmit": true,
            "jsx": "react-jsx"
          },
          "include": ["src"],
          "references": [{ "path": "./tsconfig.node.json" }]
        }
        """
    ).lstrip()


def _build_tsconfig_node_json() -> str:
    return dedent(
        """
        {
          "compilerOptions": {
            "composite": true,
            "lib": ["ES2021"],
            "module": "ESNext",
            "moduleResolution": "Bundler",
            "skipLibCheck": true,
            "target": "ES2021",
            "types": ["node"],
            "allowSyntheticDefaultImports": true
          },
          "include": ["vite.config.ts", "vitest.config.ts"]
        }
        """
    ).lstrip()


def _build_vite_config_ts() -> str:
    return dedent(
        """
        import react from "@vitejs/plugin-react";
        import { defineConfig } from "vite";

        export default defineConfig({
          plugins: [react()],
          server: {
            port: 5173,
          },
        });
        """
    ).lstrip()


def _build_vitest_config_ts() -> str:
    return dedent(
        """
        import { defineConfig } from "vitest/config";

        export default defineConfig({
          test: {
            environment: "jsdom",
            globals: true,
            include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
            setupFiles: "./src/test/setup.ts",
          },
        });
        """
    ).lstrip()


def _build_index_html() -> str:
    return dedent(
        """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
            <title>Ryan Codes Security Posture</title>
          </head>
          <body>
            <div id="root"></div>
            <script type="module" src="/src/main.tsx"></script>
          </body>
        </html>
        """
    ).lstrip()


def _build_favicon_svg() -> str:
    return dedent(
        """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img"
          aria-label="Document intelligence favicon">
          <rect width="64" height="64" rx="14" fill="#18352f" />
          <path d="M14 18h36v10H14z" fill="#f7f1e7" opacity="0.94" />
          <path d="M14 32h26v10H14z" fill="#bf5b33" />
          <circle cx="49" cy="42" r="7" fill="#f1b44c" />
        </svg>
        """
    ).lstrip()


def _build_app_tsx() -> str:
    return dedent(
        """
        import { SecurityPostureSite } from "./components/SecurityPostureSite";

        function App() {
          return <SecurityPostureSite />;
        }

        export default App;
        """
    ).lstrip()


def _build_main_tsx() -> str:
    return dedent(
        """
        import React from "react";
        import ReactDOM from "react-dom/client";

        import App from "./App";
        import "./styles.css";

        ReactDOM.createRoot(document.getElementById("root")!).render(
          <React.StrictMode>
            <App />
          </React.StrictMode>,
        );
        """
    ).lstrip()


def _build_styles_css() -> str:
    return dedent(
        """
        :root {
          --accent: #bf5b33;
          --accent-strong: #18352f;
          --accent-soft: rgba(191, 91, 51, 0.14);
          --border: rgba(17, 34, 29, 0.12);
          --canvas: rgba(255, 252, 245, 0.72);
          --card: rgba(255, 255, 255, 0.86);
          --ink: #11221d;
          --muted: #5b675f;
          --shadow: 0 22px 48px rgba(44, 37, 24, 0.12);
          background:
            radial-gradient(
              circle at top left,
              rgba(241, 180, 76, 0.18),
              transparent 34%
            ),
            radial-gradient(
              circle at 82% 12%,
              rgba(224, 123, 74, 0.18),
              transparent 26%
            ),
            linear-gradient(180deg, #f7f1e7 0%, #efe5d5 100%);
          color: var(--ink);
          font-family: "Aptos", "Trebuchet MS", sans-serif;
          font-synthesis: none;
          line-height: 1.5;
          text-rendering: optimizeLegibility;
        }

        * {
          box-sizing: border-box;
        }

        body {
          margin: 0;
          min-height: 100vh;
        }

        a {
          color: inherit;
          text-decoration: none;
        }

        a:focus-visible,
        button:focus-visible {
          outline: 3px solid rgba(191, 91, 51, 0.65);
          outline-offset: 4px;
        }

        button {
          border: 0;
          border-radius: 999px;
          background: var(--accent-strong);
          color: #fff9f0;
          cursor: pointer;
          font: inherit;
          padding: 0.8rem 1.1rem;
          transition: opacity 180ms ease, transform 180ms ease;
        }

        button:hover,
        .button-link:hover,
        .profile-link-card:hover {
          opacity: 0.94;
          transform: translateY(-1px);
        }

        .app-shell {
          margin: 0 auto;
          max-width: 1240px;
          padding: 2rem 1.25rem 4rem;
        }

        .section-stack,
        .queue-column {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }

        .hero {
          display: grid;
          gap: 1.5rem;
          grid-template-columns: minmax(0, 2.1fr) minmax(290px, 1fr);
          margin-bottom: 2rem;
        }

        .hero h1 {
          font-size: clamp(2.6rem, 6vw, 4.8rem);
          letter-spacing: -0.06em;
          line-height: 0.95;
          margin: 0.45rem 0 1rem;
          max-width: 10ch;
        }

        .hero-copy,
        .metric-detail,
        .mini-card-copy,
        .operations-list li,
        .workspace-caption,
        .workspace-field-row span,
        .profile-link-card p,
        .section-heading p,
        .timeline-card p {
          color: var(--muted);
        }

        .eyebrow,
        .queue-card-label,
        .workspace-field-row small,
        .workspace-subcard small {
          color: var(--accent);
          font-family: "Cascadia Mono", "Consolas", monospace;
          font-size: 0.82rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }

        .hero-panel,
        .metric-card,
        .surface-card,
        .operations-panel,
        .workspace-card {
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 28px;
          box-shadow: var(--shadow);
        }

        .security-hero-copy,
        .surface-card,
        .operations-panel,
        .workspace-card,
        .metric-card,
        .hero-panel {
          padding: 1.35rem;
        }

        .hero-panel {
          align-self: end;
          display: flex;
          flex-direction: column;
          gap: 0.9rem;
          justify-content: center;
        }

        .hero-panel strong,
        .workspace-subcard strong,
        .metric-card strong,
        .timeline-card h3,
        .surface-card h3 {
          letter-spacing: -0.04em;
          margin: 0;
        }

        .hero-panel > strong {
          font-size: 1.45rem;
        }

        .hero-actions,
        .profile-link-list,
        .chip-list {
          display: flex;
          flex-wrap: wrap;
          gap: 0.75rem;
        }

        .button-link,
        .secondary-button {
          align-items: center;
          border-radius: 999px;
          display: inline-flex;
          font: inherit;
          min-height: 48px;
          padding: 0.75rem 1rem;
          transition: opacity 180ms ease, transform 180ms ease;
        }

        .button-link {
          background: var(--accent-strong);
          color: #fff9f0;
        }

        .secondary-link,
        .secondary-button {
          background: rgba(255, 255, 255, 0.66);
          border: 1px solid rgba(24, 53, 47, 0.16);
          color: var(--accent-strong);
        }

        .chip-list {
          list-style: none;
          margin: 0;
          padding: 0;
        }

        .reason-chip {
          background: rgba(24, 53, 47, 0.08);
          border: 1px solid rgba(24, 53, 47, 0.1);
          border-radius: 999px;
          padding: 0.55rem 0.85rem;
        }

        .security-status-grid,
        .metrics-grid,
        .showcase-grid,
        .security-transparency-grid,
        .workspace-field-list,
        .timeline-list {
          display: grid;
          gap: 1rem;
        }

        .security-status-grid,
        .metrics-grid,
        .security-architecture-grid,
        .security-control-grid,
        .security-faq-grid {
          grid-template-columns: repeat(3, minmax(0, 1fr));
        }

        .security-boundary-grid,
        .security-transparency-grid {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .workspace-subcard {
          background: rgba(255, 255, 255, 0.58);
          border: 1px solid rgba(17, 34, 29, 0.1);
          border-radius: 22px;
          display: flex;
          flex-direction: column;
          gap: 0.3rem;
          padding: 1rem;
        }

        .workspace-subcard span {
          color: var(--muted);
        }

        .profile-link-card {
          background: rgba(255, 255, 255, 0.64);
          border: 1px solid rgba(24, 53, 47, 0.12);
          border-radius: 22px;
          display: flex;
          flex: 1 1 180px;
          flex-direction: column;
          gap: 0.25rem;
          min-width: 0;
          padding: 0.95rem 1rem;
          transition: opacity 180ms ease, transform 180ms ease;
        }

        .metric-card span,
        .profile-link-card strong {
          color: var(--accent);
          font-family: "Cascadia Mono", "Consolas", monospace;
          font-size: 0.82rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }

        .metric-card strong {
          display: block;
          font-size: clamp(2rem, 4vw, 3rem);
          margin-top: 0.45rem;
        }

        .section-heading {
          display: flex;
          flex-direction: column;
          gap: 0.45rem;
        }

        .section-heading h2,
        .surface-card h3 {
          margin: 0;
        }

        .section-heading-row {
          align-items: start;
          display: flex;
          gap: 1rem;
          justify-content: space-between;
        }

        .workbench-layout {
          align-items: start;
          display: grid;
          gap: 1.5rem;
          grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr);
        }

        .simulation-main,
        .public-main,
        .public-aside {
          min-width: 0;
        }

        .workspace-card,
        .surface-card,
        .operations-panel {
          gap: 0.85rem;
        }

        .workspace-caption {
          margin: 0;
        }

        .workspace-field-list {
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        }

        .workspace-field-row {
          background: var(--canvas);
          border: 1px solid rgba(17, 34, 29, 0.08);
          border-radius: 18px;
          display: flex;
          flex-direction: column;
          gap: 0.2rem;
          padding: 0.9rem;
        }

        .workspace-field-row strong {
          font-size: 1rem;
          letter-spacing: -0.02em;
        }

        .security-rule-row {
          border-top: 1px solid rgba(17, 34, 29, 0.08);
          padding-top: 0.75rem;
        }

        .security-rule-row:first-of-type {
          border-top: 0;
          padding-top: 0;
        }

        .operations-list {
          display: grid;
          gap: 0.8rem;
          margin: 0;
          padding-left: 1.25rem;
        }

        .compact-rule-list li::marker {
          color: var(--accent);
        }

        .timeline-card {
          align-items: start;
          background: rgba(255, 255, 255, 0.58);
          border: 1px solid rgba(17, 34, 29, 0.1);
          border-radius: 22px;
          display: grid;
          gap: 0.65rem;
          grid-template-columns: 18px minmax(0, 1fr);
          padding: 1rem;
        }

        .timeline-marker {
          align-self: center;
          background: rgba(191, 91, 51, 0.2);
          border: 3px solid rgba(191, 91, 51, 0.8);
          border-radius: 999px;
          height: 14px;
          width: 14px;
        }

        .timeline-marker[data-state="active"] {
          box-shadow: 0 0 0 8px rgba(191, 91, 51, 0.14);
        }

        @media (max-width: 1024px) {
          .hero,
          .workbench-layout,
          .security-boundary-grid,
          .security-transparency-grid {
            grid-template-columns: 1fr;
          }

          .security-status-grid,
          .metrics-grid,
          .security-architecture-grid,
          .security-control-grid,
          .security-faq-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }

        @media (max-width: 720px) {
          .app-shell {
            padding: 1.25rem 0.9rem 3rem;
          }

          .hero h1 {
            max-width: none;
          }

          .section-heading-row {
            align-items: stretch;
            flex-direction: column;
          }

          .security-status-grid,
          .metrics-grid,
          .security-architecture-grid,
          .security-control-grid,
          .security-faq-grid,
          .workspace-field-list {
            grid-template-columns: 1fr;
          }

          .button-link,
          .secondary-button {
            justify-content: center;
            width: 100%;
          }

          .hero-actions {
            flex-direction: column;
          }
        }
        """
    ).lstrip()
