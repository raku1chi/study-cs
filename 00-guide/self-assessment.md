# 自己診断とスキルマップ

> 今の実力を把握し、どこから学ぶべきかを決めるためのページです。学習を始める前と、その後 3 か月ごとに見直してください。

## 1. レベルの定義

このカリキュラムでは、各領域の習熟度を 5 段階で考えます。

| レベル | 名称 | 状態 |
|---|---|---|
| L0 | 未習得 | 用語を聞いたことがない、または説明できない |
| L1 | 説明できる | 仕組みを自分の言葉で説明でき、専門家の話についていける |
| L2 | 実装・運用できる | 実際に作れる・使える・障害を調査できる |
| L3 | 設計・判断できる | 要件に応じてトレードオフを評価し、設計や技術選定を主導できる |
| L4 | 組織を導ける | 組織の標準や戦略を定め、人を育て、経営の言葉で説明できる |

## 2. 役割ごとの目標レベル

CTO はすべての技術領域で L4 である必要はありません。求められるのは、**すべての領域で L2 以上の土台を持ち、事業に大きく影響する領域では L3 の判断力を、組織と経営では L3〜L4 の力を持つ** ことです。

| 領域 | 主な部 | シニアエンジニア | テックリード / EM | CTO |
|---|---|---|---|---|
| コンピュータシステム（ハードウェア・OS） | 1, 4 | L2 | L2 | L2 |
| 数学・アルゴリズム | 2 | L2 | L2 | L2 |
| プログラミング言語 | 3 | L2〜L3 | L2〜L3 | L2 |
| ネットワーク | 5 | L2 | L2 | L2 |
| データベース | 6 | L2〜L3 | L3 | L3 |
| 分散システム | 7 | L2 | L3 | L3 |
| ソフトウェアエンジニアリング | 8 | L3 | L3 | L3〜L4 |
| アーキテクチャ・システム設計 | 9 | L2〜L3 | L3 | L3〜L4 |
| クラウド・SRE | 10 | L2 | L3 | L3〜L4 |
| セキュリティ | 11 | L2 | L2〜L3 | L3〜L4 |
| データ・AI | 12 | L1〜L2 | L2 | L3 |
| 技術リーダーシップ・マネジメント | 13 | L1 | L3 | L4 |
| 経営・戦略・財務・ガバナンス | 14 | L0〜L1 | L1〜L2 | L3〜L4 |

表の「L3〜L4」は、会社の規模やステージによって求められる水準が変わることを示しています。たとえば数十人のスタートアップの CTO は、自らアーキテクチャを設計する（L3）ことが多く、数百人規模になると組織の標準と戦略を定める（L4）ことが中心になります（[14.1 CTOの役割](../14-cto/01-role-of-cto/README.md)）。

## 3. 部ごとの診断質問

各質問に、次の 3 段階で答えてください。**必ず頭の中ではなく、紙やエディタに答えを書き出してから** 判定します（書けないことは、説明できないことです）。

- ◎ 自信を持って説明できる／実装できる
- ○ だいたい分かるが、細部があいまい
- × 説明できない

**判定の目安**

- その部の質問がすべて ◎ → 各章の「理解度チェック」と ★★★ の演習だけを解いて先へ進む。
- ○ や × がある → その質問の章を本文から学ぶ。
- 半分以上が × → その部を最初から順に学ぶ。

### 第1部 コンピュータの基礎

| # | 質問 | 章 |
|---|---|---|
| 1 | 2 の補数で負の数を表す理由と、32 ビット符号付き整数の範囲を説明できる | [1.1](../01-computer-systems/01-data-representation/README.md) |
| 2 | `0.1 + 0.2` が `0.3` にならない理由と、金額の正しい扱い方を説明できる | [1.1](../01-computer-systems/01-data-representation/README.md) |
| 3 | UTF-8 で日本語 1 文字が何バイトになるかを、ビットパターンから説明できる | [1.1](../01-computer-systems/01-data-representation/README.md) |
| 4 | CPU が命令をフェッチ・デコード・実行する流れと、パイプラインが性能を上げる理由を説明できる | [1.2](../01-computer-systems/02-logic-and-cpu/README.md) |
| 5 | L1 キャッシュ・メインメモリ・SSD・データセンター間の通信で、アクセス時間の桁がどれくらい違うか言える | [1.3](../01-computer-systems/03-memory-hierarchy/README.md) |
| 6 | 2 次元配列を行方向と列方向に走査すると速度が変わる理由を説明できる | [1.3](../01-computer-systems/03-memory-hierarchy/README.md) |
| 7 | C のソースコードが実行ファイルになるまでの段階と、静的リンクと動的リンクの違いを説明できる | [1.4](../01-computer-systems/04-how-programs-run/README.md) |

### 第2部 数学とアルゴリズム

| # | 質問 | 章 |
|---|---|---|
| 1 | 数学的帰納法とループ不変条件の関係を説明できる | [2.1](../02-math-and-algorithms/01-discrete-math/README.md) |
| 2 | 「精度 99% のアラート」が鳴ったとき、本当に異常である確率をベイズの定理で見積もれる | [2.2](../02-math-and-algorithms/02-probability-statistics/README.md) |
| 3 | レイテンシを平均値ではなくパーセンタイルで見るべき理由を説明できる | [2.2](../02-math-and-algorithms/02-probability-statistics/README.md) |
| 4 | サーバーの利用率が 100% に近づくと待ち時間が急増する理由を、待ち行列理論で説明できる | [2.2](../02-math-and-algorithms/02-probability-statistics/README.md) |
| 5 | 動的配列の末尾への追加が「償却 O(1)」である理由を説明できる | [2.3](../02-math-and-algorithms/03-complexity/README.md) |
| 6 | ハッシュテーブルの衝突の解決方法と、性能が最悪になる条件を説明できる | [2.4](../02-math-and-algorithms/04-basic-data-structures/README.md) |
| 7 | ダイクストラ法とトポロジカルソートを実装でき、それぞれの使いどころを言える | [2.5](../02-math-and-algorithms/05-trees-heaps-graphs/README.md) |
| 8 | 動的計画法が使える問題の条件を説明し、編集距離を実装できる | [2.6](../02-math-and-algorithms/06-algorithm-design/README.md) |
| 9 | 正規表現が ReDoS を引き起こす仕組みと、停止性問題が静的解析ツールに与える限界を説明できる | [2.7](../02-math-and-algorithms/07-theory-of-computation/README.md) |

### 第3部 プログラミング言語

| # | 質問 | 章 |
|---|---|---|
| 1 | 継承とコンポジションのトレードオフを、具体例で説明できる | [3.1](../03-programming-languages/01-paradigms/README.md) |
| 2 | 静的型付けと動的型付け、名前的型付けと構造的型付けの違いを説明できる | [3.2](../03-programming-languages/02-type-systems/README.md) |
| 3 | 「不正な状態を表現できない型」の設計例を示せる | [3.2](../03-programming-languages/02-type-systems/README.md) |
| 4 | 参照カウントとトレーシング GC の違いと、GC がテールレイテンシに与える影響を説明できる | [3.3](../03-programming-languages/03-memory-management/README.md) |
| 5 | 再帰下降パーサで、演算子の優先順位と結合性を正しく扱える | [3.4](../03-programming-languages/04-build-an-interpreter/README.md) |

### 第4部 オペレーティングシステム

| # | 質問 | 章 |
|---|---|---|
| 1 | `fork` と `exec` の違いと、ゾンビプロセスが生まれる理由を説明できる | [4.1](../04-operating-systems/01-processes-and-syscalls/README.md) |
| 2 | SIGTERM を受けたアプリケーションが安全に終了する（グレースフルシャットダウン）ために必要なことを説明できる | [4.1](../04-operating-systems/01-processes-and-syscalls/README.md) |
| 3 | 仮想メモリ・ページフォルト・TLB の関係を説明できる | [4.2](../04-operating-systems/02-virtual-memory/README.md) |
| 4 | `write()` が成功してもデータが失われうる理由と、`fsync` の役割を説明できる | [4.3](../04-operating-systems/03-filesystems-and-io/README.md) |
| 5 | デッドロックが起きる 4 つの条件と、ロックの順序による回避方法を説明できる | [4.4](../04-operating-systems/04-concurrency/README.md) |
| 6 | コンテナが namespace と cgroup でどう実現されているか、VM と比べて分離の強さがどう違うかを説明できる | [4.5](../04-operating-systems/05-virtualization-and-containers/README.md) |

### 第5部 コンピュータネットワーク

| # | 質問 | 章 |
|---|---|---|
| 1 | `10.0.0.0/16` のような CIDR 表記から、アドレスの範囲とホスト数を計算できる | [5.1](../05-networking/01-layers-and-ip/README.md) |
| 2 | TCP の 3 ウェイハンドシェイク・再送・輻輳制御が、それぞれ何のためにあるか説明できる | [5.2](../05-networking/02-tcp-and-udp/README.md) |
| 3 | TCP はバイトストリームなので、アプリケーション側でメッセージの区切りが必要になる理由を説明できる | [5.2](../05-networking/02-tcp-and-udp/README.md) |
| 4 | システム移行の前に DNS の TTL を下げておく理由を説明できる | [5.3](../05-networking/03-dns-http-tls/README.md) |
| 5 | TLS が何を保証するかと、証明書の期限が切れると何が起きるかを説明できる | [5.3](../05-networking/03-dns-http-tls/README.md) |
| 6 | ブラウザに URL を入力してからページが表示されるまでを、層ごとの処理として説明できる | [5.4](../05-networking/04-web-architecture/README.md) |
| 7 | CORS が何を防ぎ、何を防がないかを説明できる | [5.4](../05-networking/04-web-architecture/README.md) |

### 第6部 データベース

| # | 質問 | 章 |
|---|---|---|
| 1 | ウィンドウ関数と再帰 CTE を使った SQL を書ける | [6.1](../06-databases/01-relational-model-and-sql/README.md) |
| 2 | NULL を含む列に対する `NOT IN` が期待どおりに動かない理由を説明できる | [6.1](../06-databases/01-relational-model-and-sql/README.md) |
| 3 | 複合インデックスで列の順序が重要な理由を説明できる | [6.2](../06-databases/02-indexes-and-query-processing/README.md) |
| 4 | `OFFSET` によるページングが遅くなる理由と、キーセットページングを説明できる | [6.2](../06-databases/02-indexes-and-query-processing/README.md) |
| 5 | 書き込みスキューの例を挙げ、スナップショット分離では防げない理由を説明できる | [6.3](../06-databases/03-transactions/README.md) |
| 6 | WAL によって、クラッシュ後にデータが復旧できる仕組みを説明できる | [6.4](../06-databases/04-storage-and-recovery/README.md) |
| 7 | B 木系と LSM 木系のストレージエンジンのトレードオフを説明できる | [6.4](../06-databases/04-storage-and-recovery/README.md) |
| 8 | RDB・ドキュメント DB・KVS・検索エンジン・データウェアハウスの使い分けを説明できる | [6.5](../06-databases/05-beyond-relational/README.md) |

### 第7部 分散システム

| # | 質問 | 章 |
|---|---|---|
| 1 | 分散システムで「遅いノード」と「停止したノード」を区別できない理由を説明できる | [7.1](../07-distributed-systems/01-fundamentals/README.md) |
| 2 | 実時間の時計ではなく論理時計（Lamport 時計・ベクタークロック）が必要になる理由を説明できる | [7.1](../07-distributed-systems/01-fundamentals/README.md) |
| 3 | W + R > N のクォーラムで最新の値が読める理由を説明できる | [7.2](../07-distributed-systems/02-replication-and-consistency/README.md) |
| 4 | 線形化可能性と結果整合性の違いと、それぞれが適するデータの例を挙げられる | [7.2](../07-distributed-systems/02-replication-and-consistency/README.md) |
| 5 | コンシステントハッシュで、ノード追加時に移動するデータが少なくて済む理由を説明できる | [7.3](../07-distributed-systems/03-partitioning/README.md) |
| 6 | Raft のリーダー選出の仕組みと、ノード数を奇数にする理由を説明できる | [7.4](../07-distributed-systems/04-consensus-and-coordination/README.md) |
| 7 | 分散ロックにフェンシングトークンが必要な理由を説明できる | [7.4](../07-distributed-systems/04-consensus-and-coordination/README.md) |
| 8 | Transactional Outbox パターンが解決する問題を説明できる | [7.5](../07-distributed-systems/05-messaging-and-events/README.md) |

### 第8部 ソフトウェアエンジニアリング

| # | 質問 | 章 |
|---|---|---|
| 1 | 「深いモジュール」と「浅いモジュール」の違いを、例を挙げて説明できる | [8.1](../08-software-engineering/01-code-quality-and-design/README.md) |
| 2 | モックを使いすぎるとテストが壊れやすくなる理由を説明できる | [8.2](../08-software-engineering/02-testing/README.md) |
| 3 | Git のコミットが、どのようなオブジェクトで構成されているか説明できる | [8.3](../08-software-engineering/03-version-control-and-review/README.md) |
| 4 | フィーチャーフラグとカナリアリリースで、デプロイとリリースを分離する方法を説明できる | [8.4](../08-software-engineering/04-ci-cd-and-release/README.md) |
| 5 | カラム名の変更を無停止で行う expand–contract の手順を説明できる | [8.4](../08-software-engineering/04-ci-cd-and-release/README.md) |
| 6 | 技術的負債を「変更頻度 × 複雑さ」のホットスポットで可視化できる | [8.5](../08-software-engineering/05-refactoring-and-tech-debt/README.md) |
| 7 | 過去のスループットから、モンテカルロ法で完了日を予測できる | [8.6](../08-software-engineering/06-process-and-documentation/README.md) |

### 第9部 アーキテクチャとシステム設計

| # | 質問 | 章 |
|---|---|---|
| 1 | 品質特性シナリオを書き、アーキテクチャ上の決定を ADR として記録できる | [9.1](../09-architecture/01-architecture-fundamentals/README.md) |
| 2 | モジュラーモノリスとマイクロサービスを選ぶ基準を説明できる | [9.2](../09-architecture/02-architecture-styles/README.md) |
| 3 | 集約（aggregate）の境界の決め方を説明できる | [9.3](../09-architecture/03-domain-driven-design/README.md) |
| 4 | 冪等キーによって、決済 API の二重実行を防ぐ仕組みを説明できる | [9.4](../09-architecture/04-api-design/README.md) |
| 5 | API の後方互換性を壊す変更の例を 3 つ以上挙げられる | [9.4](../09-architecture/04-api-design/README.md) |
| 6 | キャッシュのスタンピード（thundering herd）とその対策を説明できる | [9.5](../09-architecture/05-scalability-and-performance/README.md) |
| 7 | DAU（日次アクティブユーザー数）から、QPS・ストレージ容量・サーバー台数を概算できる | [9.5](../09-architecture/05-scalability-and-performance/README.md) |
| 8 | 決済システムや予約システムを、要件から障害時の振る舞いまで設計できる | [9.6](../09-architecture/06-system-design-cases/README.md) |

### 第10部 クラウドとSRE

| # | 質問 | 章 |
|---|---|---|
| 1 | IAM で最小権限を実現する方法と、長期間有効なアクセスキーを避けるべき理由を説明できる | [10.1](../10-cloud-and-sre/01-cloud-and-iac/README.md) |
| 2 | Kubernetes のリコンサイルループ（宣言的 API）の考え方を説明できる | [10.2](../10-cloud-and-sre/02-containers-and-kubernetes/README.md) |
| 3 | liveness probe の誤った設定が障害を拡大させる理由を説明できる | [10.2](../10-cloud-and-sre/02-containers-and-kubernetes/README.md) |
| 4 | SLI・SLO・SLA・エラーバジェットの関係を説明し、バーンレートアラートを設計できる | [10.3](../10-cloud-and-sre/03-reliability-engineering/README.md) |
| 5 | 可用性 99.9% のサービス 3 つに直列に依存するシステム全体の可用性を計算できる | [10.3](../10-cloud-and-sre/03-reliability-engineering/README.md) |
| 6 | パーセンタイルを平均してはいけない理由と、ヒストグラムの役割を説明できる | [10.4](../10-cloud-and-sre/04-observability/README.md) |
| 7 | インシデントコマンダーの役割と、非難しないポストモーテムの書き方を説明できる | [10.5](../10-cloud-and-sre/05-incident-management/README.md) |
| 8 | リザーブドインスタンス・Savings Plans・スポットインスタンスの使い分けを説明できる | [10.6](../10-cloud-and-sre/06-finops/README.md) |

### 第11部 セキュリティ

| # | 質問 | 章 |
|---|---|---|
| 1 | STRIDE を使って、あるシステムの脅威モデリングができる | [11.1](../11-security/01-security-principles/README.md) |
| 2 | ECB モードが危険な理由と、認証付き暗号（AEAD）を使うべき理由を説明できる | [11.2](../11-security/02-cryptography/README.md) |
| 3 | パスワードの保存に SHA-256 のような高速なハッシュ関数を使ってはいけない理由を説明できる | [11.2](../11-security/02-cryptography/README.md) |
| 4 | OAuth 2.0 の認可コードフロー（PKCE 付き）の流れと、OAuth が「認証」の仕組みではない理由を説明できる | [11.3](../11-security/03-authn-authz/README.md) |
| 5 | JWT を検証するときに必ず確認すべき項目を挙げられる | [11.3](../11-security/03-authn-authz/README.md) |
| 6 | SQL インジェクション・XSS・CSRF・SSRF の仕組みと対策を説明できる | [11.4](../11-security/04-web-security/README.md) |
| 7 | SBOM の役割と、脆弱性の優先度付け（CVSS・EPSS・KEV）を説明できる | [11.5](../11-security/05-security-operations/README.md) |

### 第12部 データとAI

| # | 質問 | 章 |
|---|---|---|
| 1 | スタースキーマと SCD Type 2 を説明できる | [12.1](../12-data-and-ai/01-data-engineering/README.md) |
| 2 | データリークの例を挙げ、それがモデルの評価を過大にする理由を説明できる | [12.2](../12-data-and-ai/02-machine-learning/README.md) |
| 3 | 不均衡なデータで正解率（accuracy）が役に立たない理由と、代わりに使う指標を説明できる | [12.2](../12-data-and-ai/02-machine-learning/README.md) |
| 4 | 誤差逆伝播法（自動微分）の仕組みを説明できる | [12.3](../12-data-and-ai/03-deep-learning/README.md) |
| 5 | Transformer のアテンションの計算式の意味を説明できる | [12.3](../12-data-and-ai/03-deep-learning/README.md) |
| 6 | RAG の構成要素と、検索の品質を測る指標を説明できる | [12.4](../12-data-and-ai/04-llm-applications/README.md) |
| 7 | プロンプトインジェクションの脅威と、ツールを使うエージェントの防御策を説明できる | [12.4](../12-data-and-ai/04-llm-applications/README.md) |
| 8 | データドリフトの検知方法と、LLM アプリケーションの評価を CI に組み込む方法を説明できる | [12.5](../12-data-and-ai/05-mlops-llmops/README.md) |

### 第13部 技術リーダーシップ

| # | 質問 | 章 |
|---|---|---|
| 1 | Staff エンジニアの役割の型（テックリード・アーキテクト・ソルバー・右腕）を説明できる | [13.1](../13-technical-leadership/01-tech-lead-and-staff/README.md) |
| 2 | 設計ドキュメントを書き、設計レビューを運営できる | [13.2](../13-technical-leadership/02-technical-decisions/README.md) |
| 3 | SBI モデルを使って、具体的なフィードバックを伝えられる | [13.3](../13-technical-leadership/03-engineering-management/README.md) |
| 4 | 構造化面接（評価基準とルーブリック）を設計できる | [13.4](../13-technical-leadership/04-hiring/README.md) |
| 5 | キャリアラダーとキャリブレーションの目的を説明できる | [13.5](../13-technical-leadership/05-growth-and-evaluation/README.md) |
| 6 | チームトポロジーの 4 つのチームタイプと、コンウェイの法則の関係を説明できる | [13.6](../13-technical-leadership/06-team-and-org-design/README.md) |
| 7 | DORA の 4 指標を定義し、それを個人の評価に使ってはいけない理由を説明できる | [13.7](../13-technical-leadership/07-delivery-and-productivity/README.md) |

### 第14部 CTOの仕事

| # | 質問 | 章 |
|---|---|---|
| 1 | 会社のステージ（創業期・成長期・上場準備期）によって CTO の役割がどう変わるか説明できる | [14.1](../14-cto/01-role-of-cto/README.md) |
| 2 | 事業戦略と結びついた技術戦略を「診断・基本方針・一貫した行動」の形で書ける | [14.2](../14-cto/02-technology-strategy/README.md) |
| 3 | SaaS の粗利率・NRR・CAC 回収期間を計算し、インフラ費用が与える影響を説明できる | [14.3](../14-cto/03-business-and-finance/README.md) |
| 4 | 取締役会向けに、技術の状況とリスクを 1 枚で報告できる | [14.4](../14-cto/04-executive-communication/README.md) |
| 5 | 請負と準委任の違い、偽装請負のリスク、個人データ漏えい時の報告義務を概説できる | [14.5](../14-cto/05-governance-risk-compliance/README.md) |
| 6 | ランサムウェア被害の初動（最初の 24 時間）を指揮できる | [14.6](../14-cto/06-crisis-management/README.md) |
| 7 | 技術デューデリジェンスで確認すべき観点を挙げられる | [14.7](../14-cto/07-due-diligence-and-ma/README.md) |
| 8 | 社内の AI 利用ポリシーと、AI への投資判断の枠組みを作れる | [14.8](../14-cto/08-ai-strategy/README.md) |

## 4. 経験のチェックリスト

知識はこのカリキュラムで身につけられますが、次のような **経験** は実務でしか得られません。CTO を目指すなら、学習と並行して、今の職場でこれらの機会を意識的に取りに行きましょう。すべてがそろっている必要はありませんが、欠けている項目は「次の半年で取りに行く機会」のリストになります。

**技術的なリーダーシップ**

- [ ] 複数人のチームで、ある機能やシステムの技術的な方向性を決め、完成まで導いた
- [ ] 設計ドキュメントを書き、他チームを含むレビューを経て合意を得た
- [ ] 重大な障害でインシデントコマンダー（対応の指揮）を務め、ポストモーテムをまとめた
- [ ] 技術選定を行い、その理由を ADR などで文書化した
- [ ] 大きな移行（データベース、クラウド、フレームワークなど）を計画し、完了させた

**人と組織**

- [ ] メンバーの 1on1 を継続的に行った
- [ ] 採用面接官を 20 回以上務め、評価基準の設計や見直しに関わった
- [ ] 新しいメンバーのオンボーディングを設計・担当した
- [ ] 評価・昇格の判断に関わった
- [ ] パフォーマンスの課題や対立など、難しい人の問題に向き合った

**事業と経営**

- [ ] 人件費やクラウド費用を含む予算の策定・管理に関わった
- [ ] 経営会議や取締役会、顧客の経営層に対して、技術的な内容を説明した
- [ ] 顧客のセキュリティチェックシートや監査・認証（ISMS、SOC 2 など）の対応に関わった
- [ ] ベンダーの選定や契約交渉に関わった
- [ ] 事業計画やプロダクトロードマップの策定に、技術の立場から関わった

## 5. 定期的な見直し

- **3 か月ごと** に、診断質問に答え直しましょう。◎ が増えていく様子を記録しておくと、成長を実感できます。
- 回答は fork したリポジトリの `notes/` に日付付きで保存しておくのがお勧めです（例: `notes/self-assessment-2026-10.md`）。
- 役割が変わったとき（テックリードになった、マネージャーになった、など）は、[2. 役割ごとの目標レベル](#2-役割ごとの目標レベル) を見直し、次に伸ばすべき領域を決め直してください。
