import { isDemoReadOnly } from "@/lib/demo";

export function DemoReadOnlyBanner() {
  if (!isDemoReadOnly()) return null;
  return (
    <div className="vg-demo-banner" role="status">
      <strong>Demo pública somente leitura</strong>
      <span>
        Os dados apresentados são sintéticos. Criação, edição, aprovação e upload de evidências
        estão desabilitados.
      </span>
    </div>
  );
}
