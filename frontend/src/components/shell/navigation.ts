export const NAV_ITEMS = [
  { to: "/", label: "Overview", end: true },
  { to: "/electricity", label: "Electricity Intelligence", end: false },
  { to: "/finance", label: "Financial Scenario Studio", end: false },
  { to: "/pjm", label: "PJM Infrastructure Explorer", end: false },
] as const;

export function currentSection(pathname: string): string {
  const match = NAV_ITEMS.find((item) => (item.end ? pathname === "/" : pathname.startsWith(item.to)));
  return match?.label ?? "Overview";
}
