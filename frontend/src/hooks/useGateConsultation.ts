/**
 * U1 (tenth review of PR #81; RC-126; DRAFT, PENDING owner approval): ONE consultation of the quality gate with its
 * automatic retries held as STATE — never derived during render from a mutable ref.
 *
 *  - a rate-limited answer schedules exactly ONE timer (the server's wait, with backoff);
 *  - nothing is scheduled and no countdown runs while a request is in flight;
 *  - at most MAX_AUTOMATIC_RETRIES automatic retries per subject (G29);
 *  - "stuck" (the caller shows "Check again") only once the last answer has arrived.
 *
 * The subject is what the answer belongs to (the selected file before the run; the run's result for the final
 * consultation): a new subject starts afresh, and an answer is exposed only for the subject it was asked for (G18, U3).
 */
import { useCallback, useEffect, useReducer, useRef, useState, type Reducer } from 'react';
import { MAX_AUTOMATIC_RETRIES } from '@/services/qualityGate/gate';

interface State<T> {
  subject: unknown;
  seq: number;
  attempt: number;
  inFlight: boolean;
  answer: T | null;
  wait: number | null;
}

type Action<T> =
  | { type: 'start'; subject: unknown }
  | { type: 'retry' }
  | { type: 'again' }
  | { type: 'answer'; seq: number | null; answer: T; base: number | null };

function reducer<T>(s: State<T>, a: Action<T>): State<T> {
  switch (a.type) {
    case 'start':
      return { subject: a.subject, seq: s.seq + 1, attempt: 0, inFlight: a.subject !== null, answer: null, wait: null };
    case 'retry':
      return { ...s, seq: s.seq + 1, attempt: s.attempt + 1, inFlight: true, wait: null };
    case 'again':
      return { ...s, seq: s.seq + 1, attempt: 0, inFlight: true, wait: null };
    case 'answer':
      if (a.seq !== null && a.seq !== s.seq) return s;          // the answer to an older request never acts
      return {
        // M1 (thirteenth review): an answer shown from elsewhere (a newer consultation) supersedes the request in
        // flight — its older answer can never overwrite this one
        ...s, seq: a.seq === null ? s.seq + 1 : s.seq, inFlight: false, answer: a.answer,
        wait: a.base !== null && s.attempt < MAX_AUTOMATIC_RETRIES ? a.base * 2 ** s.attempt : null,
      };
    default:
      return s;
  }
}

/** The seconds left of a wait, counted down once a second; null when nothing is waited for. */
function useCountdown(seconds: number | null, restartOn: unknown): number | null {
  const [left, setLeft] = useState<number | null>(seconds);
  useEffect(() => {
    setLeft(seconds);
    if (seconds === null) return undefined;
    const id = setInterval(() => setLeft((v) => (v === null ? null : Math.max(0, v - 1))), 1000);
    return () => clearInterval(id);
  }, [seconds, restartOn]);
  return left;
}

export interface GateConsultation<T> {
  /** the answer for the current subject, or null while none has arrived */
  answer: T | null;
  /** seconds left before the automatic retry; null when none is scheduled (and always while in flight) */
  left: number | null;
  /** no request in flight, an answer is shown and no automatic retry is left */
  settled: boolean;
  /** ask again now (the physician's "Check again"): the retries start afresh */
  again: () => void;
  /** show an answer obtained elsewhere for this subject (it schedules its retry like any other) */
  show: (answer: T) => void;
}

/**
 * @param subject  what the answer belongs to; null = nothing to ask
 * @param ask      the request for the given subject; resolves to null for an answer that must not act (another file)
 * @param baseOf   the server's wait in seconds when the answer is rate limited, else null
 * @param debounceMs  delay before each request
 */
export function useGateConsultation<T>(subject: unknown, ask: (subject: unknown) => Promise<T | null>,
  baseOf: (answer: T) => number | null, debounceMs = 0): GateConsultation<T> {
  const [state, dispatch] = useReducer<Reducer<State<T>, Action<T>>>(reducer,
    { subject: null, seq: 0, attempt: 0, inFlight: false, answer: null, wait: null });
  const askRef = useRef(ask);
  askRef.current = ask;
  const baseRef = useRef(baseOf);
  baseRef.current = baseOf;

  useEffect(() => { dispatch({ type: 'start', subject }); }, [subject]);

  // the ONE request of the current sequence number
  useEffect(() => {
    if (!state.inFlight || state.subject === null) return undefined;
    let live = true;
    const seq = state.seq;
    const asked = state.subject;                   // M1 (thirteenth review): the subject this request is for
    const send = () => {
      void askRef.current(asked).then((answer) => {
        if (live && answer !== null) dispatch({ type: 'answer', seq, answer, base: baseRef.current(answer) });
      });
    };
    const timer = setTimeout(send, debounceMs);
    return () => { live = false; clearTimeout(timer); };
  }, [state.seq, state.inFlight, state.subject, debounceMs]);

  // ONE timer per rate-limited answer, never while a request is in flight
  useEffect(() => {
    if (state.inFlight || state.wait === null) return undefined;
    const id = setTimeout(() => dispatch({ type: 'retry' }), state.wait * 1000);
    return () => clearTimeout(id);
  }, [state.seq, state.inFlight, state.wait, state.answer]);

  const again = useCallback(() => dispatch({ type: 'again' }), []);    // stable: safe in an effect's dependencies
  const own = state.subject === subject && subject !== null;
  const left = useCountdown(own && !state.inFlight ? state.wait : null, state.answer);
  return {
    answer: own ? state.answer : null,
    left: own && !state.inFlight && state.wait !== null ? left : null,
    settled: own && !state.inFlight && state.answer !== null && state.wait === null,
    again,
    show: (answer: T) => dispatch({ type: 'answer', seq: null, answer, base: baseRef.current(answer) }),
  };
}
