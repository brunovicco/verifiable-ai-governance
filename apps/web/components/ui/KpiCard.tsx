import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

type KpiTone = "neutral" | "info" | "success" | "warning" | "danger";

interface KpiCardProps {
  label: string;
  value: ReactNode;
  helper?: ReactNode;
  icon?: IconName;
  tone?: KpiTone;
}

export function KpiCard({ label, value, helper, icon = "dashboard", tone = "neutral" }: KpiCardProps) {
  return (
    <article className={`vg-kpi-card vg-kpi-card--${tone}`}>
      <div className="vg-kpi-card__top">
        <span className="vg-kpi-card__label">{label}</span>
        <span className="vg-kpi-card__icon"><Icon name={icon} size={18} /></span>
      </div>
      <strong className="vg-kpi-card__value">{value}</strong>
      {helper && <span className="vg-kpi-card__helper">{helper}</span>}
    </article>
  );
}
