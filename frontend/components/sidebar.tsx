import { Suspense, cache } from "react";

import { NavLink } from "@/components/nav-link";
import { getCategories, getProfile, getProjects, getSkills } from "@/lib/api";

// One fetch per request, shared by the three count badges.
const getCounts = cache(async () => {
  const [projects, skills, categories] = await Promise.all([
    getProjects({}),
    getSkills(),
    getCategories(),
  ]);
  return { projects: projects.total, skills: skills.length, categories: categories.length };
});

/** Sidebar data is optional: if the API is down, the page body shows the error instead. */
async function orNull<T>(load: () => Promise<T>): Promise<T | null> {
  try {
    return await load();
  } catch {
    return null;
  }
}

async function CountBadge({ which }: { which: "projects" | "skills" | "categories" }) {
  const counts = await orNull(getCounts);
  return counts ? <span className="count">{counts[which]}</span> : null;
}

async function ProfileFooter() {
  const profile = await orNull(getProfile);
  if (!profile) return <div className="profile-meta">No data imported yet</div>;
  return (
    <>
      <div className="profile-name">{profile.owner_name}</div>
      <div className="profile-meta">
        {profile.experience_level}
        {profile.primary_roles[0] ? ` · ${profile.primary_roles[0]}` : ""}
      </div>
    </>
  );
}

const Soon = ({ stage }: { stage: number }) => <span className="soon">Stage {stage}</span>;

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">W</div>
        <div className="brand-name">WorkStory AI</div>
      </div>

      <nav>
        <div className="nav-group-label">My Experience</div>
        <NavLink href="/projects" icon="▦" trailing={<Suspense><CountBadge which="projects" /></Suspense>}>
          Projects
        </NavLink>
        <NavLink href="/skills" icon="◆" trailing={<Suspense><CountBadge which="skills" /></Suspense>}>
          Skills
        </NavLink>
        <NavLink href="/categories" icon="▤" trailing={<Suspense><CountBadge which="categories" /></Suspense>}>
          Categories
        </NavLink>
      </nav>

      <nav>
        <div className="nav-group-label">Assistant</div>
        <NavLink href="/assistant" icon="✦" trailing={<Soon stage={2} />}>
          Ask my experience
        </NavLink>
      </nav>

      <nav>
        <div className="nav-group-label">Interview Prep</div>
        <NavLink href="/prep" icon="◎" trailing={<Soon stage={3} />}>
          Interview prep
        </NavLink>
      </nav>

      <div className="sidebar-footer">
        <Suspense fallback={<div className="profile-meta">…</div>}>
          <ProfileFooter />
        </Suspense>
      </div>
    </aside>
  );
}
