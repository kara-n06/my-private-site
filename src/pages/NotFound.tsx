import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <article>
      <h1>404 - Not Found</h1>
      <p>ページが見つかりませんでした。</p>
      <Link to="/">トップに戻る</Link>
    </article>
  );
}
