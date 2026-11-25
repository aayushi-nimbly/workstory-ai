"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

export interface FilterValues {
  q: string;
  skill: string;
  category: string;
  complexity: string; // "" = any
  handsOn: boolean;
  sort: string;
}

const COMPLEXITIES = [
  ["", "Any"],
  ["high", "High"],
  ["medium", "Medium"],
  ["low", "Low"],
] as const;

/** Filter bar. Every change is written to the URL, which re-renders the server page. */
export function ProjectFilters({
  values,
  skills,
  categories,
  children,
}: {
  values: FilterValues;
  skills: string[];
  categories: string[];
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [pending, startTransition] = useTransition();
  const [q, setQ] = useState(values.q);
  const debounce = useRef<ReturnType<typeof setTimeout>>(undefined);

  function apply(next: Partial<FilterValues>) {
    const merged = { ...values, q, ...next };
    const params = new URLSearchParams();
    if (merged.q.trim()) params.set("q", merged.q.trim());
    if (merged.skill) params.set("skill", merged.skill);
    if (merged.category) params.set("category", merged.category);
    if (merged.complexity) params.set("complexity", merged.complexity);
    if (merged.handsOn) params.set("handsOn", "1");
    if (merged.sort && merged.sort !== "recent") params.set("sort", merged.sort);
    const query = params.toString();
    startTransition(() => router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false }));
  }

  function onSearch(value: string) {
    setQ(value);
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => apply({ q: value }), 250);
  }

  useEffect(() => () => clearTimeout(debounce.current), []);

  const anyFilter = values.q || values.skill || values.category || values.complexity || values.handsOn;

  return (
    <>
      <div className="toolbar">
        <label className="search">
          <span style={{ color: "var(--text-faint)" }}>⌕</span>
          <input placeholder="Search…" value={q} onChange={(e) => onSearch(e.target.value)} />
        </label>
        <select value={values.skill} onChange={(e) => apply({ skill: e.target.value })}>
          <option value="">Skill</option>
          {skills.map((name) => (
            <option key={name}>{name}</option>
          ))}
        </select>
        <select value={values.category} onChange={(e) => apply({ category: e.target.value })}>
          <option value="">Category</option>
          {categories.map((name) => (
            <option key={name}>{name}</option>
          ))}
        </select>
        <div className="seg">
          {COMPLEXITIES.map(([value, label]) => (
            <button
              key={value}
              className={values.complexity === value ? "on" : ""}
              onClick={() => apply({ complexity: value })}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          className={`toggle${values.handsOn ? " on" : ""}`}
          title="Only implemented or collaborated work"
          onClick={() => apply({ handsOn: !values.handsOn })}
        >
          <span className="dot" />
          Hands-on
        </button>
        <select value={values.sort} onChange={(e) => apply({ sort: e.target.value })}>
          <option value="recent">Recent</option>
          <option value="complexity">Complexity</option>
          <option value="name">Name</option>
        </select>
      </div>
      {anyFilter ? (
        <div className="result-line">
          <button
            onClick={() => {
              setQ("");
              apply({ q: "", skill: "", category: "", complexity: "", handsOn: false });
            }}
          >
            Clear filters
          </button>
        </div>
      ) : null}
      <div className={pending ? "pending" : undefined}>{children}</div>
    </>
  );
}
