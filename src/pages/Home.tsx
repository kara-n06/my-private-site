import { useEffect, useState } from "react";

interface PageMeta {
  title: string;
  path: string;
}

export function Home() {
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
    <article>
      <h1>Welcome</h1>
      <p>
        Google Drive で管理されたプライベートサイトです。
        コンテンツは Drive から自動同期されます。
      </p>

      <h2>ナビゲーション</h2>
      {pages.length > 0 ? (
        <ul>
          {pages.map((p, i) => (
            <li key={i}>
              <a href={p.path}>{p.title}</a>
            </li>
          ))}
        </ul>
      ) : (
        <p>同期されたページはありません。</p>
      )}
    </article>
  );
}
