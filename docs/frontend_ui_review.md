# Frontend UI Review Checklist (Post-Panel Tabs Implementation)

This checklist is to be used after the "Panel tabs UI" feature (`FE_PANEL_0001`) and all its preceding frontend features have been implemented.

**I. Overall Layout & Responsiveness (from `FE_LAYOUT_0001`)**

*   **`AppShell` Rendering:**
    *   [X] Does the main `AppShell` render without errors?
    *   [X] Is the `StoreProvider` (Zustand) correctly wrapping the application?
*   **Responsive Behavior of `SlidingPanel`:**
    *   [X] **Desktop/Tablet (Viewport ≥600px):**
        *   [X] Does the `SlidingPanel` dock to the left as a sidebar?
        *   [X] Does the `MapView` correctly take up the remaining screen space?
    *   [ ] **Mobile (Viewport <600px):**
        *   [X] Does the `SlidingPanel` appear at the bottom of the screen?
        *   [X] Does it correctly overlay or integrate with the `MapView` which should be full screen?
        *   [X] Is the panel height appropriate on mobile (e.g., not too tall, not too short)?
*   **Dark Mode Integration (from `uiSlice` & `AppShell`):**
    *   [X] Does the `AppShell` apply a `dark` class (or equivalent styling) when dark mode is active in the `uiSlice`? (Verify by manually changing state via Redux DevTools if toggle isn't fully wired yet, or after checking Settings tab).

**II. Map Display (from `FE_LAYOUT_0001`)**

*   **`MapView` Integration:**
    *   [X] Is the Leaflet map (`MapView.tsx`) rendering within its designated area in `AppShell`?
    *   [X] Are map tiles loading correctly from the configured `OSM_TILE_URL`?
    *   [X] Is map attribution (e.g., © OpenStreetMap contributors) visible?
    *   [X] Is the map initially centered correctly (e.g., Boston, based on `CENTER_LAT`/`CENTER_LON` env vars)?
    *   [X] Do basic map interactions (pan, zoom via mouse/touch) work as expected?

**III. Plane Rendering on Map (from `FE_MAP_0001`)**

*   **Data Flow from `planesSlice`:**
    *   [ ] Does `MapView.tsx` correctly subscribe to and receive plane data from the `planesSlice`? (Use mock data in `planesSlice` if live data isn't flowing yet).
*   **`PlaneMarker.tsx` Rendering:**
    *   [ ] For each plane in the `planesSlice`, is a `PlaneMarker` rendered on the map at the correct `lat`/`lon`?
    *   [ ] **Icon:**
        *   [ ] Is the minimalist SVG icon displayed for each plane?
        *   [ ] Does the icon rotate according to the plane's heading (`hdg`)?
        *   [ ] Does it handle a missing heading gracefully (e.g., default orientation)?
    *   [ ] **Trail:**
        *   [ ] Is the fading polyline trail rendered based on `plane.trail` data?
        *   [ ] Does the fading effect appear correctly (e.g., older segments more transparent)?
        *   [ ] Does it handle empty or short trails gracefully?
*   **Performance:**
    *   [ ] With a moderate number of planes (e.g., 10-20, or as per PRD expectations), does the map remain responsive during updates and interaction? (Subjective check for now, formal benchmarks later if needed).
    *   [ ] Are there any console warnings related to React keys or Leaflet layer issues?

**IV. Panel Functionality & Content (from `FE_PANEL_0001`)**

*   **`SlidingPanel.tsx` & `PanelTabs.tsx` Interaction:**
    *   [X] Can you click on each tab ("Planes", "Leaderboard", "Settings") in `PanelTabs.tsx`?
    *   [X] Does clicking a tab correctly update the `activePanel` state in the `uiSlice`? (Verify with Redux DevTools).
    *   [X] Does the `SlidingPanel` display the correct content component (`PlaneListPanelContent`, `LeaderboardPanelContent`, `SettingsPanelContent`) based on the active tab?
    *   [X] Is the active tab visually highlighted?
*   **Planes Tab (`PlaneListPanelContent.tsx`):**
    *   [ ] Does it display a list of active flights from `planesSlice`?
    *   [ ] For each plane, are `callsign` (or hex ident) and `alt` (altitude) shown?
    *   [X] If no planes are available, is an appropriate message ("Scanning...", "No flights detected.") displayed?
    *   [ ] Are list items styled for readability?
    *   [ ] Does clicking a plane item log to the console or call a no-op function (as per current spec, actual interaction is future)?
*   **Leaderboard Tab (`LeaderboardPanelContent.tsx`):**
    *   [ ] Does it display a list/table of players and their scores from `gameSlice`?
    *   [ ] Are players sorted by score in descending order?
    *   [ ] Is the current player's entry highlighted (if mockable/identifiable)?
    *   [ ] **Confetti:** If a lead change is simulated in `gameSlice` scores, does the confetti animation trigger briefly and appropriately? Is it performant?
    *   [X] If no players/scores, is an appropriate message displayed?
*   **Settings Tab (`SettingsPanelContent.tsx`):**
    *   [X] **Night Mode Toggle:**
        *   [X] Is the toggle switch/checkbox present?
        *   [X] Does its state reflect the `darkMode` value from `uiSlice`?
        *   [X] Does interacting with the toggle call the `toggleDarkMode` action and update the UI's appearance application-wide?
    *   [X] **Leave Room Button:**
        *   [X] Is the button present?
        *   [X] Does clicking it log the appropriate message ("Attempting to leave room" or "Leaving solo mode") to the console (as per current spec, actual WS/nav is future)?
    *   [ ] **Host Controls Section:**
        *   [ ] Is this section correctly shown/hidden based on whether the current player is the host (and not in solo mode), using mock data in `gameSlice` and `connectionSlice` (for current player's nickname)?
        *   [ ] If shown, does it display the placeholder text/buttons for host actions?

**V. State Integration & Data Display (General)**

*   [ ] Is data from all relevant Zustand slices (`planes`, `game`, `ui`) being correctly selected and displayed in the corresponding UI components?
*   [ ] When you manually change state in Redux DevTools (e.g., add a plane, change a score, toggle dark mode), does the UI react and re-render correctly without a full page reload?

**VI. Basic Interactivity (as implemented so far)**

*   [ ] Tab navigation in the panel.
*   [ ] Night mode toggle.
*   [ ] Placeholder interactions (clicks on plane list items, leave room button).

**VII. Styling & Visual Consistency**

*   [ ] Does the overall UI adhere to the intended mobile-first portrait design, with responsive adjustments for larger screens?
*   [ ] Is Tailwind CSS being applied effectively?
*   [ ] Is there a consistent visual theme (colors, fonts, spacing – even if preliminary)?
*   [ ] Are icons (plane SVG, any tab icons if used) rendering correctly and with appropriate sizing?

**VIII. Accessibility (Initial Check - WCAG 2.1 AA Focus where applicable)**

*   [ ] **Keyboard Navigation:**
    *   [ ] Can you navigate between panel tabs using the keyboard (e.g., Tab key, arrow keys if implemented as a tab group)?
    *   [ ] Can you interact with the night mode toggle and buttons using the keyboard (Enter/Space)?
*   [ ] **Focus Outline:** Is there a visible focus outline on interactive elements when navigated via keyboard?
*   [ ] **Semantic HTML (Inspect):** Are appropriate HTML tags being used (e.g., `<button>` for buttons, `<nav>` for tab navigation if applicable)?
*   [ ] **Labels:** Do interactive elements like toggles and buttons have clear, descriptive text or ARIA labels?

**IX. Developer Experience Items**

*   [ ] **Console Errors/Warnings:** Are there any JavaScript errors or warnings in the browser console during rendering or interaction?
*   [ ] **React Developer Tools:** Does the component hierarchy look sensible? Are there unexpected re-renders?
*   [ ] **Zustand DevTools (Redux DevTools Extension):** Is the store state well-structured and updating as expected?
