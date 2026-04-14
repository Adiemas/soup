import { useEffect, useState } from "react";

type Status = "loading" | "ok" | "degraded" | "error";

interface HealthBody {
  status: string;
  db?: boolean;
}

/** Polls `/api/health` once and renders the result. */
export function Health(): JSX.Element {
  const [status, setStatus] = useState<Status>("loading");
  const [detail, setDetail] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/health");
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const body = (await res.json()) as HealthBody;
        if (cancelled) return;
        setStatus(body.status === "ok" ? "ok" : "degraded");
        setDetail(JSON.stringify(body));
      } catch (err) {
        if (cancelled) return;
        setStatus("error");
        setDetail(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section aria-label="service-health">
      <h2>Health</h2>
      <p data-testid="health-status">Status: {status}</p>
      {detail && <pre data-testid="health-detail">{detail}</pre>}
    </section>
  );
}
