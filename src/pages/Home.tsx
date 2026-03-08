import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

interface PageMeta {
  title: string;
  path: string;
}

export function Home() {
  const [pages, setPages] = useState<PageMeta[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/pages.json")
      .then((res) => {
        if (!res.ok) throw new Error("pages.json not found");
        return res.json();
      })
      .then((data: PageMeta[]) => setPages(data))
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <article className="home-page fade-in">
      <div className="home-hero">
        <p className="home-eyebrow">PRIVATE SITE</p>
        <h1 className="home-title">Welcome</h1>
        <p className="home-desc">
          Google Drive で管理されたプライベートサイト。
          <br />
          コンテンツは Drive から自動同期されます。
        </p>
      </div>

      <section className="home-toc">
        <div className="toc-header">
          <h2 className="toc-title">Contents</h2>
          <span className="toc-count">
            {loading ? "—" : `${pages.length} pages`}
          </span>
        </div>

        {loading && (
          <div className="toc-loading">
            <span className="loading-dot" />
            <span className="loading-dot" />
            <span className="loading-dot" />
          </div>
        )}

        {!loading && pages.length === 0 && (
          <div className="toc-empty">
            <p>ページがまだ同期されていません。</p>
            <p className="toc-empty-hint">
              Drive に <code>.tsx</code> または <code>.html</code> ファイルを追加して同期スクリプトを実行してください。
            </p>
          </div>
        )}

        {!loading && pages.length > 0 && (
          <div className="toc-grid">
            {pages.map((p, i) => {
              const isStatic = p.path.endsWith(".html");
              const cardProps = {
                key: p.path,
                className: "toc-card fade-in",
                style: { animationDelay: `${i * 0.05}s` },
              };
              const children = (
                <>
                  <span className="toc-card-index">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span className="toc-card-title">{p.title}</span>
                  <span className="toc-card-arrow">→</span>
                </>
              );
              return isStatic ? (
                <a href={p.path} {...cardProps}>{children}</a>
              ) : (
                <Link to={p.path} {...cardProps}>{children}</Link>
              );
            })}
          </div>
        )}
      </section>
    </article>
  );
}
