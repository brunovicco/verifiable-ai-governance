import type { AssetReviewState } from "@/lib/types";

/** Prefer time-sensitive review validity over the persisted approved lifecycle label. */
export function assetDisplayStatus(
  lifecycleStatus: string,
  reviewState: AssetReviewState,
): string {
  return lifecycleStatus === "approved" && reviewState === "expired"
    ? "expired"
    : lifecycleStatus;
}
