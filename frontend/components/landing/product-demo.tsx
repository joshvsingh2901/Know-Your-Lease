"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { usePrefersReducedMotion } from "./hooks";

const ACCENT = "var(--l-accent)";

/** Mounts a fresh phase timer whenever `resetKey` changes, so switching the
 * demo question replays the reveal instead of reusing stale phase state
 * (a plain in-place reset would need a synchronous setState in the effect body). */
function RevealTimer({
  resetKey,
  active,
  reducedMotion,
  children,
}: {
  resetKey: string;
  active: boolean;
  reducedMotion: boolean;
  children: (phase: number, fastForward: () => void) => ReactNode;
}) {
  return (
    <RevealTimerInner key={resetKey} active={active} reducedMotion={reducedMotion}>
      {children}
    </RevealTimerInner>
  );
}

function RevealTimerInner({
  active,
  reducedMotion,
  children,
}: {
  active: boolean;
  reducedMotion: boolean;
  children: (phase: number, fastForward: () => void) => ReactNode;
}) {
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    if (!active || reducedMotion) return;
    const timers = [setTimeout(() => setPhase(1), 420), setTimeout(() => setPhase(2), 1150)];
    return () => timers.forEach(clearTimeout);
  }, [active, reducedMotion]);

  const activePhase = !active ? 0 : reducedMotion ? 2 : phase;
  return <>{children(activePhase, () => setPhase(2))}</>;
}

type Paragraph = { num: string; text: string; highlight?: boolean };

type DemoKey = "pets" | "early" | "deposit";

type DemoEntry = {
  question: string;
  answer: string;
  citation: string;
  page: number;
  heading: string;
  paras: Paragraph[];
};

const DATA: Record<DemoKey, DemoEntry> = {
  pets: {
    question: "Can I have pets?",
    answer:
      "Yes, but only with the Landlord's written consent. If it's granted, there's a one-time $250 pet fee, and you stay responsible for any damage the animal causes.",
    citation: "Page 13 · §14.2",
    page: 13,
    heading: "Article 14. Use of Premises",
    paras: [
      {
        num: "14.1",
        text: "The Premises shall be used and occupied by the Tenant exclusively as a private single-family residence. No part of the Premises shall be used at any time for the purpose of carrying on any business, profession, or trade.",
      },
      {
        num: "14.2",
        text: "No dog, cat, bird, or other animal shall be kept in or about the Premises without the prior written consent of the Landlord. Where such consent is granted, the Tenant shall pay a one-time pet fee of two hundred fifty dollars ($250.00) and shall remain liable for any damage caused by the animal.",
        highlight: true,
      },
      {
        num: "14.3",
        text: "The Tenant shall not permit any conduct on the Premises that unreasonably disturbs the quiet enjoyment of other occupants of the building, including between the hours of 11:00 p.m. and 7:00 a.m.",
      },
      {
        num: "14.4",
        text: "Service animals as defined by applicable provincial legislation are not considered pets for the purposes of Section 14.2 and no fee shall be charged in respect of them.",
      },
    ],
  },
  early: {
    question: "What happens if I need to leave before the lease ends?",
    answer:
      "You can end the lease early with sixty days' written notice plus a fee equal to one month's rent ($1,850). Assigning or subletting with the Landlord's approval is the alternative the lease allows.",
    citation: "Page 9 · §9.1",
    page: 9,
    heading: "Article 9. Early Termination",
    paras: [
      {
        num: "9.1",
        text: "The Tenant may terminate this Agreement prior to the expiry of the Term by delivering to the Landlord not less than sixty (60) days' written notice, together with a termination fee equal to one (1) month's Rent, being one thousand eight hundred fifty dollars ($1,850.00).",
        highlight: true,
      },
      {
        num: "9.2",
        text: "In lieu of termination under Section 9.1, the Tenant may assign this Agreement or sublet the Premises with the prior written approval of the Landlord, such approval not to be unreasonably withheld.",
      },
      {
        num: "9.3",
        text: "Notice given under this Article shall be effective on the last day of the calendar month following the month in which it is received by the Landlord.",
      },
      {
        num: "9.4",
        text: "Nothing in this Article limits the Tenant's rights of termination arising under applicable residential tenancy legislation.",
      },
    ],
  },
  deposit: {
    question: "When do I get my deposit back?",
    answer:
      "Within twenty-one days of moving out and returning the keys. Anything deducted has to come with a written, itemized statement.",
    citation: "Page 4 · §5.3",
    page: 4,
    heading: "Article 5. Security Deposit",
    paras: [
      {
        num: "5.1",
        text: "The Tenant has deposited with the Landlord the sum of one thousand eight hundred fifty dollars ($1,850.00) as a Security Deposit, to be held in accordance with applicable legislation.",
      },
      {
        num: "5.2",
        text: "The Security Deposit shall not be applied by the Tenant toward payment of the last month's Rent or any other amount owing under this Agreement.",
      },
      {
        num: "5.3",
        text: "The Landlord shall return the Security Deposit, less any lawful deductions, within twenty-one (21) days following the termination of the tenancy and the delivery of vacant possession, accompanied by a written itemized statement of any amounts withheld.",
        highlight: true,
      },
      {
        num: "5.4",
        text: "Deductions may be made only for unpaid Rent or for damage beyond reasonable wear and tear, and shall be supported by receipts made available to the Tenant on request.",
      },
    ],
  },
};

const PROMPTS: { key: DemoKey; label: string }[] = [
  { key: "pets", label: "Can I have pets?" },
  { key: "early", label: "Can I leave early?" },
  { key: "deposit", label: "When do I get my deposit back?" },
];

export function ProductDemo() {
  const reducedMotion = usePrefersReducedMotion();
  const sectionRef = useRef<HTMLDivElement>(null);
  const [started, setStarted] = useState(false);
  const [key, setKey] = useState<DemoKey>("pets");

  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setStarted(true);
          observer.disconnect();
        }
      },
      { threshold: 0.25 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  function ask(nextKey: DemoKey) {
    setKey(nextKey);
    setStarted(true);
  }

  const entry = DATA[key];

  return (
    <section id="demo" ref={sectionRef} style={{ borderTop: "1px solid var(--l-line)", background: "var(--l-paper-alt)" }}>
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "56px 24px 72px" }}>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: 16,
            marginBottom: 28,
            paddingBottom: 16,
            borderBottom: "1px solid var(--l-line)",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11.5, color: "var(--l-accent)", marginBottom: 9 }}>
              The product
            </div>
            <h2
              style={{
                fontFamily: "var(--font-serif-display)",
                fontWeight: 400,
                fontSize: "clamp(28px, 3.4vw, 38px)",
                lineHeight: 1.08,
                letterSpacing: "-0.01em",
                margin: 0,
                maxWidth: "24ch",
              }}
            >
              Every answer points back to the page it came from.
            </h2>
          </div>
          <div style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11.5, color: "var(--l-muted)" }}>
            Question &rarr; Answer &rarr; Source
          </div>
        </div>

        <div
          style={{
            border: "1px solid var(--l-line-strong)",
            borderRadius: 3,
            background: "var(--l-surface)",
            overflow: "hidden",
            boxShadow: "0 1px 0 rgba(27,26,23,0.04), 0 18px 40px -34px rgba(27,26,23,0.5)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              height: 40,
              padding: "0 14px",
              borderBottom: "1px solid var(--l-line)",
              background: "#F7F4EE",
            }}
          >
            <span style={{ width: 9, height: 11, border: "1.2px solid #A79E90", borderRadius: 1 }} />
            <span
              style={{
                fontSize: 13,
                color: "var(--l-text)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              Residential_Tenancy_Agreement_2026.pdf
            </span>
            <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)", whiteSpace: "nowrap" }}>
              24 pages
            </span>
            <span style={{ flex: 1 }} />
            <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)", whiteSpace: "nowrap" }}>
              Saved to your library
            </span>
          </div>

          <RevealTimer resetKey={key} active={started} reducedMotion={reducedMotion}>
            {(activePhase, fastForward) => {
              const lit = activePhase >= 2;
              const showAnswer = activePhase >= 1;
              return (
          <div style={{ display: "flex", flexWrap: "wrap" }}>
            <div style={{ flex: "1 1 400px", minWidth: 0, borderRight: "1px solid var(--l-line)", background: "#F3F0E9", padding: 18 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)" }}>Document</span>
                <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)" }}>
                  Page {entry.page} of 24
                </span>
              </div>
              <div
                style={{
                  background: "var(--l-surface-alt)",
                  border: "1px solid var(--l-line)",
                  borderRadius: 2,
                  padding: "26px 26px 30px",
                  minHeight: 392,
                }}
              >
                <div
                  style={{
                    fontFamily: "var(--font-serif-text)",
                    fontSize: 14,
                    color: "var(--l-faint)",
                    borderBottom: "1px solid var(--l-line)",
                    paddingBottom: 10,
                    marginBottom: 18,
                  }}
                >
                  {entry.heading}
                </div>
                {entry.paras.map((p) => {
                  const paraLit = Boolean(p.highlight) && lit;
                  return (
                    <p
                      key={p.num}
                      style={{
                        margin: "0 0 14px",
                        fontFamily: "var(--font-serif-text)",
                        fontSize: 14.5,
                        lineHeight: 1.72,
                        color: "#2A2721",
                        transition: "background 420ms ease, box-shadow 420ms ease",
                        padding: "2px 4px",
                        marginLeft: -4,
                        background: paraLit ? "rgba(154,91,60,0.13)" : "transparent",
                        boxShadow: paraLit ? `inset 3px 0 0 ${ACCENT}` : "inset 0 0 0 rgba(0,0,0,0)",
                      }}
                    >
                      <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11.5, color: "var(--l-faint)", marginRight: 8 }}>
                        {p.num}
                      </span>
                      {p.text}
                    </p>
                  );
                })}
              </div>
            </div>

            <div style={{ flex: "1 1 380px", minWidth: 0, display: "flex", flexDirection: "column", background: "var(--l-surface)" }}>
              <div style={{ padding: "18px 18px 0" }}>
                <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)" }}>Ask</span>
              </div>
              <div style={{ padding: "14px 18px 18px", display: "flex", flexDirection: "column", gap: 14, flex: 1 }}>
                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                  <div
                    style={{
                      maxWidth: "82%",
                      background: "#EFEADF",
                      border: "1px solid var(--l-line)",
                      borderRadius: 2,
                      padding: "10px 13px",
                      fontSize: 14.5,
                      lineHeight: 1.45,
                      color: "#2A2721",
                    }}
                  >
                    {entry.question}
                  </div>
                </div>
                {showAnswer && (
                  <div style={{ animation: reducedMotion ? "none" : "kylFade 420ms ease both" }}>
                    <p style={{ margin: 0, fontSize: 14.5, lineHeight: 1.62, color: "#2A2721" }}>{entry.answer}</p>
                    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                      <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)" }}>Source</span>
                      <button
                        type="button"
                        onClick={fastForward}
                        style={{
                          cursor: "pointer",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 7,
                          fontFamily: "var(--font-mono-editorial)",
                          fontSize: 11.5,
                          letterSpacing: "0.02em",
                          padding: "6px 11px",
                          borderRadius: 2,
                          whiteSpace: "nowrap",
                          transition: "all 240ms ease",
                          border: `1px solid ${lit ? ACCENT : "var(--l-line-strong)"}`,
                          background: lit ? "rgba(154,91,60,0.10)" : "#F7F4EE",
                          color: lit ? ACCENT : "var(--l-text)",
                        }}
                      >
                        {entry.citation}
                        <span style={{ fontSize: 12, lineHeight: 1 }}>&#8598;</span>
                      </button>
                      <span style={{ fontSize: 12.5, color: "var(--l-muted)" }}>
                        {lit ? "Highlighted in the document at left." : "Click to find this clause."}
                      </span>
                    </div>
                  </div>
                )}
                <div style={{ flex: 1, minHeight: 12 }} />
                <div>
                  <div style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)", marginBottom: 9 }}>
                    Try another question
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {PROMPTS.map((prompt) => (
                      <button
                        key={prompt.key}
                        type="button"
                        onClick={() => ask(prompt.key)}
                        style={{
                          cursor: "pointer",
                          fontFamily: "var(--font-sans-editorial)",
                          fontSize: 13.5,
                          padding: "7px 12px",
                          border: `1px solid ${key === prompt.key ? "var(--l-ink)" : "var(--l-line-strong)"}`,
                          background: "#F7F4EE",
                          color: "#2A2721",
                          borderRadius: 2,
                          transition: "border-color 200ms ease",
                        }}
                      >
                        {prompt.label}
                      </button>
                    ))}
                  </div>
                  <div
                    style={{
                      marginTop: 14,
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      border: "1px solid var(--l-line)",
                      borderRadius: 2,
                      background: "#F7F4EE",
                      padding: "10px 12px",
                    }}
                  >
                    <span style={{ fontSize: 14, color: "#9A9287", flex: 1 }}>Ask about your own lease&hellip;</span>
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        height: 28,
                        padding: "0 12px",
                        background: "var(--l-ink)",
                        color: "var(--l-surface)",
                        borderRadius: 2,
                        fontSize: 12.5,
                      }}
                    >
                      Ask
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
              );
            }}
          </RevealTimer>
        </div>
        <p style={{ margin: "14px 2px 0", fontSize: 13, color: "var(--l-muted)" }}>
          Illustrative document. Answers are drawn only from the lease you upload.
        </p>
      </div>
    </section>
  );
}
