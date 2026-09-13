import React from "react";

export function AssuranceDataSummary({ title, columns, rows }: {
  title: string; columns: Array<{ key: string; label: string }>;
  rows: Array<Record<string, string | number>>;
}) {
  return <details className="assurance-data-summary">
    <summary>{title}: data table</summary>
    <div className="assurance-data-summary__scroll">
      <table><caption>{title}</caption>
        <thead><tr>{columns.map((column) => <th key={column.key} scope="col">{column.label}</th>)}</tr></thead>
        <tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column, columnIndex) => columnIndex === 0
          ? <th scope="row" key={column.key}>{row[column.key]}</th>
          : <td key={column.key}>{row[column.key]}</td>)}</tr>)}</tbody>
      </table>
    </div>
  </details>;
}
