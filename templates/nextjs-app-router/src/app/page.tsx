/**
 * Home page. Server Component by default.
 * Do NOT add "use client" here unless the page needs hooks/state.
 * If interactivity is required, extract a child component marked "use client".
 */
export default function HomePage() {
  return (
    <main>
      <h1>your-app</h1>
      <p>
        Scaffolded from the soup <code>nextjs-app-router</code> template.
        This page is a Server Component.
      </p>
      <p>
        <a href="/api/health">/api/health</a>
      </p>
    </main>
  );
}
