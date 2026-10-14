// Entry point. Styles load in layer order: design tokens, Lucent, base, then each UI layer imports its own.
import "../styles/tokens.css";
import "../vendor/lucent/bundle.css";
import "./styles/base.css";
import "./ui/atoms"; // publishes React for Lucent and loads it before anything renders
import "./pages/pages.css";
import "./styles/transitions.css";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { applyTheme, getTheme } from "./lib/theme";

applyTheme(getTheme());
const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root");
createRoot(root).render(<App />);
