import Link from "next/link";

import { Complexity, InvolvementDot, LowConfidence } from "@/components/badges";
import type { ProjectSummary } from "@/lib/api";
import { INVOLVEMENT_LABEL, dateRange } from "@/lib/format";

const SHOWN_SKILLS = 3;

export function ProjectCard({ project }: { project: ProjectSummary }) {
  const shown = project.skills.slice(0, SHOWN_SKILLS);
  const more = project.skills.length - shown.length;
  return (
    <Link href={`/projects/${project.id}`} className="card">
      <div className="card-top">
        <div className="card-title">{project.name}</div>
        <span title={project.complexity_reason ?? undefined}>
          <Complexity level={project.complexity} />
        </span>
      </div>
      <p className="card-summary">{project.summary}</p>
      <div className="chips">
        {shown.map((skill) => (
          <span key={skill.name} className="chip skill-chip" title={INVOLVEMENT_LABEL[skill.involvement]}>
            <InvolvementDot involvement={skill.involvement} />
            {skill.name}
          </span>
        ))}
        {more > 0 ? <span className="chip">+{more}</span> : null}
      </div>
      <div className="card-foot">
        <span className="mono">{project.pr_count} PRs</span>
        <span>{dateRange(project.started_on, project.last_activity_on)}</span>
        <span className="spacer" />
        <LowConfidence level={project.confidence} />
      </div>
    </Link>
  );
}
