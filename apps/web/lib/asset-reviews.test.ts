import { describe, expect, it } from "vitest";

import { assetDisplayStatus } from "@/lib/asset-reviews";

describe("assetDisplayStatus", () => {
  it("surfaces an expired review instead of an approved lifecycle label", () => {
    expect(assetDisplayStatus("approved", "expired")).toBe("expired");
  });

  it("preserves draft and current approved lifecycle labels", () => {
    expect(assetDisplayStatus("draft", "not_reviewed")).toBe("draft");
    expect(assetDisplayStatus("approved", "current")).toBe("approved");
  });
});
