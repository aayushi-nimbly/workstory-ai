import type { Metadata } from "next";

import { AssistantChat } from "@/components/assistant-chat";

export const metadata: Metadata = { title: "Ask my experience" };

export default function AssistantPage() {
  return (
    <>
      <div className="page-header">
        <h1>Ask my experience</h1>
      </div>
      <AssistantChat />
    </>
  );
}
