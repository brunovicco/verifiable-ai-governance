type FieldHelpProps = {
  label: string;
  text: string;
};

/** Show contextual field guidance on hover, keyboard focus, and touch focus. */
export function FieldHelp({ label, text }: FieldHelpProps) {
  return (
    <span className="field-help">
      <button
        aria-label={`Ajuda sobre ${label}: ${text}`}
        className="field-help-trigger"
        type="button"
      >
        ?
      </button>
      <span className="field-help-tooltip" role="tooltip">{text}</span>
    </span>
  );
}
