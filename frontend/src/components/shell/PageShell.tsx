import { useEffect } from "react";
import { PageHeader } from "./PageHeader";

type PageShellProps = {
  title: string;
  scope: string;
  notice: string;
};

export function PageShell({ title, scope, notice }: PageShellProps) {
  useEffect(() => {
    document.title = `${title} · InfraLens`;
  }, [title]);

  return (
    <>
      <PageHeader title={title} scope={scope} />
      <section data-surface="phase" className="operational-panel px-4 py-4">
        <h2 className="font-serif text-[22px] leading-[30px] font-semibold">
          Analytical workspace coming in the next implementation phase
        </h2>
        <p className="mt-3 max-w-[68ch] text-[15px] leading-6">{notice}</p>
      </section>
    </>
  );
}
