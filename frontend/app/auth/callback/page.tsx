"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { handleAuthCallback } from "@/lib/auth";

export default function AuthCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    handleAuthCallback(params)
      .then(() => router.replace("/"))
      .catch((callbackError: unknown) => {
        setError(
          callbackError instanceof Error
            ? callbackError.message
            : "Sign-in could not be completed. Please try again.",
        );
      });
  }, [router]);

  return (
    <main className="grid min-h-screen place-items-center bg-[var(--paper)] px-6 text-center">
      {error ? (
        <div>
          <p className="text-sm text-[var(--error)]">{error}</p>
          <Link
            href="/"
            className="mt-4 inline-block text-sm font-semibold text-[var(--accent)] underline underline-offset-4"
          >
            Return home
          </Link>
        </div>
      ) : (
        <p className="text-sm text-[var(--muted)]">Signing you in…</p>
      )}
    </main>
  );
}
