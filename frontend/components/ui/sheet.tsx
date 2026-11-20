"use client";
import * as React from "react";
import * as Primitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
export const Sheet = Primitive.Root;
export const SheetTrigger = Primitive.Trigger;
export const SheetClose = Primitive.Close;
export const SheetTitle = Primitive.Title;
export const SheetDescription = Primitive.Description;
export function SheetContent({
  className,
  children,
  side = "right",
  ...props
}: React.ComponentProps<typeof Primitive.Content> & {
  side?: "left" | "right";
}) {
  return (
    <Primitive.Portal>
      <Primitive.Overlay className="fixed inset-0 z-50 bg-black/65 backdrop-blur-sm" />
      <Primitive.Content
        className={cn(
          "fixed inset-y-0 z-50 flex w-[min(85vw,320px)] flex-col border bg-sidebar shadow-2xl focus:outline-none",
          side === "left" ? "left-0 border-r" : "right-0 border-l",
          className,
        )}
        {...props}
      >
        {children}
        <Primitive.Close
          className="absolute right-3 top-4 rounded-lg p-2 text-muted-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
          aria-label="Close navigation"
        >
          <X className="size-5" />
        </Primitive.Close>
      </Primitive.Content>
    </Primitive.Portal>
  );
}
export function SheetHeader({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div className={cn("flex flex-col gap-2 p-5", className)} {...props} />
  );
}
export function SheetFooter({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return <div className={cn("mt-auto flex gap-2 p-5", className)} {...props} />;
}
