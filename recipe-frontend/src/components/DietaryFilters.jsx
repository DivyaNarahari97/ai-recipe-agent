import { CALORIE_OPTIONS, DIET_LABELS, TIME_OPTIONS } from "../dietary";

function LimitSelect({ label, value, options, unit, onChange }) {
  return (
    <label className="diet-limit">
      {label}
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">Any</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option} {unit}
          </option>
        ))}
      </select>
    </label>
  );
}

function DietaryFilters({ filters, onChange }) {
  const update = (changes) => onChange({ ...filters, ...changes });

  return (
    <fieldset className="diet-filters">
      <legend>Dietary preferences</legend>
      <div className="diet-chips">
        {Object.entries(DIET_LABELS).map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`diet-chip${filters[key] ? " is-active" : ""}`}
            aria-pressed={filters[key]}
            onClick={() => update({ [key]: !filters[key] })}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="diet-limits">
        <LimitSelect
          label="Max time"
          value={filters.max_minutes}
          options={TIME_OPTIONS}
          unit="min"
          onChange={(max_minutes) => update({ max_minutes })}
        />
        <LimitSelect
          label="Max calories"
          value={filters.max_calories}
          options={CALORIE_OPTIONS}
          unit="kcal"
          onChange={(max_calories) => update({ max_calories })}
        />
      </div>
    </fieldset>
  );
}

export default DietaryFilters;
