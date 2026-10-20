type LoadingStateProps = {
  label: string;
};

export function LoadingState({ label }: LoadingStateProps) {
  return (
    <p role="status" data-surface="loading" className="text-[15px] leading-6 text-ink-muted">
      {label}
    </p>
  );
}
