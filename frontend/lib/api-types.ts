/** Generated FastAPI response bindings. Regenerate openapi.d.ts from openapi.json. */
import type { components } from "./openapi";
export type User = components["schemas"]["UserOut"];
export type Document = components["schemas"]["DocumentOut"];
export type Upload = components["schemas"]["UploadOut"];
export type Job = components["schemas"]["JobOut"];
export type Conversation = components["schemas"]["ConversationOut"];
export type Message = components["schemas"]["MessageOut"];
export type ConversationDetail = components["schemas"]["HistoryOut"];
export type Citation = components["schemas"]["CitationOut"];
export type ChatResponse = components["schemas"]["ChatOut"];
export type Memory = components["schemas"]["MemoryOut"];
export type MemoryList = components["schemas"]["MemoryListOut"];
export type AnswerStatus = "answered" | "partial" | "abstained";
