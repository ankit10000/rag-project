import type {
  User,
  Document,
  Job,
  Conversation,
  ConversationDetail,
  ChatResponse,
  MemoryList,
  Upload,
} from "./api-types";
export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string) {
    super(
      status === 401
        ? "Your session has expired. Please sign in."
        : status === 403
          ? "You do not have permission to do that."
          : status === 404
            ? "This item is unavailable or you do not have access."
            : status === 409
              ? "This item changed. Refresh and try again."
              : status === 413
                ? "This file is too large."
                : status === 422
                  ? "Check your input and try again."
                  : status === 429
                    ? "Too many requests. Please try again shortly."
                    : status === 504
                      ? "The request took too long. Check activity before retrying."
                      : "We could not complete the request. Please try again.",
    );
    this.status = status;
    this.code = code;
  }
}
export function csrfToken(): string {
  if (typeof document === "undefined") return "";
  return decodeURIComponent(
    document.cookie
      .split("; ")
      .find((x) => x.startsWith("rag_csrf="))
      ?.split("=")
      .slice(1)
      .join("=") ?? "",
  );
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  const method = (options.method ?? "GET").toUpperCase();
  if (!["GET", "HEAD"].includes(method)) {
    const csrf = csrfToken();
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  let response: Response;
  try {
    response = await fetch(`/api/v2/${path}`, {
      ...options,
      headers,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new ApiError(503, "unavailable");
  }
  if (!response.ok) {
    let code = "request_failed";
    try {
      const data = await response.json();
      if (typeof data.error?.code === "string") code = data.error.code;
    } catch {}
    throw new ApiError(response.status, code);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
const json = (method: string, data: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});
export const api = {
  me: () => request<User>("auth/me"),
  login: (email: string, password: string) =>
    request<User>("auth/login", json("POST", { email, password })),
  register: (email: string, password: string, display_name: string) =>
    request<{ message?: string }>(
      "auth/register",
      json("POST", { email, password, display_name }),
    ),
  logout: () => request<void>("auth/logout", { method: "POST" }),
  documents: () => request<Document[]>("documents"),
  document: (id: string) =>
    request<Document>(`documents/${encodeURIComponent(id)}`),
  deleteDocument: (id: string) =>
    request<void>(`documents/${encodeURIComponent(id)}`, { method: "DELETE" }),
  upload: (file: File) => {
    const body = new FormData();
    body.set("file", file);
    return request<Upload>("documents", { method: "POST", body });
  },
  replaceDocument: (id: string, file: File) => {
    const body = new FormData();
    body.set("file", file);
    return request<Upload>(`documents/${encodeURIComponent(id)}`, {
      method: "PUT",
      body,
    });
  },
  conversations: () => request<Conversation[]>("conversations"),
  conversation: (id: string) =>
    request<ConversationDetail>(`conversations/${encodeURIComponent(id)}`),
  createConversation: (title = "New conversation") =>
    request<Conversation>("conversations", json("POST", { title })),
  renameConversation: (id: string, title: string) =>
    request<Pick<Conversation, "conversation_id" | "title">>(
      `conversations/${encodeURIComponent(id)}`,
      json("PATCH", { title }),
    ),
  deleteConversation: (id: string) =>
    request<void>(`conversations/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  chat: (conversation_id: string, message: string, turn_id?: string) =>
    request<ChatResponse>("chat", json("POST", { conversation_id, message, turn_id })),
  turn: (conversation_id: string, turn_id: string) =>
    request<ChatResponse | { state: "pending" }>(`conversations/${encodeURIComponent(conversation_id)}/turns/${encodeURIComponent(turn_id)}`),
  memories: async (conversation_id: string) => {
    const lists = await request<MemoryList[]>(
      `memories?conversation_id=${encodeURIComponent(conversation_id)}`,
    );
    return lists[0] ?? { conversation_id, memories: [], unverified_hidden: 0 };
  },
  deleteMemory: (conversation_id: string, id: number) =>
    request<void>(
      `conversations/${encodeURIComponent(conversation_id)}/memories/${id}`,
      { method: "DELETE" },
    ),
  jobs: () => request<Job[]>("jobs"),
  cancelJob: (id: string) =>
    request<{ cancelled: boolean }>(`jobs/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
    }),
  retryJob: (id: string) =>
    request<{ job_id: string }>(`jobs/${encodeURIComponent(id)}/retry`, {
      method: "POST",
    }),
  users: () => request<User[]>("admin/users"),
  updateUser: (id: string, change: Partial<Pick<User, "status" | "role">>) =>
    request<User>(
      `admin/users/${encodeURIComponent(id)}`,
      json("PATCH", change),
    ),
  resetPassword: (id: string, password: string) =>
    request<void>(
      `admin/users/${encodeURIComponent(id)}/reset-password`,
      json("POST", { password }),
    ),
};
export function fileUrl(id: string, page = 1): string {
  return `/api/v2/documents/${encodeURIComponent(id)}/file#page=${Math.max(1, Math.floor(page))}`;
}
