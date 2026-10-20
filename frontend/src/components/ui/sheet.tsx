import * as Dialog from "@radix-ui/react-dialog";
import { type ReactNode, useRef } from "react";
import { Button } from "./button";

type SheetProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCloseAutoFocus?: (event: Event) => void;
  title: string;
  children: ReactNode;
};

export function Sheet({ open, onOpenChange, onCloseAutoFocus, title, children }: SheetProps) {
  const firstLink = useRef<HTMLDivElement>(null);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[rgba(20,24,30,0.4)]" />
        <Dialog.Content
          id="section-sheet"
          className="sheet-shadow fixed inset-y-0 left-0 z-50 flex w-[var(--sidebar-width)] flex-col bg-paper-inset outline-none"
          onCloseAutoFocus={onCloseAutoFocus}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            const link = firstLink.current?.querySelector("a");
            if (link instanceof HTMLAnchorElement) {
              link.focus();
            }
          }}
        >
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-4">
            <div>
              <Dialog.Title className="font-serif text-[22px] leading-[30px] font-semibold text-ink">
                {title}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-[15px] leading-6 text-ink-muted">
                Choose a section.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button>Close</Button>
            </Dialog.Close>
          </div>
          <div ref={firstLink} className="px-3 py-4">
            {children}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
