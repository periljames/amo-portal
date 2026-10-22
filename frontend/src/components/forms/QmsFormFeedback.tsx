import { useEffect } from "react";

type Field = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
const isField = (node: EventTarget | null): node is Field => node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement || node instanceof HTMLSelectElement;
const editable = (field: Field) => !field.disabled && !("readOnly" in field && field.readOnly) && field.willValidate && field.getClientRects().length > 0;

function fieldMessage(field: Field): string {
  if (field.required && !field.value.trim()) return "Complete this field before continuing.";
  if ("minLength" in field && field.value.trim() && field.minLength > 0 && field.value.trim().length < field.minLength) return `Use at least ${field.minLength} characters.`;
  if (field.validity.typeMismatch && field instanceof HTMLInputElement && field.type === "email") return "Enter one complete email address, such as name@organization.com.";
  if (field.validity.tooShort) return `Use at least ${"minLength" in field ? field.minLength : 1} characters.`;
  if (field.validity.rangeUnderflow && field instanceof HTMLInputElement) return `Use a value of at least ${field.min}.`;
  if (field.validity.rangeOverflow && field instanceof HTMLInputElement) return `Use a value no greater than ${field.max}.`;
  return field.validity.valid ? "" : field.validationMessage;
}

/** Inline HTML-constraint feedback for QMS pages and their portalled forms. */
export default function QmsFormFeedback() {
  useEffect(() => {
    const touched = new WeakSet<Field>();
    const nodes = new Map<Field, HTMLElement>();
    let sequence = 0;
    const show = (field: Field) => {
      if (!editable(field) || field.closest('[data-qms-validation="off"]')) return;
      const message = fieldMessage(field);
      let node = nodes.get(field);
      if (!message) {
        if (node) {
          field.removeAttribute("aria-invalid");
          field.setAttribute("aria-describedby", (field.getAttribute("aria-describedby") || "").split(" ").filter(id => id !== node!.id).join(" "));
          node.remove(); nodes.delete(field);
        }
        return;
      }
      if (!node) {
        node = document.createElement("small");
        node.id = `qms-field-feedback-${Date.now()}-${++sequence}`;
        node.className = "qms-field-feedback";
        node.setAttribute("aria-live", "polite");
        field.insertAdjacentElement("afterend", node);
        nodes.set(field, node);
        field.setAttribute("aria-describedby", [field.getAttribute("aria-describedby"), node.id].filter(Boolean).join(" "));
      }
      field.setAttribute("aria-invalid", "true");
      node.textContent = message;
    };
    const prepare = (root: ParentNode) => root.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>("input, textarea").forEach(field => {
      if (!field.hasAttribute("spellcheck")) field.spellcheck = field instanceof HTMLTextAreaElement || (!field.type || field.type === "text");
      if (field.type === "email") { field.autocapitalize = "none"; field.spellcheck = false; }
    });
    const blur = (event: Event) => { if (isField(event.target)) { touched.add(event.target); show(event.target); } };
    const input = (event: Event) => { const field = event.target; if (isField(field) && touched.has(field)) requestAnimationFrame(() => { if (field.isConnected) show(field); }); };
    const invalid = (event: Event) => { if (isField(event.target)) { event.preventDefault(); touched.add(event.target); show(event.target); } };
    const submit = (event: Event) => {
      if (!(event.target instanceof HTMLFormElement)) return;
      let first: Field | undefined;
      event.target.querySelectorAll<Field>("input, select, textarea").forEach(field => {
        if (!editable(field)) return;
        touched.add(field); show(field);
        if (fieldMessage(field)) first ??= field;
      });
      if (first) { event.preventDefault(); event.stopPropagation(); first.focus(); }
    };
    prepare(document);
    const observer = new MutationObserver(records => {
      for (const record of records) for (const node of record.addedNodes) if (node instanceof Element) prepare(node.parentElement || node);
      for (const [field, node] of nodes) if (!field.isConnected) { node.remove(); nodes.delete(field); }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("focusout", blur, true);
    document.addEventListener("input", input, true);
    document.addEventListener("change", input, true);
    document.addEventListener("invalid", invalid, true);
    document.addEventListener("submit", submit, true);
    return () => {
      observer.disconnect();
      document.removeEventListener("focusout", blur, true); document.removeEventListener("input", input, true);
      document.removeEventListener("change", input, true); document.removeEventListener("invalid", invalid, true); document.removeEventListener("submit", submit, true);
      for (const [field, node] of nodes) { field.removeAttribute("aria-invalid"); field.setAttribute("aria-describedby", (field.getAttribute("aria-describedby") || "").split(" ").filter(id => id !== node.id).join(" ")); node.remove(); }
    };
  }, []);
  return null;
}
