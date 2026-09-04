"use client";

import { useEffect, useState, type ReactNode } from "react";

import {
  SESSION_EXPIRED_EVENT,
  beginSignIn,
  beginSignUp,
  isAuthConfigured,
  isSignedIn,
  signOut,
} from "@/lib/auth";

type SessionStatus = "checking" | "signed-out" | "signed-in" | "local";

function useSessionStatus(): SessionStatus {
  const [status, setStatus] = useState<SessionStatus>(() =>
    isAuthConfigured() ? "checking" : "local",
  );

  useEffect(() => {
    if (!isAuthConfigured()) return;
    let isCurrent = true;

    void isSignedIn().then((signedIn) => {
      if (isCurrent) setStatus(signedIn ? "signed-in" : "signed-out");
    });

    function onSessionExpired() {
      setStatus("signed-out");
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, onSessionExpired);
    return () => {
      isCurrent = false;
      window.removeEventListener(SESSION_EXPIRED_EVENT, onSessionExpired);
    };
  }, []);

  return status;
}

/** Gates access to leases behind Cognito sign-in. Renders children unchanged in local
 * development (no NEXT_PUBLIC_COGNITO_* configured), matching the backend's
 * AUTH_MODE=disabled -- this repository does not provision a live Cognito pool. */
export function AuthGate({ children }: { children: ReactNode }) {
  const status = useSessionStatus();

  if (status === "checking") {
    return (
      <div className="mx-auto mt-16 max-w-md text-center text-sm text-[var(--muted)]">
        Checking your session…
      </div>
    );
  }

  if (status === "signed-out") {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-2xl border border-[var(--line)] bg-white p-8 text-center shadow-[0_18px_60px_rgba(19,43,58,0.08)]">
        <h2 className="font-serif text-2xl text-[var(--navy)]">Sign in to continue</h2>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Your leases are private to your account.
        </p>
        <div className="mt-6 flex flex-col gap-3">
          <button
            type="button"
            onClick={() => void beginSignIn()}
            className="rounded-lg bg-[var(--accent)] px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[var(--accent-dark)]"
          >
            Sign in
          </button>
          <button
            type="button"
            onClick={() => void beginSignUp()}
            className="rounded-lg border border-[var(--line)] px-5 py-2.5 text-sm font-semibold text-[var(--navy)] hover:border-[var(--accent)]"
          >
            Create account
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

export function SignOutButton() {
  const [visible] = useState(() => isAuthConfigured());

  if (!visible) return null;

  return (
    <button
      type="button"
      onClick={() => signOut()}
      className="text-sm font-medium text-[var(--muted)] hover:text-[var(--navy)]"
    >
      Sign out
    </button>
  );
}
