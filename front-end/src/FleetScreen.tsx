/**
 * Fleet Dashboard screen: every ship as a collapsible section listing all of its bookings,
 * newest first, exactly as the server orders them. Markup, class names, icons and copy follow
 * the approved UI mockups (designed in Claude Design; not part of this repo).
 * Data comes from `api.ts` and every time is formatted by `time.ts`.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { ApiError, getFleet, type FleetShip } from './api'
import { formatDate, formatTimeRange } from './time'

/**
 * The "Fleet Dashboard" screen. It fetches the fleet on mount; the app shows one screen at a
 * time, so each visit to this tab mounts it afresh and shows bookings made since the last one.
 */
export default function FleetScreen() {
  /** `null` while the fleet is loading. */
  const [fleet, setFleet] = useState<FleetShip[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    // `ignore` drops the response of a run React has already cleaned up (StrictMode runs
    // effects twice in development, and the user may switch tabs before the fetch ends).
    let ignore = false
    getFleet()
      .then((data) => {
        if (ignore) return
        // An empty fleet means the seed was not loaded before the server started.
        if (data.length === 0) setLoadError("No ships found. Load the seed data first (see the README's Quick start).")
        else setFleet(data)
      })
      .catch((err: unknown) => {
        if (ignore) return
        // `ApiError` carries the server's explanation; anything else (a network `TypeError`,
        // a malformed-body `SyntaxError`) has a message not meant for people.
        setLoadError(
          err instanceof ApiError ? err.message : 'Could not reach the server. Please try again.',
        )
      })
    return () => {
      ignore = true
    }
  }, [])

  let body: ReactNode
  if (loadError !== null) {
    body = (
      <div className="placeholder" role="alert">
        <p className="placeholder__title">{loadError}</p>
      </div>
    )
  } else if (fleet === null) {
    body = (
      <div className="placeholder" role="status">
        <span className="spinner" aria-hidden="true" />
        <p className="placeholder__title">Loading fleet…</p>
      </div>
    )
  } else {
    body = (
      <div className="ships">
        {fleet.map((ship) => {
          const count = ship.bookings.length
          return (
            <details key={ship.id} className="ship">
              <summary className="ship__summary">
                <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
                  <polyline points="9 6 15 12 9 18" />
                </svg>
                <span className="ship__name">{ship.name}</span>
                <span className="ship__count">
                  · {count} {count === 1 ? 'booking' : 'bookings'}
                </span>
              </summary>
              {count === 0 ? (
                <p className="ship__empty">No bookings yet.</p>
              ) : (
                // A scroll region rather than pagination: ~600 rows per ship scroll under the
                // sticky header. tabIndex lets keyboard users focus it to scroll.
                <div
                  className="table-scroll"
                  tabIndex={0}
                  role="region"
                  aria-label={`${ship.name} bookings`}
                >
                  <table className="table">
                    <caption className="sr-only">{ship.name} bookings, newest first</caption>
                    <thead>
                      <tr>
                        <th className="col-date" scope="col">
                          Date
                        </th>
                        <th className="col-time" scope="col">
                          Time (CT)
                        </th>
                        <th scope="col">Pilot</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ship.bookings.map((booking) => (
                        <tr key={booking.id}>
                          <td className="nowrap">{formatDate(booking.startTime)}</td>
                          <td>{formatTimeRange(booking.startTime, booking.endTime)}</td>
                          <td>{booking.pilotName}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </details>
          )
        })}
      </div>
    )
  }

  return (
    <>
      <div className="page-head">
        <h1 className="page-title">Fleet Dashboard</h1>
        <span className="tz">
          <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <polyline points="12 7 12 12 15 14" />
          </svg>
          <span>All times Central (CT)</span>
        </span>
      </div>
      {body}
    </>
  )
}
