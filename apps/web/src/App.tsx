import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import NotFound from "@/pages/NotFound";

const Home = lazy(() => import("@/pages/Home"));
const Companies = lazy(() => import("@/pages/Companies"));
const Screener = lazy(() => import("@/pages/Screener"));
const Macro = lazy(() => import("@/pages/Macro"));
const Valuation = lazy(() => import("@/pages/Valuation"));
const Portfolios = lazy(() => import("@/pages/Portfolios"));
const Backtest = lazy(() => import("@/pages/Backtest"));
const Research = lazy(() => import("@/pages/Research"));
const Reports = lazy(() => import("@/pages/Reports"));
const Alerts = lazy(() => import("@/pages/Alerts"));
const Admin = lazy(() => import("@/pages/Admin"));
const Settings = lazy(() => import("@/pages/Settings"));

function PageFallback() {
  return (
    <div className="space-y-3 p-4">
      <div className="skeleton h-6 w-56" />
      <div className="skeleton h-3 w-96 max-w-full" />
      <div className="grid gap-3 pt-2 lg:grid-cols-3">
        <div className="skeleton h-56 lg:col-span-2" />
        <div className="skeleton h-56" />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Home />} />
          <Route path="companies" element={<Companies />} />
          <Route path="companies/:symbol" element={<Companies />} />
          <Route path="screener" element={<Screener />} />
          <Route path="macro" element={<Macro />} />
          <Route path="valuation" element={<Valuation />} />
          <Route path="valuation/:modelId" element={<Valuation />} />
          <Route path="portfolios" element={<Portfolios />} />
          <Route path="portfolios/:portfolioId" element={<Portfolios />} />
          <Route path="backtest" element={<Backtest />} />
          <Route path="research" element={<Research />} />
          <Route path="reports" element={<Reports />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="admin" element={<Admin />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
