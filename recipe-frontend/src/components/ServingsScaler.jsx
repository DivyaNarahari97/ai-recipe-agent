import { UNIT_SYSTEMS } from "../quantities";

// Servings slider (with − / + for precise taps) and a unit-system switch.
function ServingsScaler({ scale, originalServings, onServingsChange, onSystemChange }) {
  const { base, servings, system } = scale;
  const max = base ? Math.max(12, base * 3) : 0;
  const set = (value) => onServingsChange(Math.min(max, Math.max(1, value)));

  return (
    <section className="scaler" aria-label="Servings and units">
      {base ? (
        <div className="scaler-servings">
          <div className="scaler-row">
            <label htmlFor="scaler-range" className="scaler-label">
              Servings
            </label>
            <div className="scaler-stepper">
              <button
                type="button"
                aria-label="Fewer servings"
                onClick={() => set(servings - 1)}
                disabled={servings <= 1}
              >
                −
              </button>
              <output htmlFor="scaler-range" aria-live="polite">
                {servings}
              </output>
              <button
                type="button"
                aria-label="More servings"
                onClick={() => set(servings + 1)}
                disabled={servings >= max}
              >
                +
              </button>
            </div>
          </div>
          <input
            id="scaler-range"
            type="range"
            min={1}
            max={max}
            step={1}
            value={servings}
            aria-valuetext={`${servings} servings`}
            onChange={(event) => set(Number(event.target.value))}
          />
          {servings !== base && (
            <p className="scaler-note">
              Scaled from {originalServings} servings ·{" "}
              <button type="button" className="link-button" onClick={() => set(base)}>
                Reset
              </button>
            </p>
          )}
        </div>
      ) : (
        <p className="scaler-note">This recipe doesn't say how many it serves, so amounts can't be scaled.</p>
      )}

      <div className="scaler-units" role="group" aria-label="Units">
        {UNIT_SYSTEMS.map((option) => (
          <button
            key={option.id}
            type="button"
            aria-pressed={system === option.id}
            className={system === option.id ? "is-active" : ""}
            onClick={() => onSystemChange(option.id)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </section>
  );
}

export default ServingsScaler;
