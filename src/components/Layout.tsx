import { Outlet, Link } from "react-router-dom";

export function Layout() {
  return (
    <div className="site-container">
      <header className="site-header">
        <nav>
          <Link to="/" className="site-logo">
            My Private Site
          </Link>
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
