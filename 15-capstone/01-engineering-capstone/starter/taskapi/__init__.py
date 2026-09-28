"""taskapi — 15.1 実装プロジェクトのスターター（チーム向けタスク管理API）

Python 3.10 以上の標準ライブラリだけで書いた、最小限の骨組みです。
構成・起動方法・拡張の進め方は 15-capstone/01-engineering-capstone/README.md を参照してください。

モジュールの役割:
    config     設定（環境変数 → Config）
    timeutil   時刻（UTC・ISO 8601）
    web        最小限の WSGI ツールキット（Request / Response / HTTPError / Router）
    db         SQLite への接続・トランザクション・マイグレーション
    store      データアクセス層（すべての関数がテナントIDを取る）
    auth       認証（※開発用の仮実装。M3 で置き換える）
    app        ルーティングとハンドラ（WSGI アプリケーション本体）
    server     HTTP サーバー（wsgiref ＋ スレッド）
    __main__   コマンドライン（migrate / create-tenant / serve）

拡張ポイントには `TODO(M2)` のように、対応するマイルストーンの番号を書いてあります。
"""

__version__ = "0.1.0"
