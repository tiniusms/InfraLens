import { NavLink } from "react-router-dom";
import { cn } from "../../lib/cn";
import { NAV_ITEMS } from "./navigation";

type PrimaryNavProps = {
  onNavigate?: () => void;
};

export function PrimaryNav({ onNavigate }: PrimaryNavProps) {
  return (
    <nav aria-label="Primary">
      <ul className="flex flex-col gap-1">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "block border-l-2 px-3 py-2 text-[15px] leading-6",
                  isActive
                    ? "border-series-actual font-semibold text-ink"
                    : "border-transparent text-ink-muted",
                )
              }
            >
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
