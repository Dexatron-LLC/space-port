/**
 * Typed client for the Spaceport API. This is the ONLY file that calls `fetch`.
 * It mirrors the server's frozen JSON contract and does no rule logic: the server
 * decides availability and conflicts, the client just shows the result.
 * Paths are relative (`/api/...`); the Vite dev proxy forwards them to the back-end.
 */

/** A charter ship. */
export type Ship = { id: number; name: string }

/** A stored booking. `startTime`/`endTime` are ISO timestamps from the server. */
export type Booking = {
  id: number
  shipId: number
  pilotName: string
  startTime: string
  endTime: string
}

/** One candidate start time. Post `start`/`end` back verbatim when booking. */
export type Slot = { start: string; end: string; available: boolean }

/** A ship together with all of its bookings (fleet dashboard row). */
export type FleetShip = Ship & { bookings: Booking[] }

/** Request body for creating a booking. */
export type NewBooking = {
  shipId: number
  pilotName: string
  startTime: string
  endTime: string
}

/** Thrown for any non-2xx response; `message` is the server's explanation, ready to show. */
export class ApiError extends Error {
  /** HTTP status code (e.g. 409 for a booking conflict). */
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Builds a readable message from FastAPI's `detail` (string, or a list of validation errors). */
function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d as { msg?: unknown } | null)?.msg)
      .filter((m): m is string => typeof m === 'string')
    if (msgs.length > 0) return msgs.join('; ')
  }
  return fallback
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let body: unknown = null
    try {
      body = await res.json()
    } catch {
      // Non-JSON error body: fall back to the status text.
    }
    throw new ApiError(res.status, errorMessage(body, res.statusText))
  }
  return (await res.json()) as T
}

/** Lists all ships. */
export function getShips(): Promise<Ship[]> {
  return request<Ship[]>('/api/ships')
}

/** Lists every start-time slot for a ship on a date (`YYYY-MM-DD`) and charter length. */
export function getAvailability(
  shipId: number,
  date: string,
  durationMinutes: number,
): Promise<Slot[]> {
  const query = new URLSearchParams({ date, durationMinutes: String(durationMinutes) })
  return request<Slot[]>(`/api/ships/${shipId}/availability?${query}`)
}

/** Creates a booking. Rejects with an `ApiError` (409 on conflict, 422 on invalid input). */
export function createBooking(body: NewBooking): Promise<Booking> {
  return request<Booking>('/api/bookings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/** Lists every ship with its bookings, for the fleet dashboard. */
export function getFleet(): Promise<FleetShip[]> {
  return request<FleetShip[]>('/api/fleet')
}
