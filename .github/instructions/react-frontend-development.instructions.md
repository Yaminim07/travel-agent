# React & Frontend Development Rules

## 1. Architectural & Component Design
- **Functional Architecture:** Write functional components using modern ES6+ features and arrow functions (`const MyComponent = () => {}`).
- **Separation of Concerns:** Keep components lean and focused purely on UI presentation.
- **Custom Hooks Custom:** Extract any complex data transformations, state logic, or side effects into dedicated custom hooks (for example, `useWorkspace.js`).
- **State Locality:** Keep state as local as possible. Do not lift state up or use global context unless multiple non-nested components absolutely require it.

## 2. Data Fetching & Async State
- **No Raw Fetching in Hooks:** Never use raw `useEffect` loops to fetch data from the backend API.
- **Server State Management:** Use TanStack Query (React Query) or RTK Query for caching, synchronizing, and updating server state.
- **Loading & Error UX:** Every data mutation or query must explicitly account for, display, and handle loading (`isLoading`) and error (`isError`) UI states.

## 3. Styling & Performance
- **Utility-First Styling:** Use Tailwind CSS utility classes for styling. Avoid inline styles (`style={{...}}`) and vanilla CSS sheets entirely unless modifying legacy files.
- **Responsive Layouts:** Design using fluid layouts, Flexbox, and CSS Grid. Use mobile-first breakpoints (`md:`, `lg:`) instead of hardcoded pixel sizes.
- **Optimization:** Prevent unnecessary re-renders. Memoize expensive computations with `useMemo` and event handlers with `useCallback` only when performance profiles indicate a bottleneck.

## 4. Code Hygiene & UI Best Practices
- **Strict Completeness:** Do not use `// TODO` comments or leave functions incomplete. Provide complete working JSX.
- **Semantic Markup:** Always write semantic HTML elements (`<header>`, `<main>`, `<nav>`, `<button>`). Never use generic `<div>` or `<span>` blocks for elements that should naturally be interactive clickable buttons or links.
- **Accessibility (a11y):** Ensure all elements have appropriate `aria-*` tags, image `alt` text, and form labels to comply with WCAG standards.
