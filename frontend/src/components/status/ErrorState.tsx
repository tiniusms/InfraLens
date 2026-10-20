type ErrorStateProps = {
  title: string;
  message: string;
};

export function ErrorState({ title, message }: ErrorStateProps) {
  return (
    <section role="alert" data-surface="operational" className="operational-panel px-4 py-4">
      <h2 className="text-[16px] leading-6 font-semibold">{title}</h2>
      <p className="mt-2 text-[15px] leading-6">{message}</p>
    </section>
  );
}
