import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { getCategories } from "@/lib/api";

export const metadata: Metadata = { title: "Categories" };

async function CategoriesContent() {
  const categories = await getCategories();
  if (!categories.length) return <div className="empty">No categories imported yet.</div>;
  return (
    <div className="cat-grid">
      {categories.map((c) => (
        <Link
          key={c.name}
          href={`/projects?category=${encodeURIComponent(c.name)}`}
          className="cat-card"
          title={c.projects.map((p) => p.name).join("\n")}
        >
          <b style={{ fontWeight: 560 }}>{c.name}</b>
          <span className="cat-count">{c.project_count}</span>
        </Link>
      ))}
    </div>
  );
}

export default function CategoriesPage() {
  return (
    <>
      <div className="page-header">
        <h1>Categories</h1>
      </div>
      <Suspense fallback={<div className="loading">Loading categories…</div>}>
        <CategoriesContent />
      </Suspense>
    </>
  );
}
