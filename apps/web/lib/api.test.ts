import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, createInitiative, listInitiatives } from "@/lib/api";

describe("demo read-only guard", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("blocks write requests without calling fetch when NEXT_PUBLIC_DEMO_READ_ONLY is set", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_READ_ONLY", "true");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(createInitiative({ name: "Iniciativa de teste" })).rejects.toBeInstanceOf(
      ApiError,
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("still allows read requests through to fetch when read-only is enabled", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_READ_ONLY", "true");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [],
    });
    vi.stubGlobal("fetch", fetchMock);

    await listInitiatives();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("allows write requests through when read-only is not enabled", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_READ_ONLY", "false");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: "init-1" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await createInitiative({ name: "Iniciativa de teste" });
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});
