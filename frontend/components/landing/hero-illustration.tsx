"use client";

import { useEffect, useState, type CSSProperties } from "react";

import { useNarrowViewport, usePrefersReducedMotion } from "./hooks";

const ACCENT = "var(--l-accent)";

function Bar({ width, tone }: { width: string; tone: "light" | "dark" }) {
  return (
    <span
      style={{
        display: "block",
        height: 5,
        borderRadius: 1,
        width,
        background: tone === "dark" ? "#DED7CA" : "#E6E0D5",
      }}
    />
  );
}

function ClauseLine({ dim, num, widths, spaced = true }: { dim: number; num: string; widths: string[]; spaced?: boolean }) {
  return (
    <div style={{ display: "flex", gap: 12, marginBottom: spaced ? 20 : 0, transition: "opacity 600ms ease", opacity: dim }}>
      <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 10.5, color: "#C3BBAE", paddingTop: 2 }}>{num}</span>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 7 }}>
        {widths.map((w, i) => (
          <Bar key={i} width={w} tone="light" />
        ))}
      </div>
    </div>
  );
}

export function HeroIllustration() {
  const reducedMotion = usePrefersReducedMotion();
  const narrow = useNarrowViewport();
  const [hero, setHero] = useState(0);

  useEffect(() => {
    if (reducedMotion) return;
    const timers = [
      setTimeout(() => setHero(1), 520),
      setTimeout(() => setHero(2), 1240),
      setTimeout(() => setHero(3), 1900),
    ];
    return () => timers.forEach(clearTimeout);
  }, [reducedMotion]);

  const activeHero = reducedMotion ? 3 : hero;
  const dim = activeHero >= 1 ? 0.5 : 1;
  const clauseLit = activeHero >= 1;
  const clearOpacity = activeHero >= 2 ? 1 : 0;
  const denseOpacity = activeHero >= 2 ? 0 : 1;
  const noteLit = activeHero >= 3;

  const noteStyle: CSSProperties = narrow
    ? { position: "static", marginTop: 12, width: "100%" }
    : { position: "absolute", left: "60%", top: -4, width: "50%", marginTop: 0 };

  return (
    <div style={{ flex: "1 1 430px", minWidth: 0 }}>
      <div style={{ position: "relative", paddingRight: narrow ? 0 : "14%" }}>
        <div
          style={{
            background: "var(--l-surface-alt)",
            border: "1px solid var(--l-line-strong)",
            borderRadius: 2,
            padding: "30px 30px 34px",
            boxShadow: "0 1px 0 rgba(27,26,23,0.04), 0 30px 56px -46px rgba(27,26,23,0.6)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              borderBottom: "1px solid var(--l-line)",
              paddingBottom: 12,
              marginBottom: 20,
            }}
          >
            <span style={{ fontFamily: "var(--font-serif-text)", fontSize: 13.5, color: "var(--l-faint)" }}>
              Residential Tenancy Agreement
            </span>
            <span style={{ fontFamily: "var(--font-mono-editorial)", fontSize: 10.5, color: "#B3AB9E" }}>Page 13</span>
          </div>

          <ClauseLine dim={dim} num="14.1" widths={["100%", "96%", "62%"]} />

          <div
            style={{
              position: "relative",
              display: "flex",
              flexWrap: "wrap",
              gap: 14,
              alignItems: "flex-start",
              margin: "0 -8px 20px",
              padding: "9px 8px",
              transition: "background 560ms ease, box-shadow 560ms ease",
              background: clauseLit ? "rgba(154,91,60,0.12)" : "rgba(154,91,60,0)",
              boxShadow: clauseLit ? `inset 3px 0 0 ${ACCENT}` : "inset 0 0 0 rgba(0,0,0,0)",
            }}
          >
            <span
              style={{
                fontFamily: "var(--font-mono-editorial)",
                fontSize: 10.5,
                paddingTop: 3,
                transition: "color 560ms ease",
                color: clauseLit ? ACCENT : "#C3BBAE",
              }}
            >
              14.2
            </span>
            <div style={{ flex: narrow ? "1 1 100%" : "0 0 54%", minWidth: 0, position: "relative" }}>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 7,
                  paddingTop: 3,
                  transition: "opacity 480ms ease",
                  opacity: denseOpacity,
                }}
              >
                <Bar width="100%" tone="dark" />
                <Bar width="92%" tone="dark" />
                <Bar width="74%" tone="dark" />
              </div>
              <p
                style={{
                  position: "absolute",
                  inset: 0,
                  margin: 0,
                  fontFamily: "var(--font-serif-text)",
                  fontSize: 13.5,
                  lineHeight: 1.62,
                  color: "#2A2721",
                  transition: "opacity 520ms ease",
                  opacity: clearOpacity,
                }}
              >
                No animal shall be kept in or about the Premises without the prior written consent of the Landlord.
              </p>
            </div>
            <div
              style={{
                ...noteStyle,
                minWidth: 200,
                display: "flex",
                alignItems: "flex-start",
                gap: 0,
                transition: "opacity 560ms ease, transform 560ms ease",
                opacity: noteLit ? 1 : 0,
                transform: noteLit ? "none" : narrow ? "translateY(8px)" : "translateX(-10px)",
              }}
            >
              {!narrow && (
                <span style={{ height: 1, width: 22, marginTop: 16, flex: "none", background: ACCENT, display: "block" }} />
              )}
              <div
                style={{
                  flex: 1,
                  minWidth: 0,
                  background: "var(--l-surface)",
                  border: "1px solid var(--l-line-strong)",
                  borderRadius: 2,
                  padding: "13px 15px",
                  boxShadow: "0 16px 30px -26px rgba(27,26,23,0.7)",
                }}
              >
                <p
                  style={{
                    margin: 0,
                    fontFamily: "var(--font-serif-display)",
                    fontStyle: "italic",
                    fontSize: 19,
                    lineHeight: 1.32,
                    color: "var(--l-ink)",
                  }}
                >
                  You need written permission before keeping a pet.
                </p>
                <div
                  style={{
                    marginTop: 10,
                    paddingTop: 9,
                    borderTop: "1px solid var(--l-line)",
                    fontFamily: "var(--font-mono-editorial)",
                    fontSize: 10.5,
                    color: ACCENT,
                  }}
                >
                  Page 13 · Section 14.2
                </div>
              </div>
            </div>
          </div>

          <ClauseLine dim={dim} num="14.3" widths={["98%", "44%"]} />
          <ClauseLine dim={dim} num="14.4" widths={["100%", "88%", "57%"]} spaced={false} />
        </div>
        <div style={{ marginTop: 14, fontFamily: "var(--font-mono-editorial)", fontSize: 11, color: "var(--l-muted)" }}>
          Dense lease, relevant clause, plain language.
        </div>
      </div>
    </div>
  );
}
