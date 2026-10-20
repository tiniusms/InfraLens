import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  scope: string;
  children?: ReactNode;
};

export function PageHeader({ title, scope, children }: PageHeaderProps) {
  return (
    <header className="mb-8">
      <h1 className="font-serif text-[22px] leading-[30px] font-semibold text-ink">{title}</h1>
      <p className="mt-2 max-w-[68ch] text-[15px] leading-6 text-ink-muted">{scope}</p>
      {children}
    </header>
  );
}
