"use server";

import { type AskResult, askAssistant } from "@/lib/api";

export async function askQuestion(question: string): Promise<AskResult> {
  const trimmed = question.trim().slice(0, 1000);
  if (!trimmed) return { ok: false, error: "Please type a question." };
  return askAssistant(trimmed);
}
