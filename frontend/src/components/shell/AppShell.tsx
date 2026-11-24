import { useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { Button } from "../ui/button";
import { Sheet } from "../ui/sheet";
import { currentSection } from "./navigation";
import { PrimaryNav } from "./PrimaryNav";
import { ThemeSwitch } from "./ThemeSwitch";
import { useMinWidth } from "../../lib/useMinWidth";

function Wordmark() {
  return (
    <div className="px-4">
      <p className="font-serif text-[22px] leading-[30px] font-semibold text-ink">InfraLens</p>
      <p className="mt-1 text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">
        Closed historical evaluation
      </p>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const desktop = useMinWidth(1024);
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const sectionsButton = useRef<HTMLButtonElement>(null);
  const section = currentSection(pathname);

  // The sheet exists only in the mobile layout, so it must not reopen after a round trip through desktop.
  if (desktop && open) {
    setOpen(false);
  }

  return (
    <div className="min-h-screen bg-paper text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:bg-paper-raised focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      {/* The page stays at one tree position in both layouts, so crossing the breakpoint keeps its state. */}
      <div className={desktop ? "flex min-h-screen" : "flex min-h-screen flex-col"}>
        {desktop ? (
          <aside className="sticky top-0 flex h-screen w-[var(--sidebar-width)] shrink-0 flex-col border-r border-line bg-paper-inset py-6">
            <Wordmark />
            <div className="mt-8 px-1">
              <PrimaryNav />
            </div>
            <div className="mt-auto px-4 pt-8">
              <ThemeSwitch />
            </div>
          </aside>
        ) : (
          <>
            <header className="flex items-center justify-between gap-4 border-b border-line bg-paper-inset px-4 py-3">
              <div className="min-w-0">
                <p className="font-serif text-[22px] leading-[30px] font-semibold text-ink">InfraLens</p>
                <p className="truncate text-[12px] leading-4 text-ink-muted">{section}</p>
              </div>
              <Button
                ref={sectionsButton}
                aria-haspopup="dialog"
                aria-expanded={open}
                onClick={() => setOpen(true)}
                className="shrink-0"
              >
                Sections
              </Button>
            </header>
            <Sheet
              open={open}
              onOpenChange={setOpen}
              title="Sections"
              onCloseAutoFocus={(event) => {
                event.preventDefault();
                sectionsButton.current?.focus();
              }}
            >
              <PrimaryNav onNavigate={() => setOpen(false)} />
              <div className="mt-8 px-3">
                <ThemeSwitch />
              </div>
            </Sheet>
          </>
        )}
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
