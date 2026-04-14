import { useEffect, useState } from "react";

interface HealthBody {
  status: string;
  db?: boolean;
}

/** Root component — calls backend /health via the /api proxy. */
export default function App(): JSX.Element {
  const [status, setStatus] = useState("loading");
  const [greet, setGreet] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const h = await fetch("/api/health").then((r) => r.json() as Promise<HealthBody>);
        if (!cancelled) setStatus(h.status);
        const g = await fetch("/api/greet/soup").then((r) => r.json());
        if (!cancelled) setGreet(g.message);
      } catch (e) {
        if (!cancelled) setStatus(e instanceof Error ? e.message : "error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main>
      <h1>fullstack</h1>
      <p data-testid="status">Backend status: {status}</p>
      {greet && <p data-testid="greet">{greet}</p>}
    </main>
  );
}
