import { defineConfig } from "vite";

const workbenchProxy = {
  "/api/pipelines/validate": {
    target: "http://127.0.0.1:8010",
    changeOrigin: false,
  },
  "/api/v1": {
    target: "http://127.0.0.1:8011",
    changeOrigin: false,
  },
};

export default defineConfig({
  server: { proxy: workbenchProxy },
  preview: { proxy: workbenchProxy },
});
