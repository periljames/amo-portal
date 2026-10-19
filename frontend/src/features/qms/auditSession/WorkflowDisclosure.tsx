import { useEffect, useRef, type ReactNode } from "react";
import { ChevronDown, type LucideIcon } from "lucide-react";

export default function WorkflowDisclosure({ title, description, icon: Icon, children, className = "", id }: {
  title: string; description: string; icon: LucideIcon; children: ReactNode; className?: string; id?: string;
}) {
  const element = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (!id) return;
    const reveal = () => { if (window.location.hash === `#${id}` && element.current) element.current.open = true; };
    reveal(); window.addEventListener("hashchange", reveal);
    return () => window.removeEventListener("hashchange", reveal);
  }, [id]);
  return <details ref={element} id={id} className={`audit-workflow-disclosure ${className}`}>
    <summary><span className="audit-workflow-section-icon"><Icon size={19} aria-hidden /></span>
      <span><span className="audit-workflow-disclosure__title">{title}</span><small>{description}</small></span>
      <ChevronDown className="audit-workflow-disclosure__chevron" size={17} aria-hidden />
    </summary>
    <div className="audit-workflow-disclosure__content">{children}</div>
  </details>;
}
