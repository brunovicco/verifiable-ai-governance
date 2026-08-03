import type { ReactNode, SVGProps } from "react";

export type IconName =
  | "dashboard"
  | "portfolio"
  | "monitoring"
  | "documentation"
  | "layers"
  | "plus"
  | "menu"
  | "close"
  | "search"
  | "shield"
  | "arrow-right"
  | "alert"
  | "check"
  | "clock";

type IconProps = SVGProps<SVGSVGElement> & {
  name: IconName;
  size?: number;
};

const paths: Record<IconName, ReactNode> = {
  dashboard: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
  portfolio: <><path d="M3 7.5h18v11.25A2.25 2.25 0 0 1 18.75 21H5.25A2.25 2.25 0 0 1 3 18.75Z" /><path d="M8 7.5V5.25A2.25 2.25 0 0 1 10.25 3h3.5A2.25 2.25 0 0 1 16 5.25V7.5" /><path d="M3 12h18M10 12v2h4v-2" /></>,
  monitoring: <><path d="M4 19V9m5 10V5m5 14v-7m5 7V3" /><path d="M2.5 21h19" /></>,
  documentation: <><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v5h5M9 12h6M9 16h6" /></>,
  layers: <><path d="m12 3 9 5-9 5-9-5Z" /><path d="m3 13 9 5 9-5" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
  shield: <><path d="M12 3 20 6v5c0 5-3.4 8.4-8 10-4.6-1.6-8-5-8-10V6Z" /><path d="m9 12 2 2 4-4" /></>,
  "arrow-right": <path d="M5 12h14m-5-5 5 5-5 5" />,
  alert: <><path d="M12 3 2.8 20h18.4Z" /><path d="M12 9v5m0 3h.01" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
};

export function Icon({ name, size = 20, ...props }: IconProps) {
  return (
    <svg aria-hidden="true" fill="none" height={size} viewBox="0 0 24 24" width={size} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" {...props}>
      {paths[name]}
    </svg>
  );
}
