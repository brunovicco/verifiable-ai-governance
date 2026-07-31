import { label, statusClass } from "@/lib/labels";

export function StatusPill({ value }: { value: string }) {
  return <span className={statusClass(value)}>{label(value)}</span>;
}
