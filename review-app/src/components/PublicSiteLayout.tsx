import type { ReactNode } from "react";

import {
  COST_PATH,
  DEMO_PATH,
  HOME_PATH,
  SECURITY_PATH,
  navigateToAppPath,
  type PublicAppRoute,
} from "../appRoutes";

type PublicSiteLayoutProps = {
  activeRoute: PublicAppRoute;
  children: ReactNode;
  className?: string;
};

const TOP_NAV_LINKS: ReadonlyArray<{
  external?: boolean;
  href: string;
  label: string;
  route: PublicAppRoute | "github";
}> = [
  { href: HOME_PATH, label: "Home", route: "home" },
  { href: SECURITY_PATH, label: "Security", route: "security" },
  { href: COST_PATH, label: "Cost", route: "cost" },
  { href: DEMO_PATH, label: "Demo", route: "demo" },
  {
    external: true,
    href: "https://github.com/RyanKelleyCosing",
    label: "GitHub",
    route: "github",
  },
];

export function PublicSiteLayout({
  activeRoute,
  children,
  className,
}: PublicSiteLayoutProps) {
  const rootClassName = className ? `app-shell ${className}` : "app-shell";

  return (
    <div className={rootClassName} data-route-theme={activeRoute}>
      <nav aria-label="Public site navigation" className="public-top-nav">
        <a
          className="public-top-nav-brand"
          href={HOME_PATH}
          onClick={(event) => {
            event.preventDefault();
            navigateToAppPath(HOME_PATH);
          }}
        >
          ryancodes<span className="public-top-nav-brand-accent">.</span>online
        </a>
        <div className="public-top-nav-links">
          {TOP_NAV_LINKS.map((link) => {
            const isActive = link.route === activeRoute;
            const className = isActive
              ? "public-top-nav-link public-top-nav-link-active"
              : "public-top-nav-link";

            if (link.external) {
              return (
                <a
                  className={className}
                  href={link.href}
                  key={link.route}
                  rel="noreferrer"
                  target="_blank"
                >
                  {link.label}
                </a>
              );
            }

            return (
              <a
                aria-current={isActive ? "page" : undefined}
                className={className}
                href={link.href}
                key={link.route}
                onClick={(event) => {
                  event.preventDefault();
                  navigateToAppPath(link.href);
                }}
              >
                {link.label}
              </a>
            );
          })}
        </div>
      </nav>
      {children}
      <footer className="public-site-footer">
        <p>
          Built as a public review surface · all data is sanitized · the real
          operator app lives behind Microsoft Easy Auth.
        </p>
        <p>
          <a
            href="https://github.com/RyanKelleyCosing"
            rel="noreferrer"
            target="_blank"
          >
            Source on GitHub
          </a>
          <span aria-hidden="true"> · </span>
          <a
            href={SECURITY_PATH}
            onClick={(event) => {
              event.preventDefault();
              navigateToAppPath(SECURITY_PATH);
            }}
          >
            Security posture
          </a>
          <span aria-hidden="true"> · </span>
          <a
            href={COST_PATH}
            onClick={(event) => {
              event.preventDefault();
              navigateToAppPath(COST_PATH);
            }}
          >
            Cost transparency
          </a>
        </p>
      </footer>
    </div>
  );
}