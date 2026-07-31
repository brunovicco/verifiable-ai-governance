import { describe, expect, it } from "vitest";

import { label, statusClass } from "./labels";

describe("governance labels", () => {
  it("translates domain values for non-technical users", () => {
    expect(label("under_review")).toBe("Em avaliação");
    expect(label("international-processing-assessment")).toContain("processamento");
  });

  it("creates a stable status class", () => {
    expect(statusClass("not_required")).toBe("status status-not-required");
  });
});
