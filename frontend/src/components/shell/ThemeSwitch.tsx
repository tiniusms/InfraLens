import { Button } from "../ui/button";
import { useTheme } from "./useTheme";

export function ThemeSwitch() {
  const { theme, setTheme } = useTheme();
  return (
    <div className="flex gap-2" role="group" aria-label="Appearance">
      {(["light", "dark"] as const).map((name) => (
        <Button
          key={name}
          aria-pressed={theme === name}
          onClick={() => setTheme(name)}
          className="text-[12px] leading-4 font-semibold tracking-[0.04em] uppercase"
        >
          {name}
        </Button>
      ))}
    </div>
  );
}
