# 環境構築

> 演習を始めるための準備です。必要なのは Python 3.10 以上と Git だけで、追加のパッケージのインストールは不要です。

## 1. 必要なもの

| ツール | 必須/任意 | 用途 |
|---|---|---|
| Python 3.10 以上 | **必須** | 演習の実装とテスト（標準ライブラリのみを使用） |
| Git | **必須** | リポジトリの取得、自分の進捗の記録 |
| テキストエディタ | **必須** | VS Code、PyCharm、Vim など何でもよい |
| C コンパイラ（gcc / clang） | 任意 | 第 1 部・第 3 部・第 4 部の本文中の C のコード例を動かす |
| `sqlite3` コマンド | 任意 | 第 6 部で SQL を対話的に試す（演習自体は Python 組み込みの `sqlite3` モジュールで動く） |
| `strace`（Linux のみ） | 任意 | 第 4 部でシステムコールを観察する |
| `dig`・`curl`・`openssl` | 任意 | 第 5 部でネットワークを観察する |
| Docker | 任意 | 第 4 部・第 10 部のコンテナの実習 |

**OS は macOS・Linux・Windows（WSL2）のいずれか** を推奨します。第 4 部の演習の一部は `os.fork` やシグナルなど Unix の機能を使うため、Windows で直接実行するとスキップされます。

## 2. OS 別の準備

### macOS

```bash
xcode-select --install          # Git と clang（C コンパイラ）が入る
python3 --version               # 3.10 以上であることを確認
```

Python が古い、または入っていない場合は、[python.org](https://www.python.org/downloads/) のインストーラか、Homebrew（`brew install python`）でインストールします。

### Linux（Ubuntu / Debian の例）

```bash
sudo apt update
sudo apt install -y python3 git build-essential sqlite3 strace dnsutils curl
python3 --version
```

ディストリビューションの Python が 3.10 より古い場合は、後述の uv などで新しいバージョンを入れてください。

### Windows

WSL2（Windows Subsystem for Linux）上の Ubuntu を使うのが最も簡単です。PowerShell を管理者として開き、次を実行して再起動します。

```powershell
wsl --install
```

再起動後に起動する Ubuntu の中で、上の「Linux」の手順を実行してください。以降の作業はすべて WSL の中で行います（VS Code を使う場合は WSL 拡張機能で WSL 内のフォルダを開けます）。

### 補足: Python のバージョン管理

複数のバージョンの Python を使い分けたい場合は、[uv](https://docs.astral.sh/uv/) などのツールが便利です。

```bash
uv python install 3.12
uv run --python 3.12 python tools/check.py 1.1
```

## 3. リポジトリを準備する

### 自分用のコピーを作る

演習の解答や進捗を自分のリポジトリに記録できるように、GitHub で **fork** してから clone するのがお勧めです。

```bash
git clone https://github.com/<あなたのアカウント>/study-cs.git
cd study-cs
```

### 教材の更新を取り込む（fork した場合）

元のリポジトリに教材の修正や追加があったときは、次のように取り込みます。

```bash
git remote add upstream https://github.com/<元のリポジトリ>/study-cs.git   # 最初の 1 回だけ
git fetch upstream
git merge upstream/main
```

演習ファイル（`exercises/` 内のスタブ）を自分で編集しているため、同じファイルが更新されていると競合することがあります。その場合は、自分の実装を残す形で競合を解消してください。

## 4. 動作確認

リポジトリのルートで次を実行します。

```bash
python3 tools/check.py --solutions 1.1
```

次のように表示されれば、環境は正しく動いています（解答例でテストを実行しているので、すべて合格します）。

```text
対象: 解答例（solutions/） / 1章

✅ 01-computer-systems/01-data-representation           ████████████████████  31/31

完了した章: 1/1　合格したテスト: 31/31
```

次に、あなた自身の演習ファイルでテストを実行してみましょう。まだ何も実装していないので、すべて失敗するのが正常です。

```bash
python3 tools/check.py 1.1
```

## 5. 演習の進め方

1. 章の `README.md` を読む。
2. `exercises/<モジュール名>.py` を開き、各関数の docstring（仕様）を読む。
3. `raise NotImplementedError(...)` を実装に置き換える。
4. テストを実行する。

```bash
python3 tools/check.py 1.1          # 合格数と、失敗したテストの一覧
python3 tools/check.py -v 1.1       # unittest の詳細な出力
python3 tools/check.py 1            # 第 1 部の全演習
python3 tools/check.py              # すべての演習の進捗
python3 tools/check.py --list       # 演習のある章の一覧
python3 tools/check.py 3.4 -k TestStage1   # 名前に TestStage1 を含むテストだけ
```

特定のテストだけを実行したいときは、演習のディレクトリで `unittest` を直接使います。

```bash
cd 01-computer-systems/01-data-representation/exercises
python3 -m unittest -v test_datarep.TestExercise1Base            # クラス単位
python3 -m unittest -v test_datarep.TestExercise1Base.test_examples  # テスト 1 つ
```

### デバッグのコツ

- **関数を単体で呼んでみる**: 演習ディレクトリで `python3` を起動し、`from datarep import to_base` のように import して、テストと同じ入力で呼び出します。
- **`breakpoint()` を使う**: 調べたい行に `breakpoint()` と書いてテストを実行すると、デバッガ（pdb）が起動します。`p 変数名` で値を表示、`n` で次の行、`c` で続行です。
- **トレースバックは下から読む**: 最後の行が例外の種類とメッセージ、その少し上が、あなたのコードで例外が起きた行です。

## 6. エディタの設定（任意）

VS Code を使う場合は、Python 拡張機能を入れると、補完・型ヒントの表示・テストの実行ができます。演習は型ヒント付きで書かれているので、補完が効くと関数の仕様を確認しやすくなります。

## 7. トラブルシューティング

| 症状 | 原因と対処 |
|---|---|
| `python3: command not found` | Python が入っていない。Windows では WSL の中で作業しているか確認する |
| `Python 3.10 以上が必要です` と表示される | Python が古い。新しいバージョンを入れる（uv を使うと簡単） |
| `⚠️ テストの読み込みに失敗` と表示される | 演習ファイルに構文エラーがある。演習ディレクトリで `python3 -c "import <モジュール名>"` を実行すると、エラーの行が分かる |
| テストが終わらない | 無限ループの可能性がある。Ctrl+C で止め、`-v` を付けてどのテストで止まっているか確認する。`check.py` は 1 章あたり 300 秒でタイムアウトする |
| `Address already in use` | ネットワークの演習で、前回のテストのプロセスが残っている。しばらく待つか、残っているプロセスを終了する |
| Windows で文字化けや `UnicodeDecodeError` が出る | WSL を使う。どうしても Windows で直接実行する場合は、環境変数 `PYTHONUTF8=1` を設定する |
| 一部のテストが「スキップ」と表示される | その OS で使えない機能（`os.fork` など）を使うテスト。Linux か macOS、WSL で実行すると確認できる |
