import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Home } from "./pages/Home";
import { NotFound } from "./pages/NotFound";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        {/* Drive から同期したページをここに追加 */}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
