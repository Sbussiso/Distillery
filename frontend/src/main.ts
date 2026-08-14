import "./app.css";
import App from "./App.svelte";
import { mount } from "svelte";
import { boot } from "./lib/boot";

// Kick off the initial data load (models, providers, presets, health, sessions)
// before mounting so the first paint is populated.
boot();

const app = mount(App, { target: document.getElementById("app")! });

export default app;