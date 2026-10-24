"""Cost / wall-time guard across Spot attempts and Kaggle sessions (pure functions, unit-tested).

Vertex AI bills a Spot job while its VM runs (not while queued or preempted); after a preemption
the job restarts on a new VM up to six times. Each container start registers an *attempt*
(start time + heartbeats); billed time is estimated as the sum over attempts of
(last heartbeat or end - start) + a fixed start-up allowance (image pull, VM boot before the
container starts). Cost = billed hours x catalogue USD/h x a safety factor (1.15 covers a possible
Vertex premium over the Compute Engine Spot SKUs; PROTOCOL §6).
"""
import datetime

FMT = "%Y-%m-%dT%H:%M:%SZ"


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def to_s(ts):
    return ts.strftime(FMT)


def parse(s):
    return datetime.datetime.strptime(s, FMT)


def attempt_seconds(att, now=None):
    """Seconds an attempt ran: end, else last heartbeat, else (if it is the live one) now."""
    start = parse(att["start_utc"])
    end = att.get("end_utc") or att.get("heartbeat_utc")
    if att.get("live") and now is not None:
        end_dt = now
    else:
        end_dt = parse(end) if end else start
    return max(0.0, (end_dt - start).total_seconds())


def billed_seconds(attempts, now=None, overhead_s=300.0):
    return sum(attempt_seconds(a, now) + overhead_s for a in attempts)


def cost_usd(seconds, rate_usd_per_h, safety=1.15):
    return seconds / 3600.0 * rate_usd_per_h * safety


def decide(attempts, now, rate_usd_per_h, max_cost_usd, max_hours, next_epoch_s,
           reserve_s=600.0, overhead_s=300.0, safety=1.15):
    """None to continue, else the reason to stop BEFORE starting another epoch.

    Stops when finishing one more epoch plus the final reserve (validation, export, uploads) would
    exceed the cost or the hours limit.
    """
    billed = billed_seconds(attempts, now, overhead_s)
    projected = billed + max(0.0, next_epoch_s) + reserve_s
    if cost_usd(projected, rate_usd_per_h, safety) > max_cost_usd:
        return (f"max_cost: projected {cost_usd(projected, rate_usd_per_h, safety):.2f} USD > "
                f"{max_cost_usd:.2f} USD (billed so far {billed / 3600:.2f} h)")
    if projected / 3600.0 > max_hours:
        return f"max_hours: projected {projected / 3600:.2f} h > {max_hours:.2f} h"
    return None


PAUSE_PREFIX = "session_pause"


def session_decide(now, deadline, next_epoch_s, next_is_last, reserve_s=1800.0, session_reserve_s=600.0):
    """None, or the reason to PAUSE (resumable, not a stop) before starting another epoch in this session.

    Kaggle sessions end after at most 12 h; the runner gives each session a soft deadline. Another
    epoch starts only if it and the work after it fit before that deadline: the nnU-Net final
    validation + export (reserve_s) when the next epoch is the last one, else the short hand-over
    (session_reserve_s: records, copying the store to the kernel output).
    """
    if deadline is None:
        return None
    need = max(0.0, next_epoch_s) + (reserve_s if next_is_last else session_reserve_s)
    left = (deadline - now).total_seconds()
    if need > left:
        return (f"{PAUSE_PREFIX}: session deadline {to_s(deadline)}, {left / 60:.1f} min left < "
                f"{need / 60:.1f} min needed (next epoch{' + final validation' if next_is_last else ''})")
    return None


def summary(attempts, now, rate_usd_per_h, overhead_s=300.0, safety=1.15):
    b = billed_seconds(attempts, now, overhead_s)
    return {"attempts": len(attempts), "billed_seconds_estimate": round(b, 1),
            "rate_usd_per_h_list": rate_usd_per_h, "safety_factor": safety,
            "cost_usd_list_estimate": round(cost_usd(b, rate_usd_per_h, 1.0), 4),
            "cost_usd_guard_estimate": round(cost_usd(b, rate_usd_per_h, safety), 4)}
