import { label, statusClass } from "@/lib/labels";

export function StatusPill({ value }: { value: string }) {
  return (
    <span className={`${statusClass(value)} status-badge`} data-status={value}>
      <span aria-hidden="true" className="status-badge__dot" />
      {label(value)}
    </span>
  );
}
