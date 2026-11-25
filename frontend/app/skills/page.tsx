import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { InvolvementBadge, InvolvementDot } from "@/components/badges";
import { type Skill, getSkills } from "@/lib/api";
import { INVOLVEMENT_LABEL, INVOLVEMENT_ORDER } from "@/lib/format";

export const metadata: Metadata = { title: "Skills" };

function SkillLine({ skill }: { skill: Skill }) {
  const n = skill.project_count;
  return (
    <details className="skill-line">
      <summary>
        <span className="skill-name">{skill.name}</span>
        <span>
          {skill.strongest_involvement ? (
            <InvolvementBadge involvement={skill.strongest_involvement} />
          ) : null}
        </span>
        <span className="cnt mono" style={{ fontSize: 12, color: "var(--text-faint)", textAlign: "right" }}>
          {n} project{n === 1 ? "" : "s"}
        </span>
      </summary>
      <div className="chips">
        {skill.projects.map((p) => (
          <Link key={p.id} href={`/projects/${p.id}`} className="chip skill-chip proj-link">
            <InvolvementDot involvement={p.involvement} />
            {p.name}
          </Link>
        ))}
      </div>
    </details>
  );
}

async function SkillsContent() {
  const skills = await getSkills();
  const groups = new Map<string, Skill[]>();
  for (const skill of skills) {
    groups.set(skill.category, [...(groups.get(skill.category) ?? []), skill]);
  }

  if (!skills.length) return <div className="empty">No skills imported yet.</div>;

  return (
    <>
      {[...groups].map(([group, list]) => (
        <div key={group} className="skill-group">
          <h2>{group}</h2>
          <div className="skill-table">
            {list.map((skill) => (
              <SkillLine key={skill.name} skill={skill} />
            ))}
          </div>
        </div>
      ))}
    </>
  );
}

export default function SkillsPage() {
  return (
    <>
      <div className="page-header">
        <h1>Skills</h1>
      </div>
      <div className="legend">
        {INVOLVEMENT_ORDER.map((inv) => (
          <span key={inv}>
            <InvolvementDot involvement={inv} />
            {INVOLVEMENT_LABEL[inv]}
          </span>
        ))}
      </div>
      <Suspense fallback={<div className="loading">Loading skills…</div>}>
        <SkillsContent />
      </Suspense>
    </>
  );
}
