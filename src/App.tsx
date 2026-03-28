import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Home } from "./pages/Home";
import { NotFound } from "./pages/NotFound";
import React, { Suspense } from "react";

// 動的に全ての同期ページをインポート
const pages = import.meta.glob('./content/**/*.{tsx,jsx}');

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />

        {/* Drive から同期した .tsx ページを動的に追加 */}
        {Object.keys(pages).map((path) => {
          const name = path.match(/\.\/content\/(.*)\.(?:tsx|jsx)$/)?.[1];
          if (!name) return null;

          const Component = React.lazy(pages[path] as any);
          const routePath = `/${name.toLowerCase()}`;

          return (
            <Route
              key={routePath}
              path={routePath}
              element={
                <Suspense fallback={<div>Loading...</div>}>
                  <Component />
                </Suspense>
              }
            />
          );
        })}

        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
