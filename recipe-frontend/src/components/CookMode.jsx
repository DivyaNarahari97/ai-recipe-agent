import { useEffect, useRef, useState } from "react";
import { findDurations, formatClock } from "../cookTimers";

const PROGRESS_PREFIX = "recipe-assistant:cook:";
const RING_EVERY_MS = 4000;

function flattenSteps(recipe) {
  return (recipe.instructions || []).flatMap((section) =>
    (section.steps || []).map((text) => ({ section: section.section, text }))
  );
}

// Checked-off steps are remembered per recipe in this browser, so a reload mid-cook doesn't lose them.
function loadProgress(key, stepCount) {
  try {
    const saved = JSON.parse(window.localStorage.getItem(key) ?? "null");
    if (saved?.stepCount === stepCount) {
      return { done: new Set(saved.done), index: Math.min(saved.index ?? 0, stepCount - 1) };
    }
  } catch {
    // Unreadable or blocked storage: start fresh.
  }
  return { done: new Set(), index: 0 };
}

function saveProgress(key, stepCount, done, index) {
  try {
    if (done.size === 0 && index === 0) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify({ stepCount, done: [...done], index }));
  } catch {
    // Storage blocked: progress lasts for this visit only.
  }
}

// Keeps the screen on while cooking. Browsers drop the lock when the tab is hidden, so take it again on return.
function useWakeLock() {
  const supported = typeof navigator !== "undefined" && "wakeLock" in navigator;
  const [status, setStatus] = useState(supported ? "pending" : "unsupported");

  useEffect(() => {
    if (!supported) return undefined;
    let lock = null;
    let active = true;

    const acquire = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const next = await navigator.wakeLock.request("screen");
        if (!active) {
          next.release();
          return;
        }
        lock = next;
        setStatus("on");
        next.addEventListener("release", () => {
          if (active) setStatus("off");
        });
      } catch {
        if (active) setStatus("off");
      }
    };

    acquire();
    const onVisibility = () => acquire();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      active = false;
      document.removeEventListener("visibilitychange", onVisibility);
      lock?.release().catch(() => {});
    };
  }, [supported]);

  return status;
}

function beep(audio) {
  if (!audio) return;
  const start = audio.currentTime;
  for (let i = 0; i < 3; i += 1) {
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.0001, start + i * 0.35);
    gain.gain.exponentialRampToValueAtTime(0.3, start + i * 0.35 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + i * 0.35 + 0.25);
    osc.connect(gain).connect(audio.destination);
    osc.start(start + i * 0.35);
    osc.stop(start + i * 0.35 + 0.3);
  }
}

function remainingSeconds(timer, now) {
  if (timer.finished) return 0;
  return timer.endsAt ? Math.max(0, (timer.endsAt - now) / 1000) : timer.remaining;
}

function StepText({ text, stepIndex, timers, onStartTimer }) {
  const durations = findDurations(text);
  if (durations.length === 0) return text;

  const parts = [];
  let cursor = 0;
  durations.forEach((d) => {
    parts.push(text.slice(cursor, d.start));
    const running = timers.some((t) => t.stepIndex === stepIndex && t.label === d.label && !t.finished);
    parts.push(
      <button
        key={d.start}
        type="button"
        className={`cook-time-button${running ? " is-running" : ""}`}
        onClick={() => onStartTimer(stepIndex, d)}
        disabled={running}
        aria-label={running ? `${d.label} timer running` : `Start a ${d.label} timer`}
      >
        ⏱ {text.slice(d.start, d.end)}
      </button>
    );
    cursor = d.end;
  });
  parts.push(text.slice(cursor));
  return parts;
}

function TimerTray({ timers, now, onToggle, onAddMinute, onRemove }) {
  if (timers.length === 0) return null;
  return (
    <section className="cook-timers" aria-label="Timers">
      {timers.map((t) => (
        <div key={t.id} className={`cook-timer${t.finished ? " is-done" : ""}`} role={t.finished ? "alert" : undefined}>
          <div className="cook-timer-info">
            <span className="cook-timer-clock">{t.finished ? "Done!" : formatClock(remainingSeconds(t, now))}</span>
            <span className="cook-timer-label">
              Step {t.stepIndex + 1} · {t.label}
            </span>
          </div>
          <div className="cook-timer-actions">
            {!t.finished && (
              <button type="button" onClick={() => onToggle(t.id)}>
                {t.endsAt ? "Pause" : "Resume"}
              </button>
            )}
            <button type="button" onClick={() => onAddMinute(t.id)}>
              +1 min
            </button>
            <button type="button" onClick={() => onRemove(t.id)}>
              {t.finished ? "Dismiss" : "Cancel"}
            </button>
          </div>
        </div>
      ))}
    </section>
  );
}

export default function CookMode({ recipe, scale, onExit }) {
  const steps = flattenSteps(recipe);
  const progressKey = `${PROGRESS_PREFIX}${recipe.id ?? recipe.name}`;
  const [initial] = useState(() => loadProgress(progressKey, steps.length));
  const [index, setIndex] = useState(initial.index);
  const [done, setDone] = useState(initial.done);
  const [timers, setTimers] = useState([]);
  const [now, setNow] = useState(() => Date.now());
  const audioRef = useRef(null);
  const nextTimerId = useRef(1);
  const wakeLock = useWakeLock();

  const allDone = steps.length > 0 && done.size === steps.length;
  const ringing = timers.some((t) => t.finished);
  const running = timers.some((t) => t.endsAt && !t.finished);

  useEffect(() => {
    saveProgress(progressKey, steps.length, done, index);
  }, [progressKey, steps.length, done, index]);

  // Tick while any timer runs; times come from the clock, so a throttled background tab stays accurate.
  useEffect(() => {
    if (!running) return undefined;
    const id = setInterval(() => {
      const t = Date.now();
      setNow(t);
      setTimers((prev) =>
        prev.some((x) => x.endsAt && !x.finished && x.endsAt <= t)
          ? prev.map((x) => (x.endsAt && !x.finished && x.endsAt <= t ? { ...x, finished: true, endsAt: null } : x))
          : prev
      );
    }, 250);
    return () => clearInterval(id);
  }, [running]);

  // A finished timer keeps beeping until it's dismissed or extended, like a kitchen timer.
  useEffect(() => {
    if (!ringing) return undefined;
    const ring = () => {
      beep(audioRef.current);
      navigator.vibrate?.([300, 150, 300]);
    };
    ring();
    const id = setInterval(ring, RING_EVERY_MS);
    const title = document.title;
    document.title = "⏰ Timer done";
    return () => {
      clearInterval(id);
      document.title = title;
    };
  }, [ringing]);

  useEffect(() => {
    const onKey = (event) => {
      if (event.target.closest?.("input, textarea, select")) return;
      if (event.key === "ArrowRight") setIndex((i) => Math.min(i + 1, steps.length - 1));
      if (event.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [steps.length]);

  const toggleDone = (i) =>
    setDone((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  const finishStep = () => {
    setDone((prev) => new Set(prev).add(index));
    // Go to the next step that isn't checked off yet, if any.
    const after = steps.findIndex((_, i) => i > index && !done.has(i));
    if (after !== -1) setIndex(after);
  };

  const startTimer = (stepIndex, duration) => {
    // Browsers only allow sound after a tap, so set up audio here.
    if (!audioRef.current && window.AudioContext) audioRef.current = new window.AudioContext();
    audioRef.current?.resume?.();
    const id = nextTimerId.current++;
    setNow(Date.now());
    setTimers((prev) => [
      ...prev,
      { id, stepIndex, label: duration.label, endsAt: Date.now() + duration.seconds * 1000, remaining: duration.seconds, finished: false },
    ]);
  };

  const toggleTimer = (id) =>
    setTimers((prev) =>
      prev.map((t) => {
        if (t.id !== id || t.finished) return t;
        return t.endsAt
          ? { ...t, endsAt: null, remaining: remainingSeconds(t, Date.now()) }
          : { ...t, endsAt: Date.now() + t.remaining * 1000 };
      })
    );

  const addMinute = (id) => {
    setNow(Date.now());
    setTimers((prev) =>
      prev.map((t) => {
        if (t.id !== id) return t;
        if (t.finished) return { ...t, finished: false, endsAt: Date.now() + 60000, remaining: 60 };
        return t.endsAt ? { ...t, endsAt: t.endsAt + 60000 } : { ...t, remaining: t.remaining + 60 };
      })
    );
  };

  const removeTimer = (id) => setTimers((prev) => prev.filter((t) => t.id !== id));

  const startOver = () => {
    setDone(new Set());
    setIndex(0);
  };

  const exit = () => {
    if (timers.some((t) => !t.finished) && !window.confirm("Leaving cook mode stops your timers. Leave anyway?")) return;
    onExit();
  };

  if (steps.length === 0) {
    return (
      <main className="cook-page">
        <section className="empty-state">
          <h2>This recipe has no steps to cook through</h2>
          <button type="button" className="secondary-button" onClick={onExit}>
            Back to recipe
          </button>
        </section>
      </main>
    );
  }

  const step = steps[index];
  const wakeText = {
    on: "Screen stays on",
    pending: "Keeping screen on…",
    off: "Screen may turn off",
    unsupported: "This browser can't keep the screen on",
  }[wakeLock];

  return (
    <main className="cook-page">
      <header className="cook-header">
        <button type="button" className="secondary-button" onClick={exit}>
          ✕ Exit cook mode
        </button>
        <span className={`cook-wake is-${wakeLock}`}>{wakeText}</span>
      </header>

      <h1 className="cook-title">{recipe.name}</h1>

      <div className="cook-progress">
        <div
          className="cook-progress-bar"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={steps.length}
          aria-valuenow={done.size}
          aria-label="Steps done"
        >
          <span style={{ width: `${(done.size / steps.length) * 100}%` }} />
        </div>
        <span>
          Step {index + 1} of {steps.length} · {done.size} done
        </span>
      </div>

      {recipe.ingredients?.length > 0 && (
        <details className="cook-ingredients">
          <summary>
            Ingredients ({recipe.ingredients.length})
            {scale && scale.factor !== 1 && ` · for ${scale.servings} servings`}
          </summary>
          <ul>
            {recipe.ingredients.map((item, i) => (
              <li key={`${item.name}-${i}`}>
                {scale ? scale.quantity(item) : item.quantity} {item.name}
              </li>
            ))}
          </ul>
          {scale && scale.factor !== 1 && (
            <p className="cook-scaled-note">The steps still give amounts for {recipe.servings} servings.</p>
          )}
        </details>
      )}

      {allDone && (
        <section className="cook-finished" role="status">
          <h2>All steps done. Enjoy your meal!</h2>
          <div className="cook-finished-actions">
            <button type="button" className="secondary-button" onClick={exit}>
              Back to recipe
            </button>
            <button type="button" className="link-button" onClick={startOver}>
              Start over
            </button>
          </div>
        </section>
      )}

      <section className={`cook-step${done.has(index) ? " is-done" : ""}`} aria-live="polite">
        {step.section && <p className="cook-section">{step.section}</p>}
        <p className="cook-step-text">
          <StepText text={step.text} stepIndex={index} timers={timers} onStartTimer={startTimer} />
        </p>
        <label className="cook-check">
          <input type="checkbox" checked={done.has(index)} onChange={() => toggleDone(index)} />
          Step done
        </label>
      </section>

      <nav className="cook-nav" aria-label="Steps">
        <button type="button" className="secondary-button" disabled={index === 0} onClick={() => setIndex(index - 1)}>
          ← Back
        </button>
        {done.has(index) ? (
          <button
            type="button"
            className="cook-next"
            disabled={index === steps.length - 1}
            onClick={() => setIndex(index + 1)}
          >
            Next step →
          </button>
        ) : (
          <button type="button" className="cook-next" onClick={finishStep}>
            {index === steps.length - 1 ? "Done ✓" : "Done, next step →"}
          </button>
        )}
      </nav>

      <details className="cook-overview">
        <summary>All steps</summary>
        <ol>
          {steps.map((s, i) => (
            <li key={i} className={`${i === index ? "is-current" : ""}${done.has(i) ? " is-done" : ""}`}>
              <input
                type="checkbox"
                checked={done.has(i)}
                onChange={() => toggleDone(i)}
                aria-label={`Step ${i + 1} done`}
              />
              <button type="button" className="cook-overview-step" onClick={() => setIndex(i)}>
                {s.text}
              </button>
            </li>
          ))}
        </ol>
      </details>

      <TimerTray timers={timers} now={now} onToggle={toggleTimer} onAddMinute={addMinute} onRemove={removeTimer} />
    </main>
  );
}
