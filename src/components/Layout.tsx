import { Outlet, Link, useLocation } from "react-router-dom";
import { useEffect, useState, useRef } from "react";

interface PageMeta {
  title: string;
  path: string;
}

const NAV_VISIBLE_LIMIT = 5; // これを超えたら "More ▾" にまとめる

export function Layout() {
  const [pages, setPages] = useState<PageMeta[]>([]);
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);
  const location = useLocation();

  useEffect(() => {
    fetch("/pages.json")
      .then((res) => {
        if (!res.ok) throw new Error("Could not find pages.json");
        return res.json();
      })
      .then((data) => setPages(data))
      .catch((err) => console.error(err));
  }, []);

  // ドロップダウン外クリックで閉じる
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) {
        setMoreOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ページ遷移でドロップダウンを閉じる
  useEffect(() => {
    setMoreOpen(false);
  }, [location]);

  const primary = pages.slice(0, NAV_VISIBLE_LIMIT);
  const overflow = pages.slice(NAV_VISIBLE_LIMIT);
  const hasOverflow = overflow.length > 0;
  const overflowActive = overflow.some((p) => p.path === location.pathname);

  return (
    <div className="site-container">
      <header className="site-header">
        <nav className="site-nav">
          <Link to="/" className="site-logo">
            <span className="logo-icon">◈</span>
            <span className="logo-text">HOME</span>
          </Link>

          <div className="nav-divider" />

          <div className="nav-links">
            {primary.map((p) => (
              <Link
                key={p.path}
                to={p.path}
                className={`nav-btn${location.pathname === p.path ? " active" : ""}`}
              >
                {p.title}
              </Link>
            ))}

            {hasOverflow && (
              <div className="nav-more" ref={moreRef}>
                <button
                  className={`nav-btn nav-more-trigger${overflowActive ? " active" : ""}${moreOpen ? " open" : ""}`}
                  onClick={() => setMoreOpen((v) => !v)}
                  aria-expanded={moreOpen}
                  aria-haspopup="true"
                >
                  More
                  <span className="more-chevron">{moreOpen ? "▲" : "▼"}</span>
                </button>

                {moreOpen && (
                  <div className="nav-dropdown" role="menu">
                    {overflow.map((p) => (
                      <Link
                        key={p.path}
                        to={p.path}
                        className={`dropdown-item${location.pathname === p.path ? " active" : ""}`}
                        role="menuitem"
                      >
                        <span className="dropdown-bullet">›</span>
                        {p.title}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </nav>
      </header>

      <main className="site-main">
        <Outlet />
      </main>

      <footer className="site-footer">
        <span className="footer-mark">◈</span>
        <p>&copy; {new Date().getFullYear()} My Private Site</p>
      </footer>
    </div>
  );
}
