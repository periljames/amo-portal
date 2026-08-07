import React, { useMemo, useState } from "react";

import type { CalculationFormula } from "./reliabilityAnalyticsTypes";

function FormulaMath({ formula }: { formula: CalculationFormula }): React.ReactElement {
  return (
    <div
      className="reliability-formula__math"
      aria-label={`${formula.name} mathematical formula`}
      dangerouslySetInnerHTML={{ __html: formula.mathml }}
    />
  );
}

async function copyText(value: string): Promise<void> {
  await navigator.clipboard.writeText(value);
}

export function ReliabilityFormulaLibrary({ formulae }: { formulae: CalculationFormula[] }): React.ReactElement {
  const [query, setQuery] = useState("");
  const [origin, setOrigin] = useState<"ALL" | "SYSTEM" | "PROGRAMME">("ALL");
  const [copied, setCopied] = useState<string | null>(null);

  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return formulae.filter((formula) => {
      if (origin !== "ALL" && formula.origin !== origin) return false;
      if (!normalized) return true;
      const haystack = [
        formula.code,
        formula.name,
        formula.unit,
        formula.methodology,
        formula.numerator_label,
        formula.denominator_label || "",
        ...formula.source_fields,
        ...formula.applied_to,
      ].join(" ").toLowerCase();
      return haystack.includes(normalized);
    });
  }, [formulae, origin, query]);

  const handleCopy = async (formula: CalculationFormula) => {
    try {
      await copyText(formula.latex);
      setCopied(formula.code);
      window.setTimeout(() => setCopied((current) => current === formula.code ? null : current), 1800);
    } catch {
      setCopied(null);
    }
  };

  return (
    <section className="reliability-formula-library" id="reliability-formula-library" aria-labelledby="reliability-formula-heading">
      <div className="reliability-formula-library__heading">
        <div>
          <p className="reliability-v2__eyebrow">Controlled methodology</p>
          <h2 id="reliability-formula-heading">Calculation and formula library</h2>
          <p>Every analytical rate exposes its structured equation, version, units, denominator rule, source fields and machine-readable expression.</p>
        </div>
        <div className="reliability-formula-library__filters">
          <label>
            <span>Find formula</span>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Dispatch, NFF, flight hours…" />
          </label>
          <label>
            <span>Origin</span>
            <select value={origin} onChange={(event) => setOrigin(event.target.value as typeof origin)}>
              <option value="ALL">All formulae</option>
              <option value="SYSTEM">System formulae</option>
              <option value="PROGRAMME">Programme formulae</option>
            </select>
          </label>
        </div>
      </div>

      <div className="reliability-formula-library__summary" role="status">
        <strong>{visible.length}</strong>
        <span>of {formulae.length} controlled formulae shown</span>
      </div>

      <div className="reliability-formula-library__grid">
        {visible.map((formula) => (
          <article className="reliability-formula" id={`formula-${formula.code}`} key={formula.code}>
            <header className="reliability-formula__header">
              <div>
                <span className={`reliability-formula__origin reliability-formula__origin--${formula.origin.toLowerCase()}`}>{formula.origin}</span>
                <h3>{formula.name}</h3>
                <code>{formula.code} · v{formula.version}</code>
              </div>
              <button type="button" className="btn btn-small btn-secondary" onClick={() => void handleCopy(formula)}>
                {copied === formula.code ? "LaTeX copied" : "Copy LaTeX"}
              </button>
            </header>

            <FormulaMath formula={formula} />
            <pre className="reliability-formula__latex" aria-label="LaTeX source">{formula.latex}</pre>

            <dl className="reliability-formula__definition">
              <div><dt>Numerator</dt><dd>{formula.numerator_label}</dd></div>
              <div><dt>Denominator</dt><dd>{formula.denominator_label || "Not applicable"}</dd></div>
              <div><dt>Multiplier</dt><dd>{formula.multiplier ?? "Not applicable"}</dd></div>
              <div><dt>Reported unit</dt><dd>{formula.unit}</dd></div>
              <div><dt>Precision</dt><dd>{formula.precision} decimal places</dd></div>
              <div><dt>Rounding</dt><dd>{formula.rounding_mode.replaceAll("_", " ")}</dd></div>
            </dl>

            <div className="reliability-formula__method">
              <h4>Methodology</h4>
              <p>{formula.methodology}</p>
              <h4>Denominator and missing-data rule</h4>
              <p>{formula.denominator_policy}</p>
            </div>

            <details className="reliability-formula__details">
              <summary>Source fields and application map</summary>
              <div className="reliability-formula__lists">
                <div><strong>Source fields</strong><ul>{formula.source_fields.map((field) => <li key={field}><code>{field}</code></li>)}</ul></div>
                <div><strong>Used by</strong><ul>{formula.applied_to.map((item) => <li key={item}><code>{item}</code></li>)}</ul></div>
              </div>
            </details>

            <details className="reliability-formula__details">
              <summary>Machine-readable expression tree</summary>
              <pre>{JSON.stringify(formula.expression, null, 2)}</pre>
            </details>
          </article>
        ))}
      </div>

      {visible.length === 0 && (
        <div className="reliability-analytics__empty">
          <strong>No matching formula</strong>
          <span>Change the formula name, source field or origin filter.</span>
        </div>
      )}
    </section>
  );
}
