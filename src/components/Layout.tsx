import { Outlet, Link } from "react-router-dom";
import { useEffect, useState } from "react";

interface PageMeta {
  title: string;
  path: string;
}

export function Layout() {
  const [pages, setPages] = useState<PageMeta[]>([]);

  useEffect(() => {
    fetch('/pages.json')
      .then(res => {
        if (!res.ok) throw new Error("Could not find pages.json");
        return res.json();
      })
      .then(data => setPages(data))
      .catch(err => console.error(err));
  }, []);

  return (
    <div className="site-container">
      <header className="site-header">
        <nav>
          <Link to="/" className="site-logo">
            🏠 Home
          </Link>
          {pages.map((p, i) => (
            <a key={i} href={p.path} className="nav-btn" style={{ padding: '0 8px', borderRadius: '4px' }}>
              {p.title}
            </a>
          ))}
        </nav>
      </header>

      <main className="site-main">
        <Outlet />
      </main>

      <footer className="site-footer">
        <p>&copy; {new Date().getFullYear()} My Private Site</p>
      </footer>
    </div>
  );
}
