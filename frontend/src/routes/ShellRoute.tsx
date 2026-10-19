import { Outlet } from "react-router-dom";
import { AppShell } from "../components/shell/AppShell";

export function ShellRoute() {
  return (
    <AppShell>
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[var(--content-max)] px-4 py-6 outline-none lg:px-8 lg:py-8">
        <Outlet />
      </main>
    </AppShell>
  );
}
