import { afterEach, describe, expect, it, vi } from "vitest";

const status = (configured: boolean) => ({
  configured,
  client_code: configured ? "C1" : null,
  message: configured ? "Connected as C1" : "Not connected.",
  connected_at: null,
});

async function load(opts: { failures: number; configured: boolean; saved: boolean }) {
  vi.resetModules();
  let calls = 0;
  const getAngelOneStatus = vi.fn(async () => {
    calls += 1;
    if (calls <= opts.failures) throw new Error("Failed to fetch");
    return status(opts.configured);
  });
  const connectAngelOne = vi.fn(async () => status(true));
  vi.doMock("./api", () => ({ api: { getAngelOneStatus, connectAngelOne } }));
  vi.doMock("./angeloneDeviceStore", () => ({
    loadDeviceCredentials: () => (opts.saved ? { api_key: "k", client_code: "C1", pin: "1", totp_secret: "s" } : null),
  }));
  const mod = await import("./angeloneAutoConnect");
  return { mod, getAngelOneStatus, connectAngelOne };
}

afterEach(() => {
  vi.useRealTimers();
  vi.doUnmock("./api");
  vi.doUnmock("./angeloneDeviceStore");
});

describe("ensureAngelOneConnected", () => {
  it("keeps retrying while the server wakes up, then reconnects with the saved credentials", async () => {
    vi.useFakeTimers();
    const { mod, getAngelOneStatus, connectAngelOne } = await load({ failures: 3, configured: false, saved: true });
    const phases: string[] = [];
    mod.onConnectionChange((s) => phases.push(s.phase));
    const done = mod.ensureAngelOneConnected();
    await vi.runAllTimersAsync();
    const result = await done;
    expect(getAngelOneStatus).toHaveBeenCalledTimes(4);
    expect(connectAngelOne).toHaveBeenCalledTimes(1);
    expect(result.phase).toBe("connected");
    expect(phases).toContain("waking");
  });

  it("does not resend credentials when the server is already connected", async () => {
    const { mod, connectAngelOne } = await load({ failures: 0, configured: true, saved: true });
    expect((await mod.ensureAngelOneConnected()).phase).toBe("connected");
    expect(connectAngelOne).not.toHaveBeenCalled();
  });

  it("shows disconnected when there is nothing saved on this device", async () => {
    const { mod, connectAngelOne } = await load({ failures: 0, configured: false, saved: false });
    expect((await mod.ensureAngelOneConnected()).phase).toBe("disconnected");
    expect(connectAngelOne).not.toHaveBeenCalled();
  });

  it("shares one attempt between callers opening at the same time", async () => {
    const { mod, getAngelOneStatus } = await load({ failures: 0, configured: true, saved: false });
    await Promise.all([mod.ensureAngelOneConnected(), mod.ensureAngelOneConnected(), mod.ensureAngelOneConnected()]);
    expect(getAngelOneStatus).toHaveBeenCalledTimes(1);
  });
});
