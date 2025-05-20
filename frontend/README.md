# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default tseslint.config({
  extends: [
    // Remove ...tseslint.configs.recommended and replace with this
    ...tseslint.configs.recommendedTypeChecked,
    // Alternatively, use this for stricter rules
    ...tseslint.configs.strictTypeChecked,
    // Optionally, add this for stylistic rules
    ...tseslint.configs.stylisticTypeChecked,
  ],
  languageOptions: {
    // other options...
    parserOptions: {
      project: ["./tsconfig.node.json", "./tsconfig.app.json"],
      tsconfigRootDir: import.meta.dirname,
    },
  },
});
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from "eslint-plugin-react-x";
import reactDom from "eslint-plugin-react-dom";

export default tseslint.config({
  plugins: {
    // Add the react-x and react-dom plugins
    "react-x": reactX,
    "react-dom": reactDom,
  },
  rules: {
    // other rules...
    // Enable its recommended typescript rules
    ...reactX.configs["recommended-typescript"].rules,
    ...reactDom.configs.recommended.rules,
  },
});
```

## Core Infrastructure

The frontend communicates with the backend through a `WebSocketClient` located at `src/lib/WebSocketClient.ts`. This singleton automatically reconnects and maintains a heartbeat. Shared application state is managed by a Zustand **root store** created in `src/store/createRootStore.tsx` and consumed via the `useStore` hook. The store is composed of four slices (`connection`, `planes`, `game`, `ui`), with the `ui` slice persisted in `localStorage`. Run `npm run test` to execute the accompanying unit tests.

## Base Layout

The application is orchestrated by `AppShell`, which renders a full-screen Leaflet map via `MapView` and a responsive `SlidingPanel`. The panel docks to the left on wider screens (≥600&nbsp;px) and slides up from the bottom on mobile. Tab navigation within the panel toggles between placeholder views for "Planes", "Leaderboard" and "Settings". These components live under `src/components/layout/` and `src/features/*/components/`.

## Map Performance Benchmark

A Vitest benchmark ensures map updates stay within the 300 ms budget defined in the PRD. It lives in
`src/features/map/__tests__/MapPerformance.test.tsx` and runs automatically in CI. To run it locally:

```bash
# from repo root
npx ts-node scripts/run-map-bench.ts
```

The benchmark mounts `MapView` with many fake planes and logs the average render time. It is skipped
when the `CI` environment variable is unset.
