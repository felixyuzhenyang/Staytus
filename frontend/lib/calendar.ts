import type { Connection } from "./types";

export function canWriteCalendar(connection?: Connection): boolean {
  if (!connection?.connected) return false;
  if (typeof connection.calendar_write === "boolean") return connection.calendar_write;
  if (connection.provider === "icloud") return false;
  return (connection.scopes || []).some(scope => [
    "https://www.googleapis.com/auth/calendar.events.owned",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar",
    "https://graph.microsoft.com/Calendars.ReadWrite",
    "Calendars.ReadWrite",
    "icloud.calendar.write",
  ].includes(scope));
}

export function canReadMail(connection?: Connection): boolean {
  return !!connection?.connected && (connection.scopes || []).some(scope => [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify", "https://mail.google.com/",
    "https://graph.microsoft.com/Mail.Read", "https://graph.microsoft.com/Mail.ReadWrite",
    "Mail.Read", "Mail.ReadWrite",
  ].includes(scope));
}
