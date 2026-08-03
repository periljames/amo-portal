import fs from "node:fs";
import path from "node:path";

const target = path.resolve(process.cwd(), "src/styles/reliability-v2.css");
let text = fs.readFileSync(target, "utf8");
const marker = "/* COMPLETE_RELIABILITY_WORKFLOW_STYLES */";
if (!text.includes(marker)) {
  text += `

${marker}
.reliability-v2__section-heading--page {
  align-items: flex-start;
  gap: var(--space-4, 1rem);
  margin-bottom: var(--space-4, 1rem);
}

.reliability-v2__section-heading--page > div:first-child {
  min-width: 0;
  max-width: 76rem;
}

.reliability-v2__section-heading--page p:last-child {
  margin: .35rem 0 0;
  color: var(--text-muted);
  max-width: 72rem;
}

.reliability-v2__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: .45rem;
}

.reliability-v2__success,
.reliability-v2__permission-note,
.reliability-v2__compliance-banner {
  border-inline-start: .24rem solid var(--accent-color, var(--color-primary));
  background: color-mix(in srgb, var(--accent-color, var(--color-primary)) 8%, var(--surface-raised));
  padding: .75rem .9rem;
  border-radius: var(--radius-md);
  margin: .65rem 0;
}

.reliability-v2__permission-note {
  border-inline-start-color: var(--status-warning, #a76500);
  background: color-mix(in srgb, var(--status-warning, #a76500) 8%, var(--surface-raised));
  color: var(--text-muted);
}

.reliability-v2__compliance-banner {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: .8rem;
  align-items: start;
  margin-bottom: .9rem;
}

.reliability-v2__compliance-banner p {
  margin: .25rem 0 0;
  color: var(--text-muted);
}

.reliability-v2__check-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));
  gap: .65rem;
}

.reliability-v2__check {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  column-gap: .55rem;
  row-gap: .28rem;
  align-items: start;
  min-width: 0;
  padding: .75rem;
  border-block: 1px solid var(--border-subtle);
  color: inherit;
  text-decoration: none;
}

.reliability-v2__check strong,
.reliability-v2__check p,
.reliability-v2__check small {
  grid-column: 2;
}

.reliability-v2__check p {
  margin: 0;
  color: var(--text-muted);
}

.reliability-v2__form {
  display: grid;
  gap: .65rem;
  min-width: 0;
  align-content: start;
  padding-block: .35rem .9rem;
}

.reliability-v2__form + .reliability-v2__form {
  border-inline-start: 1px solid var(--border-subtle);
  padding-inline-start: 1rem;
}

.reliability-v2__form h3 {
  margin: 0;
  font-size: 1rem;
}

.reliability-v2__form label,
.reliability-v2__toolbar label {
  display: grid;
  gap: .25rem;
  min-width: 0;
  color: var(--text-muted);
  font-size: .78rem;
  font-weight: 620;
}

.reliability-v2__form input,
.reliability-v2__form select,
.reliability-v2__form textarea,
.reliability-v2__toolbar input,
.reliability-v2__toolbar select {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--surface-input, var(--surface-raised));
  color: var(--text-primary);
  padding: .46rem .55rem;
  font: inherit;
  font-weight: 450;
}

.reliability-v2__form textarea {
  resize: vertical;
  line-height: 1.42;
}

.reliability-v2__form fieldset {
  display: flex;
  flex-wrap: wrap;
  gap: .55rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: .55rem;
}

.reliability-v2__form legend {
  padding-inline: .25rem;
  color: var(--text-muted);
  font-size: .76rem;
}

.reliability-v2__check-label {
  display: flex !important;
  grid-template-columns: none !important;
  align-items: center;
  gap: .4rem !important;
  font-weight: 520 !important;
}

.reliability-v2__check-label input {
  width: auto !important;
  margin: 0;
}

.reliability-v2__form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 12rem), 1fr));
  gap: .55rem;
}

.reliability-v2__form--horizontal {
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr));
  align-items: end;
  border-block: 1px solid var(--border-subtle);
  padding-block: .8rem;
  margin-bottom: .85rem;
}

.reliability-v2__form--horizontal label:has(textarea) {
  grid-column: span 2;
}

.reliability-v2__split--forms {
  align-items: start;
}

.reliability-v2__workflow-columns {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1rem;
  align-items: start;
}

.reliability-v2__toolbar {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 10rem), max-content));
  align-items: end;
  gap: .6rem;
  padding-block: .65rem;
  border-block: 1px solid var(--border-subtle);
  margin-bottom: .75rem;
}

.reliability-v2__toolbar select[multiple] {
  min-height: 5.2rem;
}

.reliability-v2__table small {
  display: block;
  margin-top: .16rem;
  color: var(--text-muted);
}

.reliability-v2__table code,
.reliability-v2__timeline code,
.reliability-v2__evidence-row code {
  overflow-wrap: anywhere;
  font-size: .72rem;
}

.reliability-v2__json {
  margin-top: .25rem;
  max-width: 38rem;
}

.reliability-v2__json summary {
  cursor: pointer;
  color: var(--accent-color, var(--color-primary));
  font-size: .75rem;
  font-weight: 650;
}

.reliability-v2__json pre {
  max-height: 20rem;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  padding: .65rem;
  border: 1px solid var(--border-subtle);
  background: var(--surface-sunken, var(--surface-canvas));
  color: var(--text-primary);
  border-radius: var(--radius-sm);
  font-size: .72rem;
}

.reliability-v2__inline-record {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: .32rem;
  padding-block: .28rem;
  border-bottom: 1px solid var(--border-subtle);
}

.reliability-v2__evidence-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));
  gap: .8rem;
}

.reliability-v2__evidence-grid dl {
  display: grid;
  grid-template-columns: minmax(7rem, auto) minmax(0, 1fr);
  gap: .4rem .65rem;
  margin: 0;
}

.reliability-v2__evidence-grid dt {
  color: var(--text-muted);
}

.reliability-v2__evidence-grid dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.reliability-v2__evidence-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: .25rem .55rem;
  padding: .55rem 0;
  border-bottom: 1px solid var(--border-subtle);
}

.reliability-v2__evidence-row strong,
.reliability-v2__evidence-row small,
.reliability-v2__evidence-row p {
  grid-column: 2;
  margin: 0;
}

.reliability-v2__evidence-row p {
  color: var(--text-muted);
}

.reliability-v2__stage-line {
  display: flex;
  gap: .3rem;
  overflow-x: auto;
  padding: .5rem 0 .8rem;
  scrollbar-width: thin;
}

.reliability-v2__stage-line span {
  flex: 0 0 auto;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  padding: .3rem .5rem;
  color: var(--text-muted);
  font-size: .68rem;
  font-weight: 650;
}

.reliability-v2__stage-line span.is-current {
  border-color: var(--accent-color, var(--color-primary));
  background: color-mix(in srgb, var(--accent-color, var(--color-primary)) 12%, transparent);
  color: var(--text-primary);
}

.reliability-v2__timeline {
  display: grid;
  gap: 0;
}

.reliability-v2__timeline article {
  display: grid;
  grid-template-columns: minmax(8rem, 10rem) minmax(10rem, .8fr) minmax(14rem, 2fr) minmax(10rem, 1fr);
  gap: .65rem;
  align-items: start;
  padding: .55rem 0;
  border-bottom: 1px solid var(--border-subtle);
}

.reliability-v2__timeline p {
  margin: 0;
  color: var(--text-muted);
}

.reliability-v2__timeline time {
  color: var(--text-muted);
  font-size: .76rem;
}

@media (max-width: 1180px) {
  .reliability-v2__workflow-columns {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .reliability-v2__form + .reliability-v2__form {
    border-inline-start: 0;
    padding-inline-start: 0;
  }
}

@media (max-width: 760px) {
  .reliability-v2__section-heading--page,
  .reliability-v2__compliance-banner {
    grid-template-columns: 1fr;
    display: grid;
  }
  .reliability-v2__workflow-columns,
  .reliability-v2__split--forms,
  .reliability-v2__form--horizontal {
    grid-template-columns: 1fr;
  }
  .reliability-v2__form--horizontal label:has(textarea) {
    grid-column: 1;
  }
  .reliability-v2__timeline article {
    grid-template-columns: 1fr;
    gap: .2rem;
  }
}
`;
}
fs.writeFileSync(target, text.replace(/\s+$/, "") + "\n", "utf8");
console.log("Complete Reliability workflow styles appended.");
