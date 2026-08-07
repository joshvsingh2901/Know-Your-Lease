import { LeaseUpload } from "@/components/lease-upload";

export default function Home() {
  return (
    <main className="min-h-screen bg-[var(--paper)] text-[var(--ink)]">
      <header className="border-b border-[var(--line)] bg-white/80">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <a href="#main-content" className="flex items-center gap-3" aria-label="Know Your Lease home">
            <span className="grid size-9 place-items-center rounded-lg bg-[var(--navy)] text-sm font-semibold text-white">
              KYL
            </span>
            <span className="text-sm font-semibold tracking-[0.14em] text-[var(--navy)]">
              KNOW YOUR LEASE
            </span>
          </a>
          <span className="hidden text-sm text-[var(--muted)] sm:block">Private document workspace</span>
        </div>
      </header>

      <section id="main-content" className="mx-auto max-w-6xl px-5 pb-20 pt-14 sm:px-8 sm:pt-20">
        <div className="mx-auto max-w-3xl text-center">
          <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">
            Lease clarity starts here
          </p>
          <h1 className="text-balance font-serif text-4xl leading-tight tracking-[-0.025em] text-[var(--navy)] sm:text-6xl">
            Understand the agreement before it becomes a question.
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-pretty text-base leading-7 text-[var(--muted)] sm:text-lg">
            Upload your lease and ask questions with answers linked directly to the relevant clauses.
          </p>
        </div>

        <LeaseUpload />

        <div className="mx-auto mt-8 grid max-w-3xl gap-3 sm:grid-cols-3">
          {[
            ["01", "Upload", "Add your lease as a PDF."],
            ["02", "Review", "We’ll prepare each clause."],
            ["03", "Ask", "Get grounded answers with sources."],
          ].map(([number, title, copy]) => (
            <div key={number} className="border-t border-[var(--line)] px-1 pt-4">
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-xs text-[var(--accent)]">{number}</span>
                <h2 className="font-semibold text-[var(--navy)]">{title}</h2>
              </div>
              <p className="mt-1 pl-8 text-sm leading-6 text-[var(--muted)]">{copy}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-[var(--line)]">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-5 py-6 text-xs text-[var(--muted)] sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <span>Know Your Lease</span>
          <span>Document guidance, grounded in your agreement.</span>
        </div>
      </footer>
    </main>
  );
}
