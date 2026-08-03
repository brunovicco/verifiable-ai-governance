import type { ReactNode } from "react";

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    <header className="vg-page-header">
      <div className="vg-page-header__copy">
        {eyebrow && <p className="vg-eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <div className="vg-page-header__description">{description}</div>}
      </div>
      {actions && <div className="vg-page-header__actions">{actions}</div>}
    </header>
  );
}
