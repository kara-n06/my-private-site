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
        <nav style={{ display: 'flex', gap: '15px', padding: '10px 20px', borderBottom: '1px solid #ddd', overflowX: 'auto', background: '#f8f9fa' }}>
          <Link to="/" className="site-logo" style={{ fontWeight: 'bold', color: '#000', textDecoration: 'none' }}>
            🏠 Home
          </Link>
          {pages.map((p, i) => (
            <a key={i} href={p.path} style={{ color: '#0066cc', textDecoration: 'none' }}>
              {p.title}
            </a>
          ))}
        </nav>
      </header>

      <main className="site-main" style={{ padding: '20px' }}>
        <Outlet />
      </main>

      <footer className="site-footer" style={{ padding: '20px', borderTop: '1px solid #ddd', marginTop: '40px', textAlign: 'center' }}>
        <p>&copy; {new Date().getFullYear()} My Private Site</p>
      </footer>
    </div>
  );
}
