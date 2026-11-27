import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { Complexity, InvolvementBadge, LowConfidence } from "@/components/badges";
import { type ProjectDetail, getProject } from "@/lib/api";
import { INVOLVEMENT_ORDER, dateRange } from "@/lib/format";

function Fold({
  title,
  count,
  open = false,
  children,
}: {
  title: string;
  count?: number;
  open?: boolean;
  children: React.ReactNode;
}) {
  return (
    <details className="fold" open={open}>
      <summary>
        <h3>{title}</h3>
        {count !== undefined ? <span className="n">{count}</span> : null}
      </summary>
      <div className="body">{children}</div>
    </details>
  );
}

function List({ items }: { items: string[] }) {
  return (
    <ul style={{ margin: 0, paddingLeft: 18 }}>
      {items.map((item) => (
        <li key={item} style={{ margin: "4px 0" }}>
          {item}
        </li>
      ))}
    </ul>
  );
}

function PrRefs({ ids, project }: { ids?: string[]; project: ProjectDetail }) {
  if (!ids?.length) return null;
  const byId = new Map(project.pull_requests.map((pr) => [pr.id, pr]));
  return (
    <div className="ev-refs">
      {ids.map((id) => {
        const pr = byId.get(id);
        return (
          <span key={id} className="pr-ref" title={pr?.title}>
            {pr?.repo ?? "PR"}#{id.split("-").at(-1)}
          </span>
        );
      })}
    </div>
  );
}

async function ProjectContent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const project = await getProject(id);
  if (!project) notFound();

  const skills = [...project.skills].sort(
    (a, b) => INVOLVEMENT_ORDER.indexOf(a.involvement) - INVOLVEMENT_ORDER.indexOf(b.involvement),
  );

  return (
    <>
      <Link href="/projects" className="back">
        ← Projects
      </Link>
      <div className="detail-head">
        <h1>{project.name}</h1>
        <div className="badges">
          <Complexity level={project.complexity} />
          <LowConfidence level={project.confidence} />
          <span className="badge">
            {project.pr_count} PRs · {dateRange(project.started_on, project.last_activity_on)}
          </span>
        </div>
        <p className="detail-summary">{project.summary}</p>
        {project.complexity_reason ? (
          <p className="complexity-reason">
            <span>Why {project.complexity} complexity:</span> {project.complexity_reason}
          </p>
        ) : null}
      </div>

      <div className="detail-grid">
        <div>
          {project.uncertainties.length ? (
            <section className="section callout">
              <h3>⚠ Unverified</h3>
              <List items={project.uncertainties} />
            </section>
          ) : null}

          <Fold title="My contributions" count={project.my_contributions.length} open>
            <List items={project.my_contributions} />
          </Fold>

          <Fold title="Problem">
            <p style={{ margin: 0 }}>{project.problem}</p>
          </Fold>

          <Fold title="How it works">
            <p style={{ margin: 0 }}>{project.implementation}</p>
            {project.architecture ? (
              <p className="mono" style={{ margin: "10px 0 0", fontSize: 12 }}>
                {project.architecture}
              </p>
            ) : null}
          </Fold>

          {project.decisions.length ? (
            <Fold title="Decisions" count={project.decisions.length}>
              {project.decisions.map((d) => (
                <details key={d.decision} className="item">
                  <summary>{d.decision}</summary>
                  <div className="item-body">
                    <dl className="kv">
                      <dt>Why</dt>
                      <dd>{d.reasoning}</dd>
                      {d.alternatives?.length ? (
                        <>
                          <dt>Instead of</dt>
                          <dd>{d.alternatives.join(" · ")}</dd>
                        </>
                      ) : null}
                      {d.tradeoffs ? (
                        <>
                          <dt>Trade-off</dt>
                          <dd>{d.tradeoffs}</dd>
                        </>
                      ) : null}
                    </dl>
                    <PrRefs ids={d.pr_ids} project={project} />
                  </div>
                </details>
              ))}
            </Fold>
          ) : null}

          {project.challenges.length ? (
            <Fold title="Challenges" count={project.challenges.length}>
              {project.challenges.map((c) => (
                <details key={c.challenge} className="item">
                  <summary>{c.challenge}</summary>
                  <div className="item-body">→ {c.solution}</div>
                </details>
              ))}
            </Fold>
          ) : null}

          {project.metrics.length ? (
            <Fold title="Outcomes" count={project.metrics.length} open>
              {project.metrics.map((m) => (
                <div key={m.name} className="metric-row" title={m.evidence}>
                  <span className="metric-vals">
                    {m.before ?? "—"}
                    <span className="arrow">→</span>
                    <span className="after">{m.after ?? "—"}</span>{" "}
                    <span style={{ fontSize: 12, color: "var(--text-faint)" }}>{m.unit}</span>
                  </span>
                  <span>{m.name}</span>
                </div>
              ))}
            </Fold>
          ) : null}
        </div>

        <aside>
          <section className="section">
            <h3>Skills</h3>
            {skills.map((skill) => (
              <div key={skill.name} className="side-row" title={skill.evidence}>
                <span>{skill.name}</span>
                <InvolvementBadge involvement={skill.involvement} />
              </div>
            ))}
          </section>
        </aside>
      </div>
    </>
  );
}

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<div className="loading">Loading project…</div>}>
      <ProjectContent params={params} />
    </Suspense>
  );
}
