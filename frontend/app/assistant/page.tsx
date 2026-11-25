import type { Metadata } from "next";

import { Placeholder } from "@/components/placeholder";

export const metadata: Metadata = { title: "Ask my experience" };

export default function AssistantPage() {
  return (
    <Placeholder
      title="Ask my experience"
      text="Questions about your work, answered with evidence."
      stage={2}
    />
  );
}
