import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useParams } from "react-router-dom";

import {
  getPublicationReferences,
  type DocumentationReference,
} from "../../services/documentation";
import LinkedDocumentationPanel from "./LinkedDocumentationPanel";
import "./publicationInlineReferences.css";

function normalise(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLowerCase();
}

function candidateScore(element: HTMLElement, reference: DocumentationReference): number {
  const text = normalise(element.textContent || "");
  const token = normalise(reference.raw_token);
  if (!text.includes(token)) return -1;
  const context = normalise(reference.source.context || "");
  if (!context) return 1;
  const useful = context.length > 120 ? context.slice(40, -40) : context;
  if (useful.length > 18 && text.includes(useful)) return 10;
  const words = useful.split(" ").filter((word) => word.length > 4).slice(0, 8);
  return 1 + words.filter((word) => text.includes(word)).length;
}

function wrapReference(element: HTMLElement, reference: DocumentationReference, open: (reference: DocumentationReference) => void): boolean {
  if (element.querySelector(`[data-document-reference-id="${CSS.escape(reference.id)}"]`)) return true;
  const token = reference.raw_token;
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || parent.closest("button, a, script, style, .publication-inline-reference")) return NodeFilter.FILTER_REJECT;
      return normalise(node.textContent || "").includes(normalise(token)) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    },
  });
  const node = walker.nextNode() as Text | null;
  if (!node) return false;
  const value = node.data;
  const index = value.toLowerCase().indexOf(token.toLowerCase());
  if (index < 0) return false;
  const before = value.slice(0, index);
  const matched = value.slice(index, index + token.length);
  const after = value.slice(index + token.length);
  const fragment = document.createDocumentFragment();
  if (before) fragment.appendChild(document.createTextNode(before));
  const button = document.createElement("button");
  button.type = "button";
  button.className = "publication-inline-reference";
  button.dataset.documentReferenceId = reference.id;
  button.title = reference.target ? `Open ${reference.target.code} · ${reference.target.title}` : `${reference.status.replaceAll("_", " ")} reference`;
  button.textContent = matched;
  button.disabled = !reference.target;
  button.addEventListener("click", () => open(reference));
  fragment.appendChild(button);
  if (after) fragment.appendChild(document.createTextNode(after));
  node.replaceWith(fragment);
  return true;
}

function decorate(references: DocumentationReference[], open: (reference: DocumentationReference) => void): void {
  const blocks = [...document.querySelectorAll<HTMLElement>(".publication-html-block")];
  for (const reference of references) {
    if (!reference.target) continue;
    const best = blocks
      .map((element) => ({ element, score: candidateScore(element, reference) }))
      .filter((candidate) => candidate.score >= 0)
      .sort((a, b) => b.score - a.score)[0];
    if (best) wrapReference(best.element, reference, open);
  }
}

export default function PublicationInlineReferenceController() {
  const params = useParams<{ amoCode?: string; tenantSlug?: string; manualId?: string; revId?: string }>();
  const tenant = (params.amoCode || params.tenantSlug || "").toLowerCase();
  const manualId = params.manualId || "";
  const revisionId = params.revId || "";
  const [references, setReferences] = useState<DocumentationReference[]>([]);
  const [selectedReference, setSelectedReference] = useState<DocumentationReference | null>(null);
  const identity = useMemo(() => `${tenant}:${manualId}:${revisionId}`, [manualId, revisionId, tenant]);

  useEffect(() => {
    if (!tenant || !manualId || !revisionId) return;
    let active = true;
    let timer = 0;
    const load = () => getPublicationReferences(tenant, manualId, revisionId)
      .then((response) => {
        if (!active) return;
        setReferences(response.items || []);
        if (["PENDING", "RUNNING"].includes(String(response.index?.status || "").toUpperCase())) {
          timer = window.setTimeout(load, 1400);
        }
      })
      .catch(() => { if (active) timer = window.setTimeout(load, 3500); });
    load();
    return () => { active = false; if (timer) window.clearTimeout(timer); };
  }, [identity, manualId, revisionId, tenant]);

  useEffect(() => {
    if (!references.length) return;
    let scheduled = 0;
    const run = () => {
      window.clearTimeout(scheduled);
      scheduled = window.setTimeout(() => decorate(references, setSelectedReference), 30);
    };
    run();
    const observer = new MutationObserver(run);
    const root = document.querySelector(".publication-document-canvas") || document.body;
    observer.observe(root, { childList: true, subtree: true });
    return () => { observer.disconnect(); window.clearTimeout(scheduled); };
  }, [references]);

  useEffect(() => {
    document.body.classList.toggle("has-inline-linked-document", Boolean(selectedReference));
    return () => document.body.classList.remove("has-inline-linked-document");
  }, [selectedReference]);

  if (!selectedReference || !tenant || typeof document === "undefined") return null;
  return createPortal(
    <div className="publication-inline-linked-drawer">
      <LinkedDocumentationPanel tenant={tenant} referenceId={selectedReference.id} onClose={() => setSelectedReference(null)} />
    </div>,
    document.body,
  );
}
