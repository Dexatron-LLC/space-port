/**
 * Charter a Ship screen: pick a ship, date and duration, choose one of the start times the
 * server offers, enter a pilot name and book. Markup, class names, icons and copy follow the
 * approved design artboards (Main / Charter-mobile / State-* in the Claude Design canvas).
 *
 * The server owns every rule. This screen only shows the slots it is given and posts a chosen
 * slot back; it never computes availability (so it never asks for the full fleet's bookings)
 * and never builds a timestamp. All data goes through `api.ts`, all formatting through `time.ts`.
 */
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { ApiError, createBooking, getAvailability, getShips, type Ship, type Slot } from './api'
import { formatDate, formatTime, formatTimeRange, todayInTimeZone, zoneAbbreviation } from './time'

/** Charter lengths offered in the Duration select, in minutes, with their display labels. */
const DURATIONS: { minutes: number; label: string }[] = [
  { minutes: 30, label: '30 min' },
  { minutes: 60, label: '1 h' },
  { minutes: 90, label: '1 h 30 min' },
  { minutes: 120, label: '2 h' },
  { minutes: 150, label: '2 h 30 min' },
  { minutes: 180, label: '3 h' },
  { minutes: 210, label: '3 h 30 min' },
  { minutes: 240, label: '4 h' },
]

// The design's inline SVG icons. Plain elements (not components), shared where one is used twice.
const chevronDownIcon = (
  <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
    <polyline points="6 9 12 15 18 9" />
  </svg>
)
const checkIcon = (
  <svg className="icon icon--sm" viewBox="0 0 24 24" aria-hidden="true">
    <polyline points="20 6 9 17 4 12" />
  </svg>
)

/**
 * Message for a failed load. `api.ts` throws `ApiError` (with the server's explanation) for
 * HTTP errors, but a network failure surfaces as a raw `TypeError` and a malformed body as a
 * `SyntaxError`, whose messages are not meant for people.
 */
function loadErrorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Could not reach the server. Please try again.'
}

/**
 * The "Charter a Ship" screen: the controls card, the start-times card (slot grid with its
 * loading, empty and error states) and the booking panel form with its result banner.
 */
export default function CharterScreen() {
  const [ships, setShips] = useState<Ship[]>([])
  const [shipId, setShipId] = useState<number | null>(null)
  const [date, setDate] = useState(todayInTimeZone)
  const [duration, setDuration] = useState(60)
  /** `null` while the start times are loading. */
  const [slots, setSlots] = useState<Slot[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Slot | null>(null)
  const [pilotName, setPilotName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [banner, setBanner] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  /** Bumped after a booking attempt to re-fetch the slots for the same inputs. */
  const [reloadKey, setReloadKey] = useState(0)

  // Load the ships once and default to the first one.
  useEffect(() => {
    // `ignore` drops the response of a run React has already cleaned up (StrictMode runs
    // effects twice in development), so state is only set once, from the live run.
    let ignore = false
    getShips()
      .then((list) => {
        if (ignore) return
        setShips(list)
        setShipId(list[0]?.id ?? null)
      })
      .catch((err: unknown) => {
        if (!ignore) setLoadError(loadErrorMessage(err))
      })
    return () => {
      ignore = true
    }
  }, [])

  // Load the start times whenever the inputs change, or after a booking attempt (reloadKey).
  useEffect(() => {
    if (shipId === null) return
    // `ignore` discards out-of-order responses: if the user changes ship, date or duration
    // quickly, an older request can finish after a newer one and must not overwrite it.
    // It also covers StrictMode's double run of effects in development.
    let ignore = false
    getAvailability(shipId, date, duration)
      .then((list) => {
        if (ignore) return
        // An earlier load error is cleared here, not in clearSlots(): if the ships failed to
        // load there is no re-fetch coming, and clearing it would leave a spinner forever.
        setLoadError(null)
        setSlots(list)
      })
      .catch((err: unknown) => {
        if (!ignore) setLoadError(loadErrorMessage(err))
      })
    return () => {
      ignore = true
    }
  }, [shipId, date, duration, reloadKey])

  const shipName = ships.find((ship) => ship.id === shipId)?.name ?? ''
  const durationLabel = DURATIONS.find((d) => d.minutes === duration)?.label ?? `${duration} min`
  const zoneNote =
    slots && slots.length > 0
      ? `All times Central (${zoneAbbreviation(slots[0].start)})`
      : 'All times Central'
  const hasOpenSlot = slots !== null && slots.some((slot) => slot.available)
  const ready = selected !== null && pilotName.trim() !== ''

  /**
   * Drops the shown start times and the selection before they are re-fetched, so the loading
   * state shows and a slot from the old list cannot be booked. It runs from the events that
   * change the effect's inputs (not inside the effect) so React does not render twice.
   */
  function clearSlots() {
    setSlots(null)
    setSelected(null)
  }

  function selectSlot(slot: Slot) {
    // aria-pressed makes each slot a toggle, so pressing the selected one again unselects it.
    setSelected(selected?.start === slot.start ? null : slot)
    setBanner(null)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!ready || submitting || shipId === null || selected === null) return
    // Capture what is being booked now: the inputs may change while the request is in flight.
    const slot = selected
    const pilot = pilotName.trim()
    const ship = shipName
    setSubmitting(true)
    try {
      // The slot's own `start`/`end` strings are posted back verbatim, so the client never
      // builds a timestamp and cannot shift a booking by a time-zone mistake.
      await createBooking({ shipId, pilotName: pilot, startTime: slot.start, endTime: slot.end })
      setBanner({
        kind: 'success',
        text: `${ship}, ${formatTimeRange(slot.start, slot.end)} ${zoneAbbreviation(slot.start)} for ${pilot}`,
      })
      setPilotName('')
      // Re-fetch so the new booking and its refuel buffer show as unavailable.
      clearSlots()
      setReloadKey((key) => key + 1)
    } catch (err) {
      if (err instanceof ApiError) {
        // 409 conflict (someone else got there first), 422 or 404: show the server's reason,
        // keep the pilot name so the user can pick another time, and re-fetch the slots.
        setBanner({ kind: 'error', text: err.message })
        clearSlots()
        setReloadKey((key) => key + 1)
      } else {
        // Network failure or unreadable response: keep everything so the user can retry.
        setBanner({ kind: 'error', text: 'Something went wrong. Please try again.' })
      }
    } finally {
      setSubmitting(false)
    }
  }

  let startTimes: ReactNode
  if (loadError !== null) {
    startTimes = (
      <div className="placeholder" role="alert">
        <p className="placeholder__title">{loadError}</p>
      </div>
    )
  } else if (slots === null) {
    startTimes = (
      <div className="placeholder" role="status">
        <span className="spinner" aria-hidden="true" />
        <p className="placeholder__title">Loading start times…</p>
      </div>
    )
  } else if (!hasOpenSlot) {
    startTimes = (
      <div className="placeholder" role="status">
        <p className="placeholder__title">No start times fit a {durationLabel} charter on this day</p>
        <p className="placeholder__text">Try a shorter duration or another date.</p>
      </div>
    )
  } else {
    startTimes = (
      <>
        <ul className="legend" aria-label="Legend">
          <li>
            <span className="swatch" aria-hidden="true" />
            Open
          </li>
          <li>
            <span className="swatch swatch--taken" aria-hidden="true" />
            Unavailable
          </li>
          <li>
            <span className="swatch swatch--selected" aria-hidden="true">
              {checkIcon}
            </span>
            Selected
          </li>
        </ul>
        <div className="slots" role="group" aria-labelledby="times-h">
          {slots.map((slot) => {
            const isSelected = selected?.start === slot.start
            return (
              <button
                key={slot.start}
                type="button"
                className="slot"
                aria-pressed={isSelected}
                disabled={!slot.available}
                onClick={() => selectSlot(slot)}
              >
                {isSelected && checkIcon}
                <span>{formatTime(slot.start)}</span>
                {!slot.available && <span className="sr-only">, unavailable</span>}
              </button>
            )
          })}
        </div>
      </>
    )
  }

  return (
    <>
      <div className="page-head">
        <h1 className="page-title">Charter a Ship</h1>
      </div>
      <div className="charter">
        <div className="charter__main">
          <section className="card" aria-label="Charter details">
            <div className="controls">
              <div className="field field--wide">
                <label className="label" htmlFor="ship">
                  Ship
                </label>
                <div className="select-wrap">
                  <select
                    id="ship"
                    className="control"
                    value={shipId ?? ''}
                    onChange={(e) => {
                      clearSlots()
                      setShipId(Number(e.target.value))
                    }}
                  >
                    {ships.map((ship) => (
                      <option key={ship.id} value={ship.id}>
                        {ship.name}
                      </option>
                    ))}
                  </select>
                  {chevronDownIcon}
                </div>
              </div>
              <div className="field">
                <label className="label" htmlFor="date">
                  Date
                </label>
                <input
                  id="date"
                  className="control"
                  type="date"
                  value={date}
                  onChange={(e) => {
                    clearSlots()
                    setDate(e.target.value)
                  }}
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="duration">
                  Duration
                </label>
                <div className="select-wrap">
                  <select
                    id="duration"
                    className="control"
                    value={duration}
                    onChange={(e) => {
                      clearSlots()
                      setDuration(Number(e.target.value))
                    }}
                  >
                    {DURATIONS.map((d) => (
                      <option key={d.minutes} value={d.minutes}>
                        {d.label}
                      </option>
                    ))}
                  </select>
                  {chevronDownIcon}
                </div>
              </div>
            </div>
          </section>
          <section className="card" aria-labelledby="times-h">
            <div className="card-head">
              <h2 className="h2" id="times-h">
                Start times
              </h2>
              <span className="tz">
                <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="12" cy="12" r="9" />
                  <polyline points="12 7 12 12 15 14" />
                </svg>
                <span>{zoneNote}</span>
              </span>
            </div>
            {startTimes}
          </section>
        </div>
        <form className="card panel" aria-labelledby="booking-h" onSubmit={handleSubmit}>
          <h2 className="h2" id="booking-h">
            Booking
          </h2>
          {banner?.kind === 'success' && (
            <div className="banner banner--success" role="status">
              <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="12" r="9" />
                <polyline points="8 12.5 11 15.5 16 9.5" />
              </svg>
              <p>
                <strong>Booked:</strong> {banner.text}
              </p>
            </div>
          )}
          {banner?.kind === 'error' && (
            <div className="banner banner--error" role="alert">
              <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 3.5 L21.5 20 H2.5 Z" />
                <line x1="12" y1="10" x2="12" y2="14" />
                <line x1="12" y1="17" x2="12" y2="17.01" />
              </svg>
              <p>{banner.text}</p>
            </div>
          )}
          <div className="summary">
            <span className="summary__label">Selected slot</span>
            {selected ? (
              <span className="summary__value">
                {shipName} · {formatDate(selected.start)} ·{' '}
                {formatTimeRange(selected.start, selected.end)} {zoneAbbreviation(selected.start)}
              </span>
            ) : (
              <span className="summary__value summary__value--empty">No start time selected</span>
            )}
          </div>
          <div className="field">
            <label className="label" htmlFor="pilot">
              Pilot name
            </label>
            <input
              id="pilot"
              className="control"
              type="text"
              maxLength={100}
              value={pilotName}
              onChange={(e) => setPilotName(e.target.value)}
            />
          </div>
          <button
            type="submit"
            className="btn"
            disabled={!ready || submitting}
            aria-describedby={ready ? undefined : 'book-hint'}
          >
            {submitting ? 'Booking…' : 'Book charter'}
          </button>
          {!ready && (
            <p className="hint" id="book-hint">
              Choose a start time and enter a pilot name.
            </p>
          )}
        </form>
      </div>
    </>
  )
}
