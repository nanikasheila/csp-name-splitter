/**
 * Application entry point.
 *
 * Why: Svelte + Vite requires a JS entry that mounts the root component.
 * How: Import App.svelte and mount it to the #app container.
 */
import App from "./lib/App.svelte";
import { mount } from "svelte";
import "./styles/global.css";

const app = mount(App, { target: document.getElementById("app")! });

export default app;
