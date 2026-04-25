import type { ReactNode } from "react";

import { ProductShellHeader } from "./ProductShellHeader";

type ProtectedSiteLayoutProps = {
  children: ReactNode;
  navigation: ReactNode;
  operatorEmail?: string | null;
};

export function ProtectedSiteLayout({
  children,
  navigation,
  operatorEmail,
}: ProtectedSiteLayoutProps) {
  return (
    <div className="app-shell" data-route-theme="admin">
      <ProductShellHeader
        activeRoute="admin"
        mode="live"
        operatorEmail={operatorEmail}
      />
      <div className="admin-shell-layout">
        {navigation}
        <div className="admin-main-column">{children}</div>
      </div>
    </div>
  );
}