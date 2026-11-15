import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
if (typeof global !== "undefined" && !global.ResizeObserver) {
  global.ResizeObserver = ResizeObserverMock;
}
if (typeof window !== "undefined" && !window.ResizeObserver) {
  window.ResizeObserver = ResizeObserverMock;
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  document.documentElement.dataset.theme = "dark";
});
