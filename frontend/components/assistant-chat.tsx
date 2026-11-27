"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useTransition } from "react";

import { askQuestion } from "@/app/assistant/actions";
import type { AskResponse, Citation, Support } from "@/lib/api";

const SUGGESTIONS = [
  "Have I implemented retry mechanisms?",
  "What performance optimisation work have I done?",
  "What database decisions have I made?",
  "Have I worked with Kafka?",
];

const SUPPORT_LABEL: Record<Support, string> = {
  direct: "Backed by your work",
  partial: "Partly backed",
  none: "Not enough evidence",
};

type Turn =
  | { id: number; question: string; status: "pending" }
  | { id: number; question: string; status: "done"; answer: AskResponse }
  | { id: number; question: string; status: "error"; error: string };

/** Answer text with [n] markers turned into citation chips. */
function AnswerText({ text, onCite }: { text: string; onCite: (n: number) => void }) {
  const parts = text.split(/(\[\d+\])/g);
  return (
    <p className="answer-text">
      {parts.map((part, i) => {
        const match = /^\[(\d+)\]$/.exec(part);
        if (!match) return <span key={i}>{part}</span>;
        const n = Number(match[1]);
        return (
          <button key={i} className="cite" onClick={() => onCite(n)} title={`Evidence ${n}`}>
            {n}
          </button>
        );
      })}
    </p>
  );
}

function Evidence({ citation, highlighted }: { citation: Citation; highlighted: boolean }) {
  const section = citation.title.split(" — ").at(-1);
  return (
    <details className={`evidence${highlighted ? " highlight" : ""}`} open={highlighted}>
      <summary>
        <span className="cite static">{citation.number}</span>
        {citation.project_id ? (
          <Link href={`/projects/${citation.project_id}`} onClick={(e) => e.stopPropagation()}>
            {citation.project_name}
          </Link>
        ) : (
          <span>Pull request</span>
        )}
        <span className="evidence-section">{section}</span>
      </summary>
      <p className="evidence-snippet">{citation.snippet}</p>
    </details>
  );
}

function AnswerCard({ answer }: { answer: AskResponse }) {
  const [highlighted, setHighlighted] = useState<number | null>(null);
  return (
    <div className="answer-card">
      <div className="answer-head">
        <span className={`support support-${answer.support}`}>{SUPPORT_LABEL[answer.support]}</span>
        <span className="mono answer-time">{(answer.took_ms / 1000).toFixed(1)}s</span>
      </div>
      <AnswerText text={answer.answer} onCite={(n) => setHighlighted(n === highlighted ? null : n)} />
      {answer.limitations ? <p className="answer-note">⚠ {answer.limitations}</p> : null}
      {answer.warning ? <p className="answer-note">⚠ {answer.warning}</p> : null}
      {answer.citations.length ? (
        <div className="evidence-list">
          {answer.citations.map((c) => (
            <Evidence key={c.number} citation={c} highlighted={c.number === highlighted} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function AssistantChat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, startTransition] = useTransition();
  const nextId = useRef(1);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  function submit(text: string) {
    const q = text.trim();
    if (!q || pending) return;
    const id = nextId.current++;
    setTurns((t) => [...t, { id, question: q, status: "pending" }]);
    setQuestion("");
    startTransition(async () => {
      const result = await askQuestion(q);
      setTurns((t) =>
        t.map((turn) =>
          turn.id !== id
            ? turn
            : result.ok
              ? { id, question: q, status: "done", answer: result.data }
              : { id, question: q, status: "error", error: result.error },
        ),
      );
    });
  }

  return (
    <div className="chat">
      {turns.length === 0 ? (
        <div className="chat-empty">
          <div className="chips">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="chip suggestion" onClick={() => submit(s)}>
                {s}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="turns">
          {turns.map((turn) => (
            <div key={turn.id} className="turn">
              <div className="question">{turn.question}</div>
              {turn.status === "pending" ? (
                <div className="answer-card thinking">Searching your experience…</div>
              ) : turn.status === "error" ? (
                <div className="error-box">
                  <h2>Couldn’t answer</h2>
                  <p style={{ margin: 0, color: "var(--text-muted)" }}>{turn.error}</p>
                </div>
              ) : (
                <AnswerCard answer={turn.answer} />
              )}
            </div>
          ))}
          <div ref={bottom} />
        </div>
      )}

      <form
        className="ask-bar"
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about your experience…"
          maxLength={1000}
          autoFocus
        />
        <button type="submit" disabled={pending || !question.trim()}>
          {pending ? "…" : "Ask"}
        </button>
      </form>
    </div>
  );
}
