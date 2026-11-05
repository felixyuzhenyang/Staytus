"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import type { AuthState, Profile } from "@/lib/types";

export function useSession() {
  const [session, setSession] = useState<AuthState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const epoch = useRef(0);
  const request = useRef<AbortController | null>(null);

  const restore = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const generation = ++epoch.current;
    setLoading(true); setError("");
    try {
      const result = await api<AuthState>("auth/me", { signal: controller.signal });
      if (!controller.signal.aborted && generation === epoch.current) setSession(result);
    } catch (problem) {
      if (controller.signal.aborted || generation !== epoch.current) return;
      setSession(null);
      if (!(problem instanceof ApiError && problem.status === 401)) setError(problem instanceof Error ? problem.message : "Unable to restore your session.");
    } finally {
      if (!controller.signal.aborted && generation === epoch.current) setLoading(false);
    }
  }, []);

  useEffect(() => { void restore(); return () => { ++epoch.current; request.current?.abort(); }; }, [restore]);

  function acceptSession(next: AuthState) { ++epoch.current; request.current?.abort(); setSession(next); setError(""); setLoading(false); }
  function expireSession() { ++epoch.current; request.current?.abort(); setSession(null); setError(""); setLoading(false); }
  function updateProfile(profile: Profile) { setSession(current => current ? { ...current, account: { ...current.account, name: profile.name }, profile, needs_onboarding: false } : null); }
  async function logout() {
    try { await api("auth/logout", { method: "POST", body: "{}" }); } finally { expireSession(); }
  }
  return { session, loading, error, restore, acceptSession, updateProfile, expireSession, logout };
}
