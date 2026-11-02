"use client";

import { useSession } from "@/hooks/useSession";
import AuthScreen from "@/components/AuthScreen";
import Onboarding from "@/components/Onboarding";
import Workspace from "@/components/Workspace";
import { Loading } from "@/components/ui";

export default function Home() {
  const session = useSession();
  if (session.loading) return <main className="session-loading" aria-busy="true"><Loading text="Restoring your session…" /></main>;
  if (!session.session) return <AuthScreen onAuthenticated={session.acceptSession} initialError={session.error} onRetry={() => void session.restore()} />;
  const { account, profile, role, needs_onboarding } = session.session;
  if (needs_onboarding || !profile) return <Onboarding key={account.id} account={account} onComplete={session.updateProfile} onLogout={session.logout} />;
  return <Workspace key={account.id} account={account} profile={profile} role={role || "student"} onLogout={session.logout} onSessionExpired={session.expireSession} onProfileUpdated={session.updateProfile} />;
}
