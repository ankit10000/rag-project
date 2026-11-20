import { ChatWorkspace } from "@/components/chat-workspace";
export default async function Chat({
  searchParams,
}: {
  searchParams: Promise<{ conversation?: string }>;
}) {
  const p = await searchParams;
  return (
    <ChatWorkspace key={p.conversation ?? "new"} initialId={p.conversation} />
  );
}
