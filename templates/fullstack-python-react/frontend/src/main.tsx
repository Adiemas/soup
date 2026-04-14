import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

const el = document.getElementById("root");
if (!el) throw new Error("missing #root");
ReactDOM.createRoot(el).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
