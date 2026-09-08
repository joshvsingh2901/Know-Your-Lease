import Link from "next/link";

import { SignOutButton } from "@/components/auth-gate";
import { HeroIllustration } from "@/components/landing/hero-illustration";
import { ProductDemo } from "@/components/landing/product-demo";
import { landingFontVariables } from "@/lib/fonts";

export default function Home() {
  return (
    <main className={`landing ${landingFontVariables}`} style={{ minHeight: "100vh" }}>
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 20,
          background: "rgba(246,243,237,0.92)",
          backdropFilter: "blur(8px)",
          borderBottom: "1px solid var(--l-line)",
        }}
      >
        <div
          style={{
            maxWidth: 1120,
            margin: "0 auto",
            padding: "0 24px",
            height: 60,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 24,
          }}
        >
          <a href="#top" style={{ display: "flex", alignItems: "center", gap: 10 }} aria-label="Know Your Lease home">
            <span
              aria-hidden="true"
              style={{
                width: 15,
                height: 19,
                border: "1.5px solid var(--l-ink)",
                borderRadius: 1,
                display: "block",
                background: "var(--l-surface-alt)",
              }}
            />
            <span style={{ fontFamily: "var(--font-serif-display)", fontSize: 20, letterSpacing: "-0.005em" }}>
              Know Your Lease
            </span>
          </a>
          <nav style={{ display: "flex", alignItems: "center", gap: 26, fontSize: 14, color: "var(--l-text)" }}>
            <a href="#demo" style={{ color: "var(--l-text)" }}>
              How it works
            </a>
            <Link href="/documents" style={{ color: "var(--l-text)" }}>
              Documents
            </Link>
            <SignOutButton />
            <Link
              href="/documents"
              style={{
                display: "inline-flex",
                alignItems: "center",
                height: 34,
                padding: "0 16px",
                border: "1px solid var(--l-ink)",
                borderRadius: 2,
                background: "var(--l-ink)",
                color: "var(--l-surface)",
                fontSize: 14,
                fontWeight: 500,
              }}
            >
              Get started
            </Link>
          </nav>
        </div>
      </header>

      <section id="top" style={{ maxWidth: 1120, margin: "0 auto", padding: "72px 24px 64px" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 56, alignItems: "center" }}>
          <div style={{ flex: "1 1 400px", minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
              <span style={{ width: 18, height: 1, background: "var(--l-accent)" }} />
              <span
                style={{
                  fontFamily: "var(--font-mono-editorial)",
                  fontSize: 12,
                  letterSpacing: "0.02em",
                  color: "var(--l-accent)",
                }}
              >
                For first-time renters
              </span>
            </div>
            <h1
              style={{
                fontFamily: "var(--font-serif-display)",
                fontWeight: 400,
                fontSize: "clamp(42px, 5.6vw, 68px)",
                lineHeight: 1.02,
                letterSpacing: "-0.012em",
                margin: 0,
              }}
            >
              Understand your lease
              <br />
              <em style={{ fontStyle: "italic", color: "var(--l-ink-soft)" }}>before you sign.</em>
            </h1>
            <p style={{ margin: "24px 0 0", maxWidth: "46ch", fontSize: 17, lineHeight: 1.55, color: "var(--l-text)" }}>
              Ask questions about your rental agreement and find the exact clauses behind the answers.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, marginTop: 34 }}>
              <Link
                href="/documents"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  height: 44,
                  padding: "0 22px",
                  background: "var(--l-ink)",
                  color: "var(--l-surface)",
                  border: "1px solid var(--l-ink)",
                  borderRadius: 2,
                  fontSize: 15,
                  fontWeight: 500,
                }}
              >
                Get started
              </Link>
              <a
                href="#demo"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  height: 44,
                  padding: "0 20px",
                  border: "1px solid var(--l-line-strong)",
                  borderRadius: 2,
                  background: "transparent",
                  color: "var(--l-ink)",
                  fontSize: 15,
                }}
              >
                See how it works
              </a>
            </div>
          </div>
          <HeroIllustration />
        </div>
      </section>

      <ProductDemo />

      <section id="close" style={{ borderTop: "1px solid var(--l-line)" }}>
        <div
          style={{
            maxWidth: 1120,
            margin: "0 auto",
            padding: "76px 24px 84px",
            display: "flex",
            flexWrap: "wrap",
            gap: 40,
            alignItems: "flex-end",
          }}
        >
          <div style={{ flex: "1 1 420px", minWidth: 0 }}>
            <h2
              style={{
                fontFamily: "var(--font-serif-display)",
                fontWeight: 400,
                fontSize: "clamp(30px, 3.6vw, 42px)",
                lineHeight: 1.1,
                letterSpacing: "-0.01em",
                margin: 0,
                maxWidth: "22ch",
              }}
            >
              Your lease stays where you left it, and so does the <em style={{ fontStyle: "italic" }}>evidence</em>.
            </h2>
            <p style={{ margin: "18px 0 0", maxWidth: "52ch", fontSize: 16, lineHeight: 1.55, color: "var(--l-text)" }}>
              Come back to any document, re-read the clause behind an answer, and check the source yourself.
            </p>
          </div>
          <Link
            href="/documents"
            style={{
              display: "inline-flex",
              alignItems: "center",
              height: 46,
              padding: "0 24px",
              background: "var(--l-ink)",
              color: "var(--l-surface)",
              borderRadius: 2,
              fontSize: 15,
              fontWeight: 500,
              whiteSpace: "nowrap",
            }}
          >
            Get started
          </Link>
        </div>
      </section>

      <footer style={{ borderTop: "1px solid var(--l-line)", background: "var(--l-paper-alt)" }}>
        <div
          style={{
            maxWidth: 1120,
            margin: "0 auto",
            padding: "28px 24px 40px",
            display: "flex",
            flexWrap: "wrap",
            gap: 20,
            alignItems: "baseline",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", flexWrap: "wrap", gap: 22, fontSize: 13.5, color: "var(--l-text)" }}>
            <span style={{ fontFamily: "var(--font-serif-display)", fontSize: 17, color: "var(--l-ink)" }}>Know Your Lease</span>
            <a href="#demo" style={{ color: "var(--l-text)" }}>
              How it works
            </a>
            <Link href="/documents" style={{ color: "var(--l-text)" }}>
              Documents
            </Link>
            <a href="#top" style={{ color: "var(--l-text)" }}>
              Privacy
            </a>
            <a href="#top" style={{ color: "var(--l-text)" }}>
              Contact
            </a>
          </div>
          <p style={{ margin: 0, fontFamily: "var(--font-mono-editorial)", fontSize: 11.5, color: "var(--l-muted)", maxWidth: "44ch", lineHeight: 1.6 }}>
            Not legal advice. Know Your Lease helps you read your own document; it does not review, negotiate, or advise on it.
          </p>
        </div>
      </footer>
    </main>
  );
}
