import type { Metadata } from "next";
import { Suspense } from "react";

import { ProjectCard } from "@/components/project-card";
import { type FilterValues, ProjectFilters } from "@/components/project-filters";
import { type Level, getCategories, getProjects, getPullRequestCount, getSkills } from "@/lib/api";

export const metadata: Metadata = { title: "Projects" };

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

const first = (value: string | string[] | undefined) =>
  (Array.isArray(value) ? value[0] : value) ?? "";

function parseFilters(params: Record<string, string | string[] | undefined>): FilterValues {
  const complexity = first(params.complexity);
  const sort = first(params.sort);
  return {
    q: first(params.q),
    skill: first(params.skill),
    category: first(params.category),
    complexity: ["high", "medium", "low"].includes(complexity) ? complexity : "",
    handsOn: first(params.handsOn) === "1",
    sort: ["recent", "complexity", "name"].includes(sort) ? sort : "recent",
  };
}

async function ProjectsContent({ searchParams }: { searchParams: SearchParams }) {
  const filters = parseFilters(await searchParams);
  const [page, skills, categories, all, prCount] = await Promise.all([
    getProjects({
      q: filters.q,
      skill: filters.skill,
      category: filters.category,
      complexity: (filters.complexity || undefined) as Level | undefined,
      handsOn: filters.handsOn,
      sort: filters.sort as "recent" | "complexity" | "name",
    }),
    getSkills(),
    getCategories(),
    getProjects({}),
    getPullRequestCount(),
  ]);

  return (
    <>
      <div className="page-header">
        <h1>Projects</h1>
        <div className="stats">
          <Stat value={all.total} label="Projects" />
          <Stat value={prCount} label="PRs" />
          <Stat value={skills.length} label="Skills" />
        </div>
      </div>

      <ProjectFilters
        values={filters}
        skills={skills.map((s) => s.name).sort((a, b) => a.localeCompare(b))}
        categories={categories.map((c) => c.name)}
      >
        {all.total === 0 ? (
          <div className="empty">
            No experience imported yet. Run <span className="mono">uv run workstory-import</span> in{" "}
            <span className="mono">backend/</span>.
          </div>
        ) : page.items.length ? (
          <div className="grid">
            {page.items.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </div>
        ) : (
          <div className="empty">
            No matching projects.
            {filters.skill && filters.handsOn ? (
              <>
                <br />
                {filters.skill} appears in your data, but not as hands-on work.
              </>
            ) : null}
          </div>
        )}
      </ProjectFilters>
    </>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export default function ProjectsPage({ searchParams }: { searchParams: SearchParams }) {
  return (
    <Suspense fallback={<div className="loading">Loading projects…</div>}>
      <ProjectsContent searchParams={searchParams} />
    </Suspense>
  );
}
