import { Suspense, lazy } from "react";
import { Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";

const HomePage = lazy(() =>
  import("./pages/HomePage").then((module) => ({ default: module.HomePage })),
);
const ProgressPage = lazy(() =>
  import("./pages/ProgressPage").then((module) => ({ default: module.ProgressPage })),
);
const ResultsPage = lazy(() =>
  import("./pages/ResultsPage").then((module) => ({ default: module.ResultsPage })),
);

export default function App() {
  return (
    <Shell>
      <Suspense fallback={<div className="route-loading">Loading workspace...</div>}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/jobs/:jobId/progress" element={<ProgressPage />} />
          <Route path="/jobs/:jobId/results" element={<ResultsPage />} />
        </Routes>
      </Suspense>
    </Shell>
  );
}
