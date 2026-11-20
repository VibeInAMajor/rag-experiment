import { defineConfig } from "vite";

const validationProxy = {
  "/api/pipelines/validate": {
    target: "http://127.0.0.1:8010",
    changeOrigin: false,
  },
};

export default defineConfig({
  server: { proxy: validationProxy },
  preview: { proxy: validationProxy },
});
