// Typed client for the WorkStory backend. Used from Server Components only.

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export type Involvement =
  | "implemented"
  | "collaborated"
  | "modified"
  | "used"
  | "discussed"
  | "mentioned";
export type Level = "low" | "medium" | "high";

export interface Profile {
  owner_name: string;
  summary: string;
  experience_level: string;
  primary_roles: string[];
  primary_technologies: string[];
}

export interface ProjectSkill {
  name: string;
  category: string;
  involvement: Involvement;
  evidence: string;
}

export interface ProjectSummary {
  id: string;
  name: string;
  summary: string;
  complexity: Level;
  complexity_reason: string | null;
  confidence: Level;
  categories: string[];
  skills: ProjectSkill[];
  pr_count: number;
  started_on: string | null;
  last_activity_on: string | null;
}

export interface PullRequest {
  id: string;
  project_id: string | null;
  title: string;
  repo: string | null;
  status: "merged" | "open" | "closed";
}

export interface Decision {
  context: string;
  decision: string;
  reasoning: string;
  alternatives?: string[];
  tradeoffs?: string | null;
  pr_ids?: string[];
}

export interface Challenge {
  challenge: string;
  solution: string;
}

export interface Metric {
  name: string;
  before?: number | null;
  after?: number | null;
  unit?: string | null;
  period?: string | null;
  evidence: string;
}

export interface ProjectDetail extends ProjectSummary {
  problem: string;
  context: string | null;
  objectives: string[];
  my_contributions: string[];
  implementation: string;
  architecture: string | null;
  challenges: Challenge[];
  decisions: Decision[];
  metrics: Metric[];
  uncertainties: string[];
  pull_requests: PullRequest[];
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Skill {
  name: string;
  category: string;
  description: string | null;
  aliases: string[];
  project_count: number;
  strongest_involvement: Involvement | null;
  projects: { id: string; name: string; involvement: Involvement }[];
}

export interface Category {
  name: string;
  description: string | null;
  project_count: number;
  projects: { id: string; name: string }[];
}

export class ApiUnavailableError extends Error {
  constructor() {
    super(`Cannot reach the WorkStory API at ${API_URL}. Is the backend running?`);
  }
}

/** GET a JSON resource. Returns null on 404. */
async function get<T>(path: string): Promise<T | null> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`);
  } catch {
    throw new ApiUnavailableError();
  }
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`API request ${path} failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function getOrThrow<T>(path: string): Promise<T> {
  const result = await get<T>(path);
  if (result === null) throw new Error(`API request ${path} returned 404`);
  return result;
}

export interface ProjectQuery {
  q?: string;
  skill?: string;
  category?: string;
  complexity?: Level;
  handsOn?: boolean;
  sort?: "recent" | "complexity" | "name";
}

export function getProjects(query: ProjectQuery): Promise<Page<ProjectSummary>> {
  const params = new URLSearchParams({ limit: "100" });
  if (query.q) params.set("q", query.q);
  if (query.skill) params.set("skill", query.skill);
  if (query.category) params.set("category", query.category);
  if (query.complexity) params.set("complexity", query.complexity);
  if (query.sort) params.set("sort", query.sort);
  if (query.handsOn) {
    params.append("involvement", "implemented");
    params.append("involvement", "collaborated");
  }
  return getOrThrow(`/projects?${params}`);
}

export const getProject = (id: string) =>
  get<ProjectDetail>(`/projects/${encodeURIComponent(id)}`);
export const getProfile = () => get<Profile>("/profile");
export const getPullRequestCount = async () =>
  (await getOrThrow<Page<PullRequest>>("/pull-requests?limit=1")).total;
export const getSkills = () => getOrThrow<Skill[]>("/skills");
export const getCategories = () => getOrThrow<Category[]>("/categories");

// ---------- Assistant ----------

export type Support = "direct" | "partial" | "none";

export interface Citation {
  number: number;
  chunk_id: string;
  chunk_type: string;
  title: string;
  snippet: string;
  project_id: string | null;
  project_name: string | null;
  pr_ids: string[];
}

export interface AskResponse {
  question: string;
  answer: string;
  support: Support;
  limitations: string | null;
  citations: Citation[];
  retrieved_chunk_ids: string[];
  took_ms: number;
  warning: string | null;
}

export type AskResult = { ok: true; data: AskResponse } | { ok: false; error: string };

export async function askAssistant(question: string): Promise<AskResult> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/assistant/ask`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch {
    return { ok: false, error: new ApiUnavailableError().message };
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : `Request failed (${response.status})`;
    return { ok: false, error: detail };
  }
  return { ok: true, data: (await response.json()) as AskResponse };
}
