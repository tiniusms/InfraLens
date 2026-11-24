import { matchPath } from "react-router-dom";

export const NAV_ITEMS = [
  { to: "/", label: "Overview", end: true },
  { to: "/electricity", label: "Electricity Intelligence", end: true },
  { to: "/finance", label: "Financial Scenario Studio", end: true },
  { to: "/pjm", label: "PJM Infrastructure Explorer", end: true },
] as const;

export function currentSection(pathname: string): string {
  const match = NAV_ITEMS.find((item) => matchPath({ path: item.to, end: item.end }, pathname));
  return match?.label ?? "Page not found";
}
