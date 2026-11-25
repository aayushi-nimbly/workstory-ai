import type { Metadata } from "next";

import { Placeholder } from "@/components/placeholder";

export const metadata: Metadata = { title: "Interview Prep" };

export default function PrepPage() {
  return (
    <Placeholder
      title="Interview Prep"
      text="Role-, JD- and project-based questions grounded in your work."
      stage={3}
    />
  );
}
