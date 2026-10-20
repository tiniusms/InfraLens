type UnavailableStateProps = {
  title: string;
  message: string;
};

export function UnavailableState({ title, message }: UnavailableStateProps) {
  return (
    <section data-surface="unavailable" className="unavailable-panel px-4 py-4">
      <h2 className="text-[16px] leading-6 font-semibold">{title}</h2>
      <p className="mt-2 text-[15px] leading-6">{message}</p>
    </section>
  );
}
