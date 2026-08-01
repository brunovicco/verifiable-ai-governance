import { describe, expect, it } from "vitest";

import {
  assessmentFieldGuidance,
  initiativeCheckGuidance,
  proposalFieldGuidance,
  reviewFieldGuidance,
} from "./field-guidance";

describe("field guidance", () => {
  it("covers every initiative classification flag", () => {
    expect(Object.keys(initiativeCheckGuidance)).toHaveLength(12);
  });

  it("keeps every tooltip instructional", () => {
    const messages = [
      ...Object.values(proposalFieldGuidance),
      ...Object.values(initiativeCheckGuidance),
      ...Object.values(assessmentFieldGuidance),
      ...Object.values(reviewFieldGuidance),
    ];

    expect(messages.every((message) => message.length >= 40)).toBe(true);
  });
});
