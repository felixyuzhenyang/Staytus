import type { Approval } from "./types";

export type ActionOutcome = {
  title: string; message: string; badge: string;
  tone: "green" | "blue" | "amber" | "red";
  icon: "success" | "download" | "warning" | "error" | "pending";
};
export function calendarName(provider: unknown) {
  return provider === "google" ? "Google Calendar" : provider === "microsoft" ? "Outlook Calendar"
    : provider === "icloud" ? "iCloud Calendar" : provider === "export" ? "Calendar file (.ics)" : "Connected calendar";
}
export function reminderText(value: unknown): string | null {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0 || value > 40320) return null;
  if (value === 0) return "On the date";
  const [amount, unit] = value % 10080 === 0 ? [value / 10080, "week"]
    : value % 1440 === 0 ? [value / 1440, "day"] : value % 60 === 0 ? [value / 60, "hour"] : [value, "minute"];
  return `${amount} ${unit}${amount === 1 ? "" : "s"} before`;
}
export function actionOutcome(approval: Approval): ActionOutcome | null {
  const mode = approval.receipt?.mode;
  if (["FAILED_UNCONFIRMED", "UNCONFIRMED"].includes(approval.status) || mode === "provider_unconfirmed") {
    const message = approval.kind === "calendar"
      ? (approval.payload.provider || "export") === "export" ? "Refresh the Action inbox to check whether the calendar file is ready."
        : "Check your calendar before creating another reminder, to avoid a duplicate event."
      : approval.kind === "email" ? "Check your mailbox drafts before preparing this action again." : "Refresh the Action inbox to check the latest status before trying again.";
    return { title: "Result not confirmed", badge: "Needs checking", message, tone: "amber", icon: "warning" };
  }
  if (approval.status === "EXECUTING") return { title: "Action in progress", badge: "In progress", message: "The result is not available yet. Check the Action inbox for the latest status.", tone: "blue", icon: "pending" };
  if (approval.status === "FAILED") return { title: "Action failed", badge: "Failed", message: "Review the action status and connection before preparing a new request.", tone: "red", icon: "error" };
  if (approval.status === "SUCCEEDED") {
    if (approval.kind === "calendar" && mode === "file_export") return {
      title: "Calendar file ready", badge: "Ready to download", tone: "blue", icon: "download",
      message: "Download the file and import it into your calendar. The reminder has not been added to a connected calendar.",
    };
    if (approval.kind === "calendar" && mode === "provider_calendar") {
      const provider = approval.receipt?.provider || approval.payload.provider;
      return { title: provider === "google" || provider === "microsoft" || provider === "icloud" ? `Added to ${calendarName(provider)}` : "Calendar event created",
        badge: "Added to calendar", message: "Your calendar service confirmed that the reminder was created.", tone: "green", icon: "success" };
    }
    if (approval.kind === "email" && mode === "provider_draft") return { title: "Email draft created", badge: "Draft created", message: "Open your mailbox to review the draft. No email was sent.", tone: "green", icon: "success" };
    if (approval.kind === "profile_update") return { title: "Profile updated", badge: "Saved", message: "Your approved profile changes have been saved.", tone: "green", icon: "success" };
    return { title: "Action completed", badge: "Completed", message: "The action was marked complete. Review its approved details below.", tone: "blue", icon: "success" };
  }
  return approval.receipt ? { title: "Result unavailable", badge: "Needs checking", message: "Check the Action inbox for the latest result.", tone: "amber", icon: "warning" } : null;
}
