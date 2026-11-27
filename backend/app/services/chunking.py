"""Split experience data into chunks for search and RAG.

The data is already structured, so chunks follow that structure instead of
cutting text at arbitrary lengths: one chunk per meaningful section of a project
(overview, contributions, each decision, each challenge, ...) plus one per PR.

Every chunk repeats its project name and section in the text, so it still makes
sense on its own when retrieved and shown to the LLM.
"""

import hashlib
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, ChunkType
from app.experience.models import ExperienceFile, Project, PullRequest
from app.services.experience import INVOLVEMENT_RANK


@dataclass(frozen=True)
class ChunkSpec:
    id: str
    chunk_type: ChunkType
    title: str
    content: str
    project_id: str | None = None
    pr_ids: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(f"{self.title}\n{self.content}".encode()).hexdigest()


def _lines(*parts: str | None) -> str:
    return "\n".join(p for p in parts if p)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def project_chunks(project: Project) -> list[ChunkSpec]:
    skills = sorted(project.skills, key=lambda s: (INVOLVEMENT_RANK[s.involvement.value], s.name))
    common = {
        "project_id": project.id,
        "skills": [s.name for s in skills],
        "categories": project.categories,
    }

    def chunk(suffix: str, chunk_type: ChunkType, section: str, body: str, **extra) -> ChunkSpec:
        return ChunkSpec(
            id=f"{project.id}:{suffix}",
            chunk_type=chunk_type,
            title=f"{project.name} — {section}",
            content=_lines(f"Project: {project.name}", f"Section: {section}", body),
            **(common | {"pr_ids": project.pr_ids} | extra),
        )

    chunks = [
        chunk(
            "overview",
            ChunkType.overview,
            "Overview",
            _lines(
                project.summary,
                f"Categories: {', '.join(project.categories)}",
                f"Complexity: {project.complexity.value}. Confidence: {project.confidence.value}.",
                f"Unverified: {' '.join(project.uncertainties)}" if project.uncertainties else None,
            ),
        ),
        chunk(
            "problem",
            ChunkType.problem,
            "Problem and context",
            _lines(
                project.problem,
                project.context,
                f"Objectives:\n{_bullets(project.objectives)}" if project.objectives else None,
            ),
        ),
        chunk(
            "contributions",
            ChunkType.contributions,
            "My contributions",
            _bullets(project.my_contributions),
        ),
        chunk(
            "implementation",
            ChunkType.implementation,
            "Implementation and architecture",
            _lines(
                project.implementation,
                f"Architecture: {project.architecture}" if project.architecture else None,
            ),
        ),
    ]

    for i, d in enumerate(project.decisions):
        chunks.append(
            chunk(
                f"decision-{i}",
                ChunkType.decision,
                f"Decision: {d.decision}",
                _lines(
                    f"Context: {d.context}",
                    f"Decision: {d.decision}",
                    f"Reasoning: {d.reasoning}",
                    f"Alternatives considered: {', '.join(d.alternatives)}"
                    if d.alternatives
                    else None,
                    f"Trade-offs: {d.tradeoffs}" if d.tradeoffs else None,
                ),
                pr_ids=d.pr_ids or project.pr_ids,
            )
        )

    for i, c in enumerate(project.challenges):
        chunks.append(
            chunk(
                f"challenge-{i}",
                ChunkType.challenge,
                f"Challenge: {c.challenge}",
                _lines(f"Challenge: {c.challenge}", f"Solution: {c.solution}"),
            )
        )

    if project.metrics:
        rows = []
        for m in project.metrics:
            values = " → ".join(str(v) for v in (m.before, m.after) if v is not None)
            rows.append(
                f"- {m.name}: {values} {m.unit or ''}".rstrip()
                + (f" ({m.period})" if m.period else "")
                + f". Evidence: {m.evidence}"
            )
        chunks.append(chunk("outcomes", ChunkType.outcomes, "Measured outcomes", "\n".join(rows)))

    if skills:
        chunks.append(
            chunk(
                "skills",
                ChunkType.skills,
                "Skills demonstrated",
                "\n".join(f"- {s.name} ({s.involvement.value}): {s.evidence}" for s in skills),
            )
        )

    return chunks


def pull_request_chunk(pr: PullRequest, project_name: str | None) -> ChunkSpec:
    return ChunkSpec(
        id=f"pr:{pr.id}",
        chunk_type=ChunkType.pull_request,
        title=f"PR: {pr.title}",
        content=_lines(
            f"Pull request: {pr.title}",
            f"Project: {project_name}" if project_name else "Not part of a larger project.",
            f"Repository: {pr.repo}" if pr.repo else None,
            f"Status: {pr.status.value}",
            f"Summary: {pr.summary}",
            f"My contribution: {pr.contribution}",
            f"Problem: {pr.problem}" if pr.problem else None,
            f"Technologies: {', '.join(pr.technologies)}" if pr.technologies else None,
        ),
        project_id=pr.project_id,
        pr_ids=[pr.id],
        skills=pr.technologies,
    )


def build_chunks(data: ExperienceFile) -> list[ChunkSpec]:
    names = {p.id: p.name for p in data.projects}
    chunks = [c for project in data.projects for c in project_chunks(project)]
    chunks += [pull_request_chunk(pr, names.get(pr.project_id or "")) for pr in data.pull_requests]
    return chunks


def sync_chunks(session: Session, specs: list[ChunkSpec]) -> int:
    """Make the chunks table match `specs`. Caller commits.

    Chunks whose text is unchanged keep their embedding. New or edited chunks
    get `embedding = NULL` so the embedding step picks them up.
    """
    wanted = {spec.id: spec for spec in specs}
    session.execute(delete(Chunk).where(Chunk.id.not_in(wanted)))
    existing = {c.id: c for c in session.scalars(select(Chunk))}

    for spec in specs:
        fields = {
            "project_id": spec.project_id,
            "pr_ids": spec.pr_ids,
            "chunk_type": spec.chunk_type.value,
            "title": spec.title,
            "content": spec.content,
            "skills": spec.skills,
            "categories": spec.categories,
            "content_hash": spec.content_hash,
        }
        row = existing.get(spec.id)
        if row is None:
            session.add(Chunk(id=spec.id, **fields))
            continue
        if row.content_hash != spec.content_hash:
            row.embedding = None
            row.embed_model = None
            row.embedded_at = None
        for name, value in fields.items():
            if getattr(row, name) != value:
                setattr(row, name, value)
    session.flush()
    return len(specs)
