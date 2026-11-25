import Link from "next/link";

export default function NotFound() {
  return (
    <div className="empty">
      Not found. <Link href="/projects">Back to projects</Link>
    </div>
  );
}
