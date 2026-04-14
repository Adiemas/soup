import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "../App";

describe("App", () => {
  afterEach(() => vi.restoreAllMocks());

  it("displays backend status and greeting", async () => {
    const fetchMock = vi.fn(async (url: string | URL | Request) => {
      const u = url.toString();
      if (u.endsWith("/api/health")) {
        return { ok: true, json: async () => ({ status: "ok", db: true }) };
      }
      if (u.endsWith("/api/greet/soup")) {
        return { ok: true, json: async () => ({ message: "hello, soup" }) };
      }
      throw new Error("unexpected url: " + u);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("ok");
      expect(screen.getByTestId("greet")).toHaveTextContent("hello, soup");
    });
  });
});
