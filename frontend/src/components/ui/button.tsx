import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement>;

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "rounded-[2px] border border-line bg-paper-raised px-3 py-2 text-[15px] leading-6 text-ink",
        className,
      )}
      {...props}
    />
  );
});
