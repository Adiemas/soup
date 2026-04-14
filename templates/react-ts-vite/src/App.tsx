import { Health } from "./components/Health";

/** Top-level application shell. */
export default function App(): JSX.Element {
  return (
    <main>
      <h1>your-app</h1>
      <p>Scaffolded from the soup <code>react-ts-vite</code> template.</p>
      <Health />
    </main>
  );
}
