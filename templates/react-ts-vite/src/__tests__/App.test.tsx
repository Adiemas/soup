import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "../App";

describe("App", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders heading", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "ok", db: true }),
      }),
    );
    render(<App />);
    expect(screen.getByRole("heading", { name: "your-app" })).toBeInTheDocument();
  });

  it("shows ok status when /api/health returns ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "ok", db: true }),
      }),
    );
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("health-status")).toHaveTextContent("Status: ok");
    });
  });

  it("shows error status when /api/health throws", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")));
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("health-status")).toHaveTextContent("Status: error");
    });
  });
});
