import { defineConfig } from "vite";

// base relativa: la pagina funziona da qualsiasi percorso (GitHub Pages, file locale servito)
export default defineConfig({
  base: "./",
  server: { fs: { allow: [".."] } },     // mods/ sta fuori da web-builder/
  build: { target: "es2022" },
  worker: { format: "es" },
});
