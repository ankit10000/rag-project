import { DocumentDetail } from "@/components/document-detail";
export default async function DocumentPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const requested = Number(query.page);
  const initialPage = Number.isFinite(requested)
    ? Math.max(1, Math.floor(requested))
    : 1;
  return <DocumentDetail id={id} initialPage={initialPage} />;
}
