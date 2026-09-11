import React from "react";
import { ArrowRight } from "lucide-react";
import { Button } from "../../components/UI/Admin";
import "../../styles/admin-setup-workflow-navigation.css";

export default function AdminSetupWorkflowNavigator({ previous, next, onPrevious, onNext }: {
  previous?: string; next?: string; onPrevious: () => void; onNext: () => void;
}) {
  return <nav className="setup-resend__step-navigation" aria-label="Setup stage navigation">
    {previous ? <Button type="button" size="sm" variant="secondary" onClick={onPrevious}>Back: {previous}</Button> : <span />}
    {next ? <Button type="button" size="sm" onClick={onNext}>Next: {next} <ArrowRight size={14} /></Button> : null}
  </nav>;
}
