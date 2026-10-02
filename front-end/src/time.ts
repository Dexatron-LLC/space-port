/**
 * Display helpers for times. This is the ONLY file that names the time zone.
 * The API returns timestamps as ISO strings; the client never builds or shifts them,
 * it only formats them for people.
 */

/**
 * The spaceport's booking rules are in Central Time, so every displayed time is
 * Central regardless of the viewer's own zone.
 */
export const TIME_ZONE = 'America/Chicago'

const timeFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: TIME_ZONE,
  hour: 'numeric',
  minute: '2-digit',
})

/** Splits a formatted time into its parts, e.g. `{ clock: '8:00', period: 'AM' }`. */
function timeParts(iso: string): { clock: string; period: string } {
  const parts = timeFormat.formatToParts(new Date(iso))
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? ''
  return { clock: `${get('hour')}:${get('minute')}`, period: get('dayPeriod') }
}

/** Formats an instant as a Central clock time, e.g. `"8:00 AM"`. */
export function formatTime(iso: string): string {
  const { clock, period } = timeParts(iso)
  return `${clock} ${period}`
}

/**
 * Formats a start/end pair as a range. The AM/PM is shown once when both ends
 * share it (`"8:00–9:00 AM"`), otherwise on both (`"11:00 AM–12:30 PM"`).
 */
export function formatTimeRange(startIso: string, endIso: string): string {
  const start = timeParts(startIso)
  const end = timeParts(endIso)
  if (start.period === end.period) {
    return `${start.clock}–${end.clock} ${end.period}`
  }
  return `${start.clock} ${start.period}–${end.clock} ${end.period}`
}

/** The Central zone abbreviation in effect at that instant: `"CDT"` or `"CST"`. */
export function zoneAbbreviation(iso: string): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: TIME_ZONE,
    timeZoneName: 'short',
  }).formatToParts(new Date(iso))
  return parts.find((p) => p.type === 'timeZoneName')?.value ?? ''
}

const dateFormat = new Intl.DateTimeFormat('en-GB', {
  timeZone: TIME_ZONE,
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

/** Formats an instant as a Central calendar date, e.g. `"Mon 5 Oct 2026"`. */
export function formatDate(iso: string): string {
  // en-GB inserts a comma after the weekday ("Mon, 5 Oct 2026"); drop it.
  return dateFormat.format(new Date(iso)).replace(',', '')
}

const todayFormat = new Intl.DateTimeFormat('en-CA', {
  timeZone: TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

/** Today's date in Central as `"YYYY-MM-DD"` (the `en-CA` locale formats that way). */
export function todayInTimeZone(): string {
  return todayFormat.format(new Date())
}
