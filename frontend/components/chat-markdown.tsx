"use client";

import { Children, isValidElement, useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";

function plainText(node: ReactNode): string {
  return Children.toArray(node)
    .map((child) => {
      if (typeof child === "string" || typeof child === "number")
        return String(child);
      if (isValidElement<{ children?: ReactNode }>(child))
        return plainText(child.props.children);
      return "";
    })
    .join("");
}

export function CopyText({
  text,
  label = "Copy response",
}: {
  text: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setError(false);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError(true);
    }
  }
  return (
    <span className="inline-flex items-center gap-2">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="size-8 rounded-lg text-muted-foreground"
        onClick={() => void copy()}
        aria-label={copied ? "Copied" : label}
        title={copied ? "Copied" : label}
      >
        {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
      </Button>
      <span className="sr-only" role="status">
        {copied
          ? "Copied to clipboard."
          : error
            ? "Copy unavailable. Select and copy the text."
            : ""}
      </span>
    </span>
  );
}

function CodeBlock({ children }: { children?: ReactNode }) {
  const child = Children.toArray(children).find((item) => isValidElement(item));
  const language = isValidElement<{ className?: string }>(child)
    ? /language-([^\s]+)/.exec(child.props.className ?? "")?.[1]
    : undefined;
  const text = plainText(children).replace(/\n$/, "");
  return (
    <div className="my-4 min-w-0 overflow-hidden rounded-xl border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-1.5 text-xs text-muted-foreground">
        <span>{language ?? "Code"}</span>
        <CopyText text={text} label="Copy code" />
      </div>
      <pre className="m-0 max-w-full overflow-x-auto p-4 text-[13px] leading-6">
        {children}
      </pre>
    </div>
  );
}

export function ChatMarkdown({ content }: { content: string }) {
  return (
    <div className="min-w-0 space-y-4 break-words text-[15px] leading-7 [overflow-wrap:anywhere] [&_strong]:font-semibold [&_p]:leading-7 [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-6 [&_li>p]:my-1 [&_h1]:text-xl [&_h1]:font-semibold [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:font-semibold [&_blockquote]:border-l-2 [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground [&_hr]:my-6">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          code: ({ className, children }) => (
            <code
              className={
                className ??
                "rounded bg-accent px-1 py-0.5 font-mono text-[0.9em]"
              }
            >
              {children}
            </code>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="underline decoration-muted-foreground underline-offset-4 hover:decoration-foreground"
            >
              {children}
            </a>
          ),
          // Model/document Markdown must not initiate remote image requests.
          img: ({ alt }) => (
            <span className="text-muted-foreground">{alt || "Image"}</span>
          ),
          table: ({ children }) => (
            <div className="max-w-full overflow-x-auto rounded-lg border">
              <table className="text-sm">{children}</table>
            </div>
          ),
        }}
      >
        {content}
      </Markdown>
    </div>
  );
}
