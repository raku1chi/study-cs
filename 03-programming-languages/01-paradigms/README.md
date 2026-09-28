# 3.1 プログラミングパラダイムと抽象化

> 同じ問題でも、手順を並べる、オブジェクトに責務を分ける、関数を組み合わせる、欲しい結果だけを宣言する、と書き方はいくつもあります。パラダイム（paradigm）とは、単なる流儀ではなく「何を書けなくするか」という制約の体系です。この章では主要なパラダイムを「抽象化の道具」として比べ、スコープ・クロージャ・ジェネレータ・エラー処理・メタプログラミングという、どの言語でも避けて通れない仕組みを原理から理解します。

| 項目 | 内容 |
|---|---|
| 学習時間の目安 | 本文 3h ＋ 演習 5h |
| 前提となる章 | [1.4 プログラムが動く仕組み](../../01-computer-systems/04-how-programs-run/README.md)（関数呼び出しとスタックフレーム） |
| 演習 | [exercises/](exercises/)（Python） |
| キーワード | 抽象化, 命令型, オブジェクト指向, ポリモーフィズム, 関数型, 宣言型, クロージャ, ジェネレータ, Result 型, 表現問題 |

## この章のゴール

- [ ] 手続き抽象とデータ抽象の違いを説明し、表現を隠した API を設計できる
- [ ] 命令型・オブジェクト指向・関数型・宣言型の考え方と、それぞれが得意な問題を説明できる
- [ ] 3 種類のポリモーフィズムと動的ディスパッチの仕組みを説明し、継承と合成を使い分けられる
- [ ] レキシカルスコープとクロージャの仕組みを説明し、ループ内クロージャの遅延束縛バグを見抜いて直せる
- [ ] 高階関数・メモ化・ジェネレータによる遅延ストリーム・永続データ構造を実装できる
- [ ] 例外・エラー値・Result 型のトレードオフを説明し、チームのエラー処理方針を設計できる
- [ ] 表現問題を例に、オブジェクト指向と関数型の拡張性のトレードオフを説明できる

## なぜ学ぶのか

パラダイムの話は抽象的に聞こえますが、その理解不足は具体的な障害として現れます。

- **クロージャとループ変数**: 2020 年、無料の TLS 証明書を発行する Let's Encrypt は、Go で書かれた発行システムのバグにより、一部の証明書で CAA レコード（そのドメインに証明書を発行してよい認証局を指定する DNS レコード）の再確認が正しく行われていなかったと公表し、影響を受けた約 300 万枚の証明書を失効させると発表しました。公開された報告によれば、原因はループの中でループ変数を指すポインタを保存していたことで、N 個のドメインを確認するはずが、1 つのドメインを N 回確認していました。この種のバグがあまりに多かったため、Go は 1.22（2024 年）でループ変数の意味そのものを変更しました（本章の「3.4 遅延束縛の罠」で実際に確かめます）。
- **エラー処理**: Yuan らの論文 "Simple Testing Can Prevent Most Critical Failures"（OSDI 2014）は、Cassandra・HBase・HDFS などの分散システムで実際に起きた障害を分析し、致命的な障害の 92% が「ソフトウェアが明示的に通知した、致命的ではないエラーの誤った処理」に起因していたと報告しています。問題のあったエラーハンドラには、中身が空のもの、ログを出すだけのもの、`TODO` と書かれたままのものが目立ちました。
- **制御フロー**: 2014 年に見つかった Apple の TLS 実装の脆弱性（通称 goto fail, CVE-2014-1266）では、C のエラー処理で使われる `goto fail;` の行が誤って 2 回書かれていたため、2 行目が無条件に実行され、ハンドシェイクでサーバーが送る鍵交換パラメータの署名検証が飛ばされていました。エラーを「戻り値＋goto」で手作業で伝える命令型のスタイルは、1 行の書き間違いで安全性の前提を崩します。

どれも文法を知らなかったのではなく、**スコープ・状態・エラーの伝わり方という、パラダイムの根っこにある仕組みを意識していなかった** ことが原因です。また現代の主要言語は、Java がラムダ式やパターンマッチを、Python が `match` 文を取り込んだように、どれもマルチパラダイム化しています。現場で必要なのは特定のパラダイムの信者になることではなく、**問題に応じてスタイルを選び、その選択をチームで揃えられること** です。

## 1. 抽象化とパラダイム

### 1.1 抽象化とは「詳細を隠して、名前で扱う」こと

ソフトウェアの複雑さと戦う最大の武器は **抽象化（abstraction）** です。基本形は 2 つあります。

- **手続き抽象（procedural abstraction）**: 一連の計算に名前を付け、「どうやるか」を隠して「何をするか」だけで呼べるようにする。`sorted(xs)` を呼ぶ人は、中のアルゴリズムを知らなくてよい。
- **データ抽象（data abstraction）**: データの **表現（representation）** を隠し、決められた操作だけで扱えるようにする。Liskov と Zilles が 1974 年に抽象データ型（ADT: abstract data type）として定式化しました。

データ抽象の古典的な例は、SICP（後述）の有理数です。

```python
from math import gcd

def make_rat(n, d):          # 構築子: 表現（ここではタプル）を知っているのはこの 3 関数だけ
    g = gcd(n, d)
    return (n // g, d // g)
def numer(r): return r[0]    # 選択子
def denom(r): return r[1]

def add_rat(a, b):           # 利用側は表現を知らない
    return make_rat(numer(a) * denom(b) + numer(b) * denom(a), denom(a) * denom(b))

r = add_rat(make_rat(1, 2), make_rat(1, 3))
print(numer(r), "/", denom(r))   # 5 / 6
```

`add_rat` はタプルの添字を一切使っていません。この「表現を知る側」と「操作だけを使う側」の境界を **抽象の壁（abstraction barrier）** と呼びます。壁があるので、表現を辞書に変えても、約分のタイミングを変えても、利用側は変わりません。Parnas は 1972 年の論文 "On the Criteria To Be Used in Decomposing Systems into Modules" で、モジュールは処理の手順ではなく「**変わりそうな設計上の決定**」を隠すように分割せよと説きました（情報隠蔽, information hiding）。これは今でもモジュール設計・API 設計の最重要原則です（[9.3 ドメイン駆動設計とモジュール分割](../../09-architecture/03-domain-driven-design/README.md)）。

ただし、抽象は完全ではありません。Joel Spolsky が 2002 年に「自明でない抽象化はすべて、程度の差はあれ漏れる（leaky）」と書いたように、性能・障害・境界条件では下の層の性質が透けて見えます。ORM で N+1 クエリが起きる、TCP の下のパケットロスが遅延として現れる、といった具合です。**抽象を使いこなすとは、普段は下を忘れ、必要なときには下に降りられること** です。

### 1.2 パラダイムは「制約の体系」

パラダイムは、何を計算の基本単位とみなし、何を禁止・制限するかで特徴付けられます。Robert C. Martin は『Clean Architecture』で、構造化プログラミングは制御の直接的な移動（goto）に、オブジェクト指向は間接的な移動（関数ポインタ）に、関数型は代入に、それぞれ規律を課すものだと整理しています。制約があるから、読む人が「ここでは起きないこと」を前提にでき、推論が楽になるのです。

| パラダイム | 計算のモデル | 制限・規律 | 代表的な言語・技術 |
|---|---|---|---|
| 命令型・手続き型 | 状態（変数）を命令で順に書き換える | 構造化（goto を使わず順次・分岐・反復で書く） | C, Pascal, Fortran, シェル |
| オブジェクト指向 | 状態と操作をまとめたオブジェクトがメッセージをやり取りする | 状態への直接アクセスを禁じ、操作経由に限る | Java, C#, Smalltalk, Ruby |
| 関数型 | 値を受け取り値を返す関数の合成 | 代入・副作用を避ける（不変性） | Haskell, OCaml, Clojure, Elixir |
| 宣言型 | 「何が欲しいか」を記述し、手順は処理系が決める | 手順を書かせない | SQL, HTML, 正規表現, Terraform |
| 論理型 | 事実と規則から、条件を満たす答えを探索する | 手順ではなく関係を書く | Prolog, Datalog |

この分類は簡略化したもので（関数型と論理型を宣言型の一種とみなす整理もあります）、実際の言語は複数のパラダイムを混ぜています。Python は手続き型の書き方も、クラスも、高階関数も、ジェネレータによる遅延評価も使えます。以降の節で、各パラダイムの核となる仕組みを見ていきます。

## 2. 命令型とオブジェクト指向

### 2.1 命令型・手続き型

**命令型（imperative）** プログラミングは、CPU の動作（[1.2 論理回路とCPUの仕組み](../../01-computer-systems/02-logic-and-cpu/README.md)）をそのまま抽象化したもので、メモリ上の状態を命令で 1 つずつ書き換えていきます。これを手続き（関数）にまとめたのが **手続き型（procedural）** です。Dijkstra が 1968 年の書簡 "Go To Statement Considered Harmful" で goto の乱用を批判して以来、「順次・分岐・反復」だけで制御を組み立てる **構造化プログラミング** が標準になりました。

命令型は機械の動作に近いので性能を読みやすいのが長所で、弱点は **可変状態（mutable state）** です。状態が共有されると、ある場所の書き換えが離れた場所に影響します。

```python
grid = [[0] * 3] * 3      # 同じリストへの参照を 3 つ並べている（エイリアシング）
grid[0][0] = 1
print(grid)               # [[1, 0, 0], [1, 0, 0], [1, 0, 0]]
```

1 か所を書き換えたつもりが 3 行とも変わりました。`[0] * 3` で作った 1 つのリストを 3 つの行が共有しているからです。状態を「誰が、いつ書き換えうるか」を追えなくなることが、大規模な命令型コードで最も多いバグの源で、並行処理が絡むとデータ競合になります（[4.4 並行処理と同期](../../04-operating-systems/04-concurrency/README.md)）。同じ計算を、状態の書き換えなしでも書けます。

```python
total = 0                                     # 命令型: 状態を順に書き換える
for n in range(1, 11):
    if n % 2 == 0:
        total += n * n
print(total)                                              # 220
print(sum(n * n for n in range(1, 11) if n % 2 == 0))    # 式の組み合わせ（220）
```

後者には書き換えられる変数がなく、「`total` がこの時点でいくつか」を追う必要がありません。

### 2.2 カプセル化

**オブジェクト指向（OOP: object-oriented programming）** は、状態とそれを操作する手続きを **オブジェクト** にまとめ、状態への直接アクセスを禁じます。これが **カプセル化（encapsulation）** です。目的は隠すことそのものではなく、**不変条件（invariant）を守ること** にあります。「口座残高は負にならない」という条件は、残高を変更する経路が `withdraw()` だけならその 1 か所で守れますが、誰でも `balance` に代入できるなら、コード全体を調べないと保証できません。Python には言語レベルのアクセス制御がなく、`_name` は「内部用」という慣習、`__name` はサブクラスとの名前の衝突を避ける名前修飾（name mangling）にすぎません。カプセル化は言語機能よりも **設計と規約** の問題です。

### 2.3 ポリモーフィズムの 3 つの種類

**ポリモーフィズム（polymorphism, 多相性）** とは、1 つのコードが複数の型の値を扱えることです。3 種類を区別すると、言語の機能を見通しよく整理できます。

| 種類 | 仕組み | 例 |
|---|---|---|
| サブタイプ多相（subtype） | 基底型の変数に派生型の値を入れ、実行時に実際の型のメソッドが選ばれる | `Shape` の `area()` を `Rect` と `Circle` が実装する |
| パラメトリック多相（parametric） | 型を引数に取り、どの型でも **同じコード** が動く（ジェネリクス） | `def first(xs: list[T]) -> T`、Java の `List<T>` |
| アドホック多相（ad hoc） | 型ごとに **別の実装** を用意し、型に応じて選ぶ | 演算子オーバーロード（`1 + 2` と `"a" + "b"`）、Haskell の型クラス |

Python の `functools.singledispatch` は、第 1 引数の型で実装を選ぶアドホック多相の道具です。

```python
from functools import singledispatch

@singledispatch
def describe(x): return "その他"

@describe.register
def _(x: int): return f"整数 {x}"

@describe.register
def _(x: list): return f"要素数 {len(x)} のリスト"

print(describe(42), describe([1, 2]), describe("s"), describe(True), sep=" / ")
# 整数 42 / 要素数 2 のリスト / その他 / 整数 True
```

最後の `True` が「整数」として扱われたのは、Python では `bool` が `int` のサブクラスだからです。**型の階層の設計は、ディスパッチの結果として表に出てきます**（[3.2 型システム](../02-type-systems/README.md)）。

### 2.4 動的ディスパッチの仕組み

`Shape` 型のリストに `Rect` と `Circle` が混在していても、`s.area()` は実行時に実際のクラスのメソッドを呼びます。これを **動的ディスパッチ（dynamic dispatch）** と呼びます。C++ や Java の典型的な実装では、クラスごとに **仮想関数表（vtable）** という関数ポインタの表を 1 つ用意し、各オブジェクトはその表へのポインタ（vptr）を持ちます。

```text
Rect のオブジェクト          Rect の vtable（クラスごとに 1 つ）
┌──────────────┐          ┌─────────────────────┐
│ vptr ────────┼─────────▶│ area   → Rect::area │
│ w = 2        │          │ ...                 │
│ h = 3        │          └─────────────────────┘
└──────────────┘
shape->area() は「vptr が指す表の area 欄にある関数を呼ぶ」という間接呼び出しになる
```

間接呼び出しはメモリ参照と分岐予測のコストがかかり、呼び出し先が分からないのでインライン展開も妨げます。そのため JVM や JavaScript エンジンの JIT コンパイラは、実行時に観測した型から呼び出し先を推測して直接呼び出しに置き換える最適化（脱仮想化, devirtualization やインラインキャッシュ）を行います。Python では、`obj.method` はクラスの **MRO（method resolution order）** という探索順で属性を探し、多重継承でも探索順は一意に決まります。

```python
class A:
    def hello(self): return "A"
class B(A):
    def hello(self): return "B"
class C(A):
    def hello(self): return "C"
class D(B, C): pass

print([k.__name__ for k in D.__mro__], D().hello())   # ['D', 'B', 'C', 'A', 'object'] B
```

### 2.5 継承と合成 — 脆い基底クラス問題

継承（inheritance）は「型の階層（is-a）」と「実装の再利用」という 2 つの役割を同時に担います。問題は後者です。**実装を継承すると、サブクラスは基底クラスの内部の呼び出し関係に依存してしまいます**。次の例は、『Effective Java』が「継承よりコンポジションを選ぶ」項目で示した例を Python にしたものです。

```python
class Collection:                    # ライブラリが提供する基底クラス
    def __init__(self): self._items = []
    def add(self, item): self._items.append(item)
    def add_all(self, items):
        for item in items:           # 実装の都合で add() を呼んでいる
            self.add(item)

class CountingCollection(Collection):   # 利用者が継承して「追加された数」を数える
    def __init__(self):
        super().__init__()
        self.added = 0
    def add(self, item):
        self.added += 1
        super().add(item)
    def add_all(self, items):
        items = list(items)
        self.added += len(items)
        super().add_all(items)

c = CountingCollection()
c.add_all(["a", "b", "c"])
print(c.added)                       # 6（3 のはず）
```

基底クラスの `add_all` が内部で `self.add` を呼ぶため、動的ディスパッチでサブクラスの `add` が呼ばれ、二重に数えられました。しかも基底クラスの次のバージョンで `add_all` が `add` を呼ばなくなれば、今度は正しく動きます。**基底クラスの内部実装の変更が、何も変えていないサブクラスの振る舞いを変える**。これを **脆い基底クラス問題（fragile base class problem）** と呼びます。実際の Python にも同じ構造があり、`dict` を継承して `__setitem__` を上書きしても、C で実装された `update()` やコンストラクタはそれを呼びません。

```python
class UpperDict(dict):
    def __setitem__(self, key, value):
        super().__setitem__(key.upper(), value)

d = UpperDict()
d["a"] = 1
d.update({"b": 2})
print(d, UpperDict({"c": 3}))   # {'A': 1, 'b': 2} {'c': 3}  ← update とコンストラクタは素通り
```

`collections.UserDict` は `collections.abc.MutableMapping` の上に Python で実装されており、`update` もコンストラクタも `__setitem__` を通るので、この用途では `dict` より継承に向いています。つまり「継承してよいクラス」とは、どのメソッドがどのメソッドを呼ぶかまで設計され、それが利用者に分かるクラスです。一般的な解決策は **合成（composition）と委譲（delegation）** です。

```python
class CountingCollection:            # 継承せず、内部に持って仕事を任せる
    def __init__(self, inner):
        self._inner, self.added = inner, 0
    def add(self, item):
        self.added += 1
        self._inner.add(item)
    def add_all(self, items):
        items = list(items)
        self.added += len(items)
        self._inner.add_all(items)   # inner の中で add() が呼ばれても、こちらの add ではない
# CountingCollection(Collection()) に add_all(["a", "b", "c"]) すると added は 3
```

1994 年の『デザインパターン』（いわゆる GoF 本）は「クラス継承よりオブジェクトの合成を優先せよ」と述べ、『Effective Java』は「継承のために設計し文書化せよ、さもなくば継承を禁止せよ」と述べています。継承を使ってよいのは、本当に is-a の関係で **リスコフの置換原則（LSP）**（基底型が使える場所ならどこでも派生型に置き換えて正しく動く）を満たし、かつ基底クラスが継承を前提に設計されている（抽象基底クラス、フレームワークの拡張点など）ときです。Go や Rust が実装の継承を持たず、インタフェース（トレイト）と合成だけで設計する言語になっているのは、この教訓の反映です（[8.1 良いコードと設計原則](../../08-software-engineering/01-code-quality-and-design/README.md)）。

## 3. スコープとクロージャ

### 3.1 レキシカルスコープ

**スコープ（scope）** は、名前がどの範囲で有効かを決める規則です。現代のほぼすべての言語は **レキシカルスコープ（lexical scope, 静的スコープ）** を採用しており、関数の中の名前は **関数が定義された場所** の外側を順に探して解決されます。**呼び出した側** の変数を探すのが **動的スコープ（dynamic scope）** で、古い Lisp や Emacs Lisp の既定の動作（Emacs 24 以降はレキシカルスコープも選べる）などに見られます。動的スコープでは関数の意味が呼び出し元によって変わるため、読んで理解するのが難しくなります。

```python
x = "global"
def outer():
    x = "enclosing"
    def inner():
        return x          # 定義された場所から見える x
    return inner

print(outer()())          # enclosing（outer はもう終わっているのに x が見える）
```

### 3.2 Python の LEGB 規則

Python は名前を **L**ocal（関数内）→ **E**nclosing（外側の関数）→ **G**lobal（モジュール）→ **B**uilt-in（組み込み）の順に探します。重要なのは、**関数内のどこかでその名前に代入していれば、その名前は関数全体でローカル変数になる** という規則です。これは関数定義の時点で決まります。

```python
counter = 0
def broken():
    counter += 1          # 代入があるので、counter はこの関数のローカル変数
broken()
# UnboundLocalError: cannot access local variable 'counter' where it is not associated with a value
# （Python 3.11 のメッセージ。3.10 では "local variable 'counter' referenced before assignment"）
```

外側の変数に代入したいときは `nonlocal`（外側の関数の変数）や `global`（モジュールの変数）で宣言します。

### 3.3 クロージャ

関数が、定義された環境の変数を捕まえたまま持ち運ばれるとき、その関数と環境の組を **クロージャ（closure）** と呼びます。

```python
def make_counter():
    count = 0
    def increment():
        nonlocal count
        count += 1
        return count
    return increment

c1, c2 = make_counter(), make_counter()
print(c1(), c1(), c2())                   # 1 2 1（c1 と c2 は別々の count を持つ）
print(c1.__closure__[0].cell_contents)    # 2
```

`make_counter` が終わっても `count` は消えません。スタックフレームは関数の終了とともに捨てられるので（[1.4](../../01-computer-systems/04-how-programs-run/README.md)）、CPython はクロージャに捕まえられた変数を **セル（cell）** というヒープ上の箱に置き、関数オブジェクトにそのセルへの参照を持たせます。クロージャは「状態を持つ関数」であり、フィールドとメソッドを 1 つずつ持つオブジェクトと同じ表現力を持っています。演習 1 の `curry` や `memoize` は、クロージャで状態を閉じ込める練習です。

### 3.4 遅延束縛の罠

クロージャが捕まえるのは **変数そのもの** であって、その時点の **値** ではありません。この性質を **遅延束縛（late binding）** と呼び、ループと組み合わさると典型的なバグになります。

```python
callbacks = []
for i in range(3):
    callbacks.append(lambda: i)
print([f() for f in callbacks])      # [2, 2, 2]（[0, 1, 2] ではない）
```

```text
callbacks[0] ─┐
callbacks[1] ─┼──▶ 変数 i（ループ全体で 1 つ）── ループ終了時の値 2
callbacks[2] ─┘
```

3 つのラムダは同じ 1 つの変数 `i` を捕まえ、呼び出した時点で読むので、全員がループ終了時の値を返します。Python の公式 FAQ にも「ループ内で定義したラムダがすべて同じ結果を返すのはなぜか」という項目があるほど有名な罠です。直し方は「今の値」を新しい束縛に閉じ込めることです。

```python
callbacks = [lambda i=i: i for i in range(3)]            # デフォルト引数は定義時に評価される
from functools import partial
callbacks2 = [partial(lambda n: n, i) for i in range(3)]  # partial で値を固定する
print([f() for f in callbacks], [f() for f in callbacks2])   # [0, 1, 2] [0, 1, 2]
```

ループ変数が「ループ全体で 1 つ」か「反復ごとに新しい」かは言語によって違います。JavaScript では `var` と `let` で振る舞いが違います（Node.js 22 で実行）。

```javascript
const a = [], b = [];
for (var i = 0; i < 3; i++) a.push(() => i);   // var は関数全体で 1 つ
for (let j = 0; j < 3; j++) b.push(() => j);   // let は反復ごとに新しい束縛
console.log(a.map(f => f()), b.map(f => f())); // [ 3, 3, 3 ] [ 0, 1, 2 ]
```

Go は 1.22 で意味を変えました。同じコードでも、`go.mod` の `go` ディレクティブ（そのモジュールが前提とする言語バージョン）によって結果が変わります（Go 1.24 で実行）。

```go
var ptrs []*int
for i := 0; i < 3; i++ {
	ptrs = append(ptrs, &i) // ループ変数のアドレスを保存する
}
for _, p := range ptrs {
	fmt.Print(*p, " ")
}
// go.mod が "go 1.21" のとき: 3 3 3
// go.mod が "go 1.22" のとき: 0 1 2
```

冒頭の Let's Encrypt の事例は、1.21 以前の意味論で起きたこの種のバグでした。**言語のバージョンを上げると、同じソースコードの意味が変わることがある** という点も、アップグレード計画で覚えておくべき教訓です。

## 4. 関数型プログラミング

### 4.1 純粋関数と参照透過性

**純粋関数（pure function）** とは、(1) 同じ引数なら必ず同じ結果を返し（現在時刻・乱数・グローバル変数・外部の状態に依存しない）、(2) 副作用（side effect）がない（引数や外部の状態を書き換えない、I/O をしない）関数です。純粋な式は、その値で置き換えてもプログラムの意味が変わりません。これを **参照透過性（referential transparency）** と呼び、次のことが可能になります。

- **テストが簡単**: 入力と期待される出力を並べるだけでよく、モックや準備が要らない。
- **キャッシュできる**: 同じ引数の結果を再利用できる（**メモ化**, memoization。演習 1 の `memoize`）。
- **並列化できる**: 共有状態がないので、順序を気にせず同時に実行できる。

逆に言えば、メモ化してよいのは純粋関数だけです。現在時刻に依存する関数や DB を読む関数をメモ化すると、古い結果を返し続けるバグになります。

### 4.2 不変性と永続データ構造

関数型プログラミングでは、データを書き換えず、変更したいときは **新しい値を作ります**（**不変性**, immutability）。毎回コピーすると遅いように思えますが、不変なら **共有しても安全** なので、変わらない部分はコピーせずに共有できます。これを **構造共有（structural sharing）** と呼び、変更前のバージョンも使い続けられるデータ構造を **永続データ構造（persistent data structure）** と呼びます。

```text
a = PList.of(2, 3)      a ──▶ [2] ──▶ [3] ──▶ (空)
b = a.push(1)           b ──▶ [1] ──┘            （a のノードをそのまま共有。O(1)）
c = b.set(0, 9)         c ──▶ [9] ──┘            （先頭だけ作り直し、残りは共有）
```

連結リストで O(1) なのは先頭への追加だけですが、Clojure や Scala の永続ベクタ・永続マップは、分岐数の大きい木（32 分木など）で **経路コピー（path copying）** を行い、更新を O(log₃₂ n)（実用上ほぼ定数）で実現しています。React で状態を書き換えずに新しいオブジェクトを作るのも同じ発想で、変更の検出が参照の比較だけで済みます。Python では、タプル・`frozenset`・`frozen=True` のデータクラスが不変です。ただし不変なのは「浅く」だけで、タプルの中のリストは書き換えられます。演習 3 では、構造共有する永続リストを実装します。

### 4.3 第一級関数と高階関数

関数を数値や文字列と同じように変数に入れ、引数に渡し、戻り値として返せることを **第一級関数（first-class function）**、関数を受け取ったり返したりする関数を **高階関数（higher-order function）** と呼びます。代表が `map`（各要素を変換）、`filter`（条件で選ぶ）、`reduce`（畳み込む）です。

```python
from functools import reduce
evens = filter(lambda n: n % 2 == 0, range(1, 11))
squares = map(lambda n: n * n, evens)
print(reduce(lambda acc, n: acc + n, squares, 0))   # 220
```

Python では内包表記や `sum` の方が読みやすいことが多く、記法そのものより **「繰り返しの骨組み」と「各要素への処理」を分離できる** という考え方が大事です。関数を組み合わせる道具として、関数合成（`compose`, `pipe`）や、引数を 1 つずつ受け取る関数に変換する **カリー化（currying）** があります（演習 1）。

### 4.4 再帰と末尾呼び出し

関数型言語はループの代わりに **再帰（recursion）** を多用します。再帰呼び出しのたびにスタックフレームが積まれるので、深い再帰はスタックを使い果たします。Scheme などの言語は、関数の最後で行う呼び出し（**末尾呼び出し**, tail call）ではフレームを再利用することを仕様で保証しており、末尾再帰をループと同じメモリで実行できます。Python は末尾呼び出しの最適化を行いません（Guido van Rossum は 2009 年のブログで、スタックトレースが失われることなどを理由に採用しないと説明しています）。

```python
import sys
print(sys.getrecursionlimit())         # 1000（既定の上限）
def depth(n):
    return 0 if n == 0 else 1 + depth(n - 1)
depth(10_000)                          # RecursionError: maximum recursion depth exceeded
```

Python では、深さが入力に比例する処理（長い連結リストの走査、深い木の探索）はループや明示的なスタックで書くのが原則です。演習 3 のテストでは 5 万要素のリストを使うので、再帰で書くと失敗します。

### 4.5 遅延評価とジェネレータ

式の値を必要になるまで計算しないことを **遅延評価（lazy evaluation）** と呼びます。Haskell は言語全体が遅延評価で、無限リストを自然に扱えます。Python では **イテレータ** と **ジェネレータ** が遅延評価の道具です。イテレータプロトコルは「次の要素をください（`__next__`）」「もうありません（`StopIteration` 例外）」という約束だけでできており、`for` 文はこの約束に従うあらゆるオブジェクトを回せます。

これを簡単に書けるのが **ジェネレータ関数**（本体に `yield` を含む関数）です。呼び出しても本体は実行されずジェネレータオブジェクトが返り、`next()` のたびに次の `yield` まで実行して **一時停止** します。局所変数と実行位置はジェネレータオブジェクトの中（ヒープ）に保存されるので、関数から戻った後も再開できます。

```python
def read_lines():
    for line in ["a,1", "b,2", "c,3"]:
        print(f"  読む: {line}")
        yield line

def parse(lines):
    for line in lines:
        name, value = line.split(",")
        print(f"  変換: {name}")
        yield name, int(value)

pipeline = parse(read_lines())       # まだ何も実行されない
print("パイプラインを作った")
print(next(pipeline))
print(next(pipeline))
```

```text
パイプラインを作った
  読む: a,1
  変換: a
('a', 1)
  読む: b,2
  変換: b
('b', 2)
```

「全行を読む → 全行を変換する」ではなく、**1 要素ずつ段をまたいで流れていく** のが分かります。巨大なログファイルを一定のメモリで処理できるのはこのためです。一方で、次の 2 つの性質に注意が必要です。

- **イテレータは使い捨て**: 一度最後まで回したジェネレータは、2 回目は空です。

  ```python
  def stats(values):
      n = sum(1 for _ in values)     # ここで values を使い切る
      return n, sum(values)          # ジェネレータなら 2 回目は空

  print(stats([1, 2, 3]))            # (3, 6)
  print(stats(x for x in [1, 2, 3])) # (3, 0)  ← エラーにならず静かに間違う
  ```

- **ジェネレータ関数の本体は、最初の `next()` まで実行されない**: 引数の検査を本体に書くと、エラーが呼び出し箇所ではなく使用箇所で遅れて発生します。演習 2 では、これを避ける書き方を練習します。

標準ライブラリの `itertools` には `islice`・`takewhile`・`pairwise`（3.10 以降）などの部品がそろっています。演習 2 では、これらに相当するものを自分で実装します。なお、「一時停止して再開できる関数」という仕組みは、`async`/`await` による非同期処理の土台にもなっています（[4.4 並行処理と同期](../../04-operating-systems/04-concurrency/README.md)）。

### 4.6 関数型の核、命令型の殻

実務のシステムは I/O（DB、HTTP、時刻、乱数）なしには動かないので、すべてを純粋にはできません。そこで、**判断のロジックを純粋関数の「核」に集め、I/O を薄い「殻」に押し出す** 設計がよく使われます。Gary Bernhardt が 2012 年ごろに "Functional Core, Imperative Shell" として広めた考え方です。

```python
from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class Subscription:
    user_id: str
    expires_on: date
    reminded: bool

# 核: 純粋関数。I/O も現在時刻の取得もしない
def reminders_due(subs: list[Subscription], today: date, days_before: int = 3) -> list[str]:
    return [s.user_id for s in subs
            if not s.reminded and 0 <= (s.expires_on - today).days <= days_before]

# 殻: I/O をここに集め、判断は核に任せる
def run_daily_job(repo, mailer, today: date) -> None:
    for user_id in reminders_due(repo.load_active(), today):
        mailer.send(user_id, "まもなく契約の期限です")
        repo.mark_reminded(user_id)

subs = [Subscription("u1", date(2026, 10, 1), False),   # 核のテストにモックは要らない
        Subscription("u2", date(2026, 10, 1), True),
        Subscription("u3", date(2026, 12, 1), False)]
print(reminders_due(subs, today=date(2026, 9, 28)))     # ['u1']
```

`today` を引数で受け取るのがポイントです。関数の中で `date.today()` を呼ぶと時刻に依存する不純な関数になり、テストで日付を固定できません。**依存を引数で受け取る** だけで、ビジネスルールの大部分を速く決定的なテストで検証できます（[8.2 テスト戦略](../../08-software-engineering/02-testing/README.md)）。

## 5. 宣言型と論理型

### 5.1 「何が欲しいか」を書く

**宣言型（declarative）** プログラミングでは、欲しい結果の性質だけを書き、手順は処理系に任せます。代表例が SQL です。次のクエリは「tom の子孫をすべて」求めますが、どの順に表を走査し、どの索引を使うかは書いていません。

```python
import sqlite3
db = sqlite3.connect(":memory:")
db.executescript("""
CREATE TABLE parent (parent TEXT, child TEXT);
INSERT INTO parent VALUES ('tom', 'bob'), ('bob', 'ann'), ('ann', 'kai'), ('tom', 'liz');
""")
rows = db.execute("""
WITH RECURSIVE ancestor(a, d) AS (
    SELECT parent, child FROM parent                  -- 親は祖先である
    UNION
    SELECT p.parent, an.d                             -- 親の祖先も祖先である
    FROM parent AS p JOIN ancestor AS an ON p.child = an.a
)
SELECT d FROM ancestor WHERE a = 'tom' ORDER BY d
""").fetchall()
print([r[0] for r in rows])     # ['ann', 'bob', 'kai', 'liz']
```

宣言型の考え方は、SQL（[6.1 リレーショナルモデルとSQL](../../06-databases/01-relational-model-and-sql/README.md)）のほか、HTML と CSS、正規表現、ビルドツール、そしてインフラの構成管理に広がっています。Terraform や Kubernetes では、「サーバーを 3 台作る手順」ではなく「3 台ある状態」を記述し（Kubernetes なら `replicas: 3`）、処理系の中で動き続ける **調整ループ（reconciliation loop）** がそれを実現します（[10.1 クラウドコンピューティングとIaC](../../10-cloud-and-sre/01-cloud-and-iac/README.md)、[10.2 コンテナオーケストレーションとKubernetes](../../10-cloud-and-sre/02-containers-and-kubernetes/README.md)）。

```text
（擬似コード）
loop forever:
    desired = 宣言された状態を読む        # 例: replicas = 3
    actual  = 実際の状態を観測する        # 例: 動いている Pod は 2 個
    差分を埋める操作を 1 つ実行する       # 例: Pod を 1 個作る
```

手順ではなく状態を宣言するので、同じ宣言を何度適用しても結果が同じになり（冪等性）、障害で 1 台消えても自動的に元に戻ります。**宣言型の弱点は、処理系の戦略が期待と違ったとき** に現れます。SQL が遅いとき、実行計画（選ばれた手順）を読めなければ手が出せません（[6.2 インデックスとクエリ処理](../../06-databases/02-indexes-and-query-processing/README.md)）。宣言型を使いこなすにも、結局その下の「どうやるか」の理解が必要です。

### 5.2 論理型プログラミング

**論理型（logic）** プログラミングは、事実と規則を書き、問い合わせに対して条件を満たす答えを処理系が探索します。代表的な言語 Prolog では、上の SQL と同じ内容を次のように書きます（記法を示すための例です）。

```text
parent(tom, bob).   parent(bob, ann).   parent(ann, kai).   parent(tom, liz).
ancestor(X, Y) :- parent(X, Y).                   % X が Y の親なら、X は Y の祖先
ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).   % X が Z の親で Z が Y の祖先なら …
?- ancestor(tom, Who).                            % Who = bob ; Who = liz ; Who = ann ; …
```

処理系は **単一化（unification）**（2 つの項を等しくする変数の割り当てを見つける操作）と **バックトラック** で答えを探します。論理型言語そのものを業務で書く機会は多くありませんが、考え方は広く使われています。型推論は型の等式を単一化で解きます（[3.2 型システム](../02-type-systems/README.md) の演習で実装します）。Prolog の部分集合で停止性を保証しやすい Datalog は、コード解析の CodeQL が使う QL 言語や、ポリシーエンジン Open Policy Agent の Rego に影響を与えています。

## 6. エラー処理のモデル

失敗しうる操作の結果をどうやって呼び出し元に伝えるか。これは言語の設計思想が最も強く表れる部分で、主なモデルは 3 つあります。

### 6.1 例外

**例外（exception）** は、エラーを通常の戻り値とは別の経路で、呼び出し階層を自動的にさかのぼって伝えます（Python・Java・C#・JavaScript など）。正常系がすっきり書け、途中の関数はエラーについて何も書かなくてよいのが長所です。短所はその裏返しで、**どの関数がどんな例外を送出するかがシグネチャに現れない** ため、呼び出し側が処理を忘れても分かりません。Java の **検査例外（checked exception）** は、送出しうる例外をシグネチャに宣言させて処理をコンパイラに強制する試みでしたが、冗長さやバージョン管理のしにくさが批判され、後発の C# や Kotlin は採用していません。Java 8 で導入されたラムダ式・Stream API とも相性がよくありません。

### 6.2 エラー値

Go は、エラーを **普通の戻り値** として返します。

```go
func parseAge(s string) (int, error) {
	n, err := strconv.Atoi(s)
	if err != nil {
		return 0, fmt.Errorf("年齢の解析に失敗: %w", err) // 文脈を足して包む
	}
	if n < 0 || n > 150 {
		return 0, fmt.Errorf("年齢が範囲外: %d", n)
	}
	return n, nil
}
// "42", "abc", "200" を渡したときの出力（呼び出し側は省略）:
// 年齢: 42
// エラー: 年齢の解析に失敗: strconv.Atoi: parsing "abc": invalid syntax
// エラー: 年齢が範囲外: 200
```

失敗しうる箇所がすべてコード上に見えるのが長所で、Rob Pike は 2015 年の Go ブログ記事 "Errors are values" で、エラーを値としてプログラムで扱う利点を説明しています。短所は `if err != nil` の繰り返しによる冗長さと、`_` でエラーを捨てるなどのチェック漏れを型で防げないことです。`%w` で元のエラーを包んでおけば、呼び出し側は `errors.Is` / `errors.As` で原因を判定できます。C の戻り値によるエラー処理は同じモデルの原始的な形で、冒頭の goto fail はその弱点が表面化した例です。

### 6.3 Result 型

Rust は成功と失敗を **型** で表します。`Result<T, E>` は `Ok(T)` か `Err(E)` のどちらかで、値を取り出すには両方の場合を扱う必要があります。

```rust
enum AgeError { NotANumber(ParseIntError), OutOfRange(i32) }

fn parse_age(s: &str) -> Result<i32, AgeError> {
    let n: i32 = s.parse().map_err(AgeError::NotANumber)?; // 失敗ならここで Err を返す
    if !(0..=150).contains(&n) {
        return Err(AgeError::OutOfRange(n));
    }
    Ok(n)
}

fn main() {
    for s in ["42", "abc", "200"] {
        match parse_age(s) {  // Ok と Err の全種類を書かないとコンパイルエラーになる
            Ok(age) => println!("年齢: {}", age),
            Err(AgeError::NotANumber(e)) => println!("エラー: 数値ではありません（{}）", e),
            Err(AgeError::OutOfRange(n)) => println!("エラー: 範囲外です（{}）", n),
        }
    }
}
// 年齢: 42
// エラー: 数値ではありません（invalid digit found in string）
// エラー: 範囲外です（200）
```

`?` 演算子は「`Err` ならその場で呼び出し元に返し、`Ok` なら中身を取り出す」という伝播を 1 文字で書く仕組みで、エラー値の明示性と例外の簡潔さを両立させます。Haskell の `Either`、Swift の `Result` も同じ考え方です。演習 4 では、Python で `Ok` / `Err` を実装し、例外を使わない入力検証パイプラインを作ります。

### 6.4 比較と使い分け

| モデル | 失敗の伝わり方 | 長所 | 短所 |
|---|---|---|---|
| 例外 | 呼び出し階層を自動でさかのぼる | 正常系が読みやすい。途中の層は何も書かなくてよい | シグネチャに現れない。握りつぶしやすい。どこで飛ぶか追いにくい |
| エラー値 | 戻り値の 1 つとして返す | 失敗しうる箇所が見える。制御フローが素直 | 冗長。チェック漏れを型で防げない |
| Result 型 | 型として返し、`?` などで伝播 | チェック漏れを型検査で防げる。`map` / `and_then` で合成できる | 型が複雑になる。パターンマッチや `?` の支援がないと書きにくい |

どのモデルでも共通して重要なのは、次の区別です。Microsoft の研究的な OS プロジェクト "Midori" の開発に携わった Joe Duffy は、ブログ記事 "The Error Model"（2016）で、この区別をエラー処理設計の出発点に置いています。

- **想定内の失敗（recoverable error）**: 入力の誤り、ファイルがない、ネットワークの一時的な断絶など。呼び出し側が処理すべきもので、Result やエラー値、特定の例外で表す。
- **バグ（プログラムの誤り）**: 不変条件の違反、ありえない場所の `None` など。その場で回復しようとせず、処理を中断（panic、assert、プロセスの再起動）して早く気付くべきもの。

冒頭の Yuan らの分析が示すとおり、**エラー処理コードは最もテストされず、最も障害を生むコード** です。`except Exception: pass` のような握りつぶしは、問題を隠して後で大きくする典型です。

## 7. メタプログラミング

**メタプログラミング（metaprogramming）** とは、プログラムを操作するプログラムを書くことです。定型的なコードを減らせる一方、「コードに書かれていない振る舞い」を生むので、使いどころの判断が重要です。

### 7.1 デコレータ

Python の **デコレータ（decorator）** は、関数を受け取って関数を返す高階関数を `@` の構文で適用する仕組みです。

```python
import functools

def retry(times):
    """ConnectionError が出たら times 回まで再試行するデコレータを作る。"""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, times + 1):
                try:
                    return fn(*args, **kwargs)
                except ConnectionError as e:
                    print(f"  {attempt} 回目の失敗: {e}")
            raise ConnectionError(f"{times} 回試して失敗しました")
        return wrapper
    return decorator

@retry(times=3)                 # fetch = retry(times=3)(fetch) と同じ意味
def fetch(url): ...
```

`@functools.wraps(fn)` を忘れると、`fetch.__name__` が `"wrapper"` になり、元の関数の名前や docstring が失われて、ログやデバッグで元の関数が分からなくなります。デコレータは、ロギング・計測・認可・キャッシュ・再試行のように、**本来の処理と直交する関心事（横断的関心事, cross-cutting concern）** の分離に向いています。ただし、再試行を副作用のある処理（決済など）に付けると二重実行の原因になります。再試行が安全なのは冪等な操作だけです（[9.4 API設計](../../09-architecture/04-api-design/README.md)）。Python には他にも、属性アクセスを差し替えるデスクリプタ（`property` の正体）、クラスの生成を制御するメタクラスなどがあり、`@dataclass` もクラス定義から `__init__`・`__eq__`・`__repr__` を **コード生成** するデコレータです。

### 7.2 マクロ

**マクロ（macro）** は、コンパイル前にプログラムの字面や構文木を変換する仕組みです。C のプリプロセッサマクロは **テキストの置換** なので、構文を無視した事故が起きます。

```c
#define SQUARE(x) x * x            /* 素朴なマクロ: 引数のテキストがそのまま貼り込まれる */
#define SQUARE_OK(x) ((x) * (x))   /* 括弧で守った版 */

printf("%d\n", SQUARE(1 + 2));     /* 5（1 + 2 * 1 + 2 に展開される） */
printf("%d\n", SQUARE_OK(1 + 2));  /* 9 */
```

`gcc -E` で展開結果を見ると、`SQUARE(1 + 2)` は `1 + 2 * 1 + 2` になっています。括弧で守っても、`SQUARE_OK(i++)` は `i++` を 2 回評価してしまいます（C では未定義動作）。これに対し、Lisp 系の言語や Rust の `macro_rules!` は **構文木を単位に** 変換し、マクロ内の変数名が呼び出し側と衝突しないようにする **衛生的マクロ（hygienic macro）** の性質（Rust では部分的）を持ちます。構文木の変換は [3.4 言語処理系を作る](../04-build-an-interpreter/README.md) で実際に書きます。

### 7.3 メタプログラミングのコスト

メタプログラミングは少ないコードで多くの振る舞いを生みますが、それは **grep しても振る舞いの出どころが見つからない** ことでもあります。Google の Python スタイルガイドは、メタクラスや動的な属性アクセスなどを "Power Features" と呼び、使用を避けるよう求めています。フレームワーク（Django の ORM、pytest のフィクスチャなど）のように、多くの利用者のために少数の専門家が保守する場所では威力を発揮しますが、業務コードの中で乱用すると、新しいメンバーが読めないコードになります。

## 8. 表現問題とマルチパラダイムの現実

### 8.1 表現問題

数式の構文木（AST）で、オブジェクト指向と関数型の設計を比べます。オブジェクト指向版では、操作を各クラスのメソッドとして書きます。

```python
class Num:
    def __init__(self, value): self.value = value
    def evaluate(self, env): return self.value
    def to_str(self): return repr(self.value)

class Var:
    def __init__(self, name): self.name = name
    def evaluate(self, env): return env[self.name]
    def to_str(self): return self.name

class Add:
    def __init__(self, left, right): self.left, self.right = left, right
    def evaluate(self, env): return self.left.evaluate(env) + self.right.evaluate(env)
    def to_str(self): return f"({self.left.to_str()} + {self.right.to_str()})"

e = Add(Num(1), Add(Var("x"), Num(2)))
print(e.evaluate({"x": 10}), e.to_str())   # 13 (1 + (x + 2))
```

関数型版では、データ（型）と操作（関数）を分け、関数の中で場合分けします（Python 3.10 の `match` 文）。

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Num: value: int

@dataclass(frozen=True)
class Var: name: str

@dataclass(frozen=True)
class Add: left: "Expr"; right: "Expr"

Expr = Num | Var | Add

def evaluate(e: Expr, env: dict) -> int:
    match e:
        case Num(value): return value
        case Var(name): return env[name]
        case Add(left, right): return evaluate(left, env) + evaluate(right, env)
    raise TypeError(e)
# to_str も同じ形の関数として書く（省略）
```

この 2 つに「新しい種類のノード（例: 掛け算 `Mul`）」と「新しい操作（例: 微分 `derive`）」を追加する場合を考えます。

| 追加するもの | オブジェクト指向版 | 関数型版 |
|---|---|---|
| 新しいノードの種類（型） | クラスを 1 つ追加するだけ。既存コードは変更不要 | **すべての操作関数** に分岐を追加する |
| 新しい操作 | **すべてのクラス** にメソッドを追加する | 関数を 1 つ追加するだけ。既存コードは変更不要 |

型と操作の 2 つの軸のうち、一方は簡単に拡張でき、もう一方は既存コードの修正が必要になります。Philip Wadler は 1998 年に、この「既存コードを再コンパイルせず、型安全性を保ったまま、型と操作の両方を追加できるか」という問題を **表現問題（Expression Problem）** と名付けました。

どちらを選ぶかは、**どちらの軸がより頻繁に拡張されるか** で決まります。GUI の部品のように種類が増え続けるものはオブジェクト指向が、コンパイラの構文木のように種類がほぼ固定で操作（型検査、最適化、コード生成、整形）が増え続けるものは関数型の形が向いています。オブジェクト指向で操作の追加を楽にする定番の手法が **Visitor パターン** で、これは実質的に「関数型版の場合分けをオブジェクト指向の言葉で書いたもの」です。両方の軸を拡張可能にする仕組みとして、Haskell の型クラス、Clojure のプロトコルやマルチメソッド、Julia の多重ディスパッチなどがあり、Python の `singledispatch` も型ごとの実装を後から `register` できる「開いた関数」です。

関数型版の弱点（分岐の追加漏れ）は、**網羅性検査（exhaustiveness check）** で補えます。Rust や OCaml は `match` が全ケースを扱っていないとコンパイル時にエラーや警告を出し、Python でも型検査器（mypy など）と `typing.assert_never`（3.11 以降）で同様の検査ができます（[3.2 型システム](../02-type-systems/README.md)）。新しいノードを追加したとき、**直すべき場所をツールが列挙してくれる** のです。演習 5 では、関数型版で評価器と整形器を書き、次に新しい操作（微分）と新しい型（べき乗）を追加して、このトレードオフを体験します。

### 8.2 マルチパラダイムの現実とチームでのスタイル選択

主要言語は互いの長所を取り込み、マルチパラダイム化しています。Java はラムダ式と Stream API（Java 8）、レコード（16）、sealed クラス（17）、switch のパターンマッチ（21）を、C# は LINQ・レコード・パターンマッチを、Python は内包表記・ジェネレータ・`match` 文（3.10）を取り込みました。つまり「どのパラダイムの言語を選ぶか」よりも、**同じ言語の中で、どの部分をどのスタイルで書くかをチームで揃えること** の方が、日々の生産性と品質に効きます。Python のチームなら、例えば次のような指針が考えられます。

- ドメインのロジック（計算・判定・変換）は、不変なデータクラスと純粋関数で書く（関数型の核）。
- I/O・リソース管理（DB 接続、ファイル、外部 API）は、クラスとコンテキストマネージャで境界に閉じ込める（命令型の殻）。
- 継承はフレームワークの拡張点（抽象基底クラス）に限り、実装の再利用には合成を使う。
- 想定内の失敗は戻り値（Result 相当）か明示的な例外クラスで表し、握りつぶしを静的解析で禁止する。
- メタクラスや動的な属性生成は、共通基盤のコードに限る。

指針は、コードレビューの基準とリンタの設定に落とし込んで初めて機能します（[8.3 バージョン管理とコードレビュー](../../08-software-engineering/03-version-control-and-review/README.md)）。

## よくある落とし穴

1. **コードを再利用するために継承する**。基底クラスの内部実装に依存し、基底クラスの変更で壊れる（脆い基底クラス問題）。is-a の関係でなければ合成と委譲を使い、継承させるクラスはどのメソッドがどのメソッドを呼ぶかまで文書化する。
2. **ループの中でクロージャを作り、ループ変数を後から参照する**。全員が最後の値を見る。デフォルト引数・`partial`・関数呼び出しで「今の値」を束縛する。Go は 1.22 で意味が変わったので、`go.mod` の言語バージョンも確認する。
3. **ジェネレータを 2 回回す**。2 回目は黙って空になり、エラーにならずに結果が間違う。複数回使うならリストにする。関数の引数型を `Iterable` にするか `Sequence` にするかは、この違いを表す設計判断である。
4. **可変オブジェクトをデフォルト引数にする**。`def add_tag(tag, tags=[])` のリストは関数定義時に 1 回だけ作られ、呼び出しをまたいで共有される（`add_tag("a")` の後の `add_tag("b")` は `['a', 'b']` を返す）。`None` をデフォルトにして関数内で作る。
5. **例外を握りつぶす**。`except Exception: pass` やログだけのハンドラは、障害を隠して後で大きくする。想定内の失敗だけを具体的な型で捕まえ、それ以外は上に伝えて落とす。
6. **純粋でない関数や、引数の種類が無限にある関数をメモ化する**。古い結果を返し続けたり、キャッシュが際限なく膨らんでメモリリークになったりする（[3.3 メモリ管理とランタイム](../03-memory-management/README.md)）。`functools.lru_cache` をインスタンスメソッドに付けると、キャッシュが `self` を参照し続けてオブジェクトが解放されない点にも注意する。
7. **Python で深い再帰を書く**。末尾呼び出しの最適化はなく、既定の上限は 1000 段。入力に比例して深くなる処理はループか明示的なスタックで書く。
8. **メタプログラミングで「賢い」コードを書く**。動的に生成された属性やメソッドは、エディタの補完も grep も効かない。同じことが素直なコードで書けるなら、素直な方を選ぶ。

## CTOの視点

1. **エラー処理の方針をアーキテクチャ上の決定として明文化する**。Yuan らの分析が示すように、致命的な障害の多くはエラー処理の誤りから生まれます。「どの失敗を想定内として扱い（戻り値・特定の例外）、どれをバグとしてプロセスごと落とすか」「どの層でエラーに文脈を付けて包むか」「外部 API の失敗を再試行してよい条件（冪等性）」を ADR（アーキテクチャ決定記録）にし、空のハンドラや広すぎる `except` をリンタで禁止しましょう。ポストモーテムでは「このエラーは誰が、どこで処理するはずだったか」を必ず問います。
2. **継承を公開 API にしない**。社内ライブラリや SDK で「このクラスを継承して使ってください」と公開すると、内部実装の変更がすべて破壊的変更になりえます。拡張点はインタフェース（抽象基底クラス、Protocol）とコールバックで提供し、それ以外は継承を想定しないという方針を、共通基盤チームの設計レビュー基準にします。
3. **「関数型の核・命令型の殻」をテストのコストの問題として扱う**。ビジネスルールが DB やネットワークの呼び出しと絡み合っていると、テストが遅く不安定になり、CI の待ち時間とエンジニアの時間を毎日浪費します。設計レビューでは「このルールを DB なしでテストできますか？」と問いましょう。答えが No なら、核と殻の分離が設計の宿題です。
4. **パラダイムや言語の採用は、採用市場と保守の問題でもある**。Haskell・Elixir・Clojure などは特定の領域で高い生産性と信頼性を発揮しますが、採用候補者の母数、立ち上がりの教育コスト、ライブラリの充実度、5 年後に誰が保守するかを考える必要があります。主要言語が関数型の要素を取り込んだ今、多くの利点は既存言語とチームの規約で得られます。新しい言語の提案には「それで何が可能になり、その代償を誰が払うのか」を具体的に説明してもらいましょう（言語選定の基準は [3.4 言語処理系を作る](../04-build-an-interpreter/README.md) の「CTOの視点」でまとめます）。
5. **採用面接では「なぜそう書くのか」を問う**。ループ内クロージャのバグの原因を説明できるか、継承を合成に直す理由を語れるか、例外と Result を状況に応じて使い分けられるかは、文法知識よりも設計を議論できる力をよく表します。

## 演習

演習コードは [exercises/paradigms.py](exercises/paradigms.py) にあります。関数・メソッドの docstring に仕様が書いてあるので、`raise NotImplementedError(...)` を実装に置き換えてください。解答例は [solutions/paradigms.py](solutions/paradigms.py) にありますが、まずは自力で取り組みましょう。

```bash
python3 tools/check.py 3.1        # リポジトリのルートで実行。合格数と失敗したテストが表示される
python3 tools/check.py -v 3.1     # 詳しい出力

# 演習ごとに実行する（exercises/ ディレクトリで）
python3 -m unittest -v test_paradigms.TestExercise2Streams
```

| # | 難易度 | 内容 | 関数・クラス |
|---|---|---|---|
| 1 | ★☆☆ | 関数合成・カリー化・メモ化デコレータ（ハッシュできない引数の扱い、例外をキャッシュしない） | `compose`, `pipe`, `curry`, `memoize` |
| 2 | ★★☆ | ジェネレータによる遅延ストリーム（必要な分だけ取り出す、引数の即時検査） | `iterate`, `take`, `take_while`, `chunked`, `sliding_window` |
| 3 | ★★☆ | 構造共有する永続リスト（経路コピー、再帰を使わない比較） | `PList` |
| 4 | ★★☆ | Result 型と、例外を使わない入力検証パイプライン（全項目のエラーを集める） | `Ok`, `Err`, `sequence`, `parse_int`, `parse_age`, `parse_email`, `validate_signup` |
| 5 | ★★★ | 表現問題: 評価器と整形器 → 新しい操作（微分）→ 新しい型（べき乗）＋ 記述（下記） | `evaluate`, `to_str`, `derive`, `Pow` |
| 6 | ★★☆ | 記述: チームのエラー処理方針を設計する（下記） | — |

### 演習 5 の進め方と記述課題

演習 5 は 3 段階です。**5a** で `Num`・`Var`・`Add`・`Mul`・`Neg` に対する `evaluate` と `to_str` を `match` 文で書き、**5b** で新しい操作 `derive`（微分）を追加し、**5c** で新しい型 `Pow`（べき乗）を 3 つの関数すべてに追加します。テストクラスも `TestExercise5aEvalAndPrint`・`TestExercise5bNewOperation`・`TestExercise5cNewType` に分かれています。実装を終えたら、次の問いに答えてください。

1. 5b（新しい操作）と 5c（新しい型）で、既存の関数を何か所変更しましたか。
2. 同じ AST を 8.1 節のオブジェクト指向版（各クラスにメソッドを持たせる）で作っていたら、5b と 5c はそれぞれ何か所の変更になりますか。
3. 「数式の種類はほぼ固定で、整形・最適化・コード生成などの操作が増えていく」システムなら、どちらの設計を選びますか。「利用者がプラグインで新しい種類のノードを追加できる」システムならどうですか。

<details>
<summary>解答例</summary>

1. 5b は `derive` を 1 つ **追加** しただけで、既存の関数は変更していません。5c は `Pow` の追加に加えて、`evaluate`・`to_str`・`derive` の **既存の 3 関数すべて** に分岐を追加しました（`to_str` では優先順位の規則にも手を入れました）。
2. オブジェクト指向版では逆になります。5b は `Num`・`Var`・`Add`・`Mul`・`Neg` の **既存の 5 クラスすべて** に `derive` メソッドを追加する必要があり、5c は `Pow` クラスを 1 つ追加してその中に 3 つのメソッドを書くだけです。
3. 種類が固定で操作が増えるなら関数型版が向いており、まれに型を追加したときの修正漏れは網羅性検査で検出できます。利用者がプラグインで種類を追加するなら、利用者は既存の関数を書き換えられないので、オブジェクト指向版（各ノードが必要な操作をすべて実装するインタフェース）か、`singledispatch` のように後から実装を登録できる仕組みが向いています。

採点の観点: 変更箇所の数を正しく数え、「どちらの軸が頻繁に拡張されるか」という判断基準を言語化できていれば合格です。網羅性検査や Visitor パターンに触れられていれば十分な理解です。

</details>

### 演習 6（記述）: チームのエラー処理方針

あなたは決済を扱う Python の Web サービス（開発者 30 名）のテックリードです。最近の障害レビューで、次のことが分かりました。

- 外部の決済 API がタイムアウトしたとき、`except Exception: logger.warning(...)` で握りつぶされ、注文が「支払い済み」のまま処理が進んでいた。
- 同じ種類の入力エラーが、ある API では HTTP 400、別の API では HTTP 500 として返っていた。
- 再試行のデコレータが、冪等でない「返金」処理にも付けられていた。

チームのエラー処理方針を A4 1 枚程度でまとめてください。「エラーの分類」「どの層で何をするか」「禁止事項とその検出方法」「再試行の条件」「レビューで確認すること」を含めてください。

<details>
<summary>解答例</summary>

**エラーの分類と扱い**

| 分類 | 例 | 表し方 | 扱い |
|---|---|---|---|
| 入力エラー | 金額が負、必須項目がない | 検証関数が Result（または `ValidationError`）で返す | HTTP 400 と項目ごとのメッセージ。ログは INFO |
| 一時的な外部障害 | 決済 API のタイムアウト | 専用の例外（`PaymentGatewayTimeout` など） | 冪等な操作に限り再試行。尽きたら注文を「保留」にし HTTP 503。アラート用メトリクスを増やす |
| 恒久的な外部の失敗 | カードの拒否 | ドメインの結果（`PaymentDeclined`） | 利用者に伝える。再試行しない |
| バグ | 不変条件の違反、想定外の `None` | 捕まえない | 最上位のハンドラが HTTP 500 とスタックトレース付きの ERROR ログ。エラー追跡ツールに送る |

**層ごとの責務**: ドメイン層（純粋関数）は入力検証と業務ルールの判定だけを行い、I/O をしない。アプリケーション層は外部 API の例外を捕まえて状態遷移を決め（「支払い済み」にせず「保留」にする）、注文 ID などの文脈を付けて包む（`raise ... from e`）。HTTP 層は、例外の種類からステータスコードへの対応表を **1 か所** に定義する（400 と 500 の揺れをなくす）。

**禁止事項と検出**: `except Exception:` や素の `except:` での握りつぶしを禁止し、リンタで検出する。最上位のハンドラなど例外的に必要な箇所は理由をコメントし、レビューで承認する。外部 API 呼び出しでは捕まえる例外の型を具体的に書く。

**再試行の条件**: 再試行してよいのは冪等な操作（GET、冪等キー付きの POST）だけ。返金・決済には冪等キーを必須とし、キーのない呼び出しに再試行デコレータを付けない。指数バックオフ・ジッター・最大回数は共通ライブラリで統一する。

**レビューで確認すること**: 「途中で失敗したら、データはどの状態に残るか」「この例外は誰がどの層で処理する想定か」「利用者の誤り・外部の障害・バグのどれか。ステータスコードとログレベルはそれに合っているか」。

採点の観点: (1) 想定内の失敗とバグを区別している、(2) 握りつぶしの禁止を仕組み（リンタ・レビュー）で担保している、(3) 再試行を冪等性と結び付けている、(4) 失敗時のデータの状態を考えている、の 4 点がそろえば合格です。

</details>

## 理解度チェック

**Q1. 手続き抽象とデータ抽象の違いを説明してください。また、1.1 節の有理数の例で、表現をタプルから辞書 `{"n": 5, "d": 6}` に変えるとき、変更が必要な関数はどれですか。**

<details>
<summary>解答</summary>

手続き抽象は、一連の計算に名前を付けて「どうやるか」を隠すことです。データ抽象は、データの表現を隠し、決められた操作（構築子・選択子など）だけで扱えるようにすることです。

変更が必要なのは、表現を知っている `make_rat`・`numer`・`denom` の 3 つだけです。`add_rat` は選択子と構築子しか使っていないので変更不要です。表現に依存するコードを最小限の場所に閉じ込めることで、変更の影響範囲を限定できるのが抽象の壁の効果です。

</details>

**Q2. 次のコードの出力と、その理由を説明してください。また、`[0, 10, 20]` を出力するように直してください。**

```python
fs = [lambda: i * 10 for i in range(3)]
print([f() for f in fs])
```

<details>
<summary>解答</summary>

出力は `[20, 20, 20]` です。3 つのラムダは、内包表記のスコープにある **同じ 1 つの変数 `i`** を捕まえており、値をコピーしていません（遅延束縛）。ラムダが呼ばれるのはループが終わった後なので、全員が最後の値 `i = 2` を読みます。

直し方は「今の値」を新しい束縛に閉じ込めることです。

```python
fs = [lambda i=i: i * 10 for i in range(3)]   # デフォルト引数は定義時に評価される
print([f() for f in fs])                       # [0, 10, 20]
```

`functools.partial` や、値を引数に取ってラムダを返す関数を使っても直せます。

</details>

**Q3. 2.5 節の `CountingCollection`（継承版）で `added` が 6 になる理由を、動的ディスパッチの観点から説明してください。基底クラスの `add_all` が将来 `self._items.extend(items)` に書き換えられたら、何が起きますか。**

<details>
<summary>解答</summary>

`CountingCollection.add_all` は 3 を加えてから `super().add_all()` を呼びます。基底クラスの `add_all` の中の `self.add(item)` は、`self` の実際のクラスである `CountingCollection` の `add` に動的ディスパッチされるので、さらに 1 ずつ計 3 が加算され、合計 6 になります。

基底クラスが `extend` を使うように変わると `add` が呼ばれなくなり、`added` は 3 になって、今度は「正しく」動きます。**利用者が何も変更していないのに、基底クラスの内部実装の変更で振る舞いが変わる** のが問題の本質です（脆い基底クラス問題）。合成で書けば、内部の `add` 呼び出しは内側のオブジェクトの中で完結するので、この問題は起きません。

</details>

**Q4. 次の関数のうち、`memoize` してよいものはどれですか。(a) `tax(price: int) -> int`（税額を計算） (b) `now_str() -> str`（現在時刻を文字列で返す） (c) `fetch_user(user_id: int) -> User`（DB から読む）**

<details>
<summary>解答</summary>

- (a) してよい。同じ引数なら同じ結果を返す純粋関数です（ただし税率が変わりうるなら、税率も引数にするのが望ましい）。
- (b) してはいけない。現在時刻に依存するので純粋ではなく、最初の結果を返し続けます。
- (c) 原則としてしてはいけない。DB の内容が変われば結果が変わります。キャッシュが必要なら、有効期限と無効化の方針を持つ専用のキャッシュ層として設計します。

</details>

**Q5. `def take(n, xs):` の本体に `if n < 0: raise ValueError` と `yield` の両方を書くと、`take(-1, data)` を呼んだ時点ではエラーが起きません。なぜですか。どう直しますか。**

<details>
<summary>解答</summary>

本体に `yield` を含む関数はジェネレータ関数になり、呼び出してもジェネレータオブジェクトが返るだけで、本体は最初の `next()` まで実行されません。そのため引数の検査も、誰かがそのジェネレータを回し始めるまで行われず、エラーが使用箇所で遅れて発生します。

検査を行う普通の関数と、要素を生成する内側のジェネレータ関数に分け、外側で検査してから内側を呼んだ結果を返すように直します（演習 2 の解答例を参照）。

</details>

**Q6. 次の 3 つの状況では、Result（エラー値）・例外・プロセスの中断のどれで扱うのが適切ですか。(a) 利用者がフォームに不正なメールアドレスを入力した (b) 起動時に必須の設定ファイルが存在しない (c) 残高の計算結果が負になった（仕様上ありえない）**

<details>
<summary>解答</summary>

- (a) 想定内の失敗なので、Result（または専用の検証例外）で返し、項目ごとのメッセージを表示します。1 項目目で止めず、全項目のエラーを集めるのが親切です（演習 4 の `validate_signup`）。
- (b) 回復の手段がないので、明確なメッセージを出して **起動時にすぐ終了** します。欠落を黙ってデフォルト値で補うと、本番で予期しない動作をします。
- (c) 仕様上ありえない状態はバグです。その場でつじつまを合わせず、アサーションや例外で処理を中断し、スタックトレースとともに記録して早く気付けるようにします。

</details>

**Q7. 表現問題とは何ですか。オブジェクト指向と関数型のスタイルで、それぞれ何が簡単で何が難しいかを説明してください。**

<details>
<summary>解答</summary>

データの種類（型）と、それに対する操作の両方を、既存のコードを変更・再コンパイルせず、型安全性を保ったまま追加できるか、という問題です（Philip Wadler, 1998）。オブジェクト指向（操作を各クラスのメソッドにする）では、新しい型の追加はクラスを 1 つ書くだけで簡単ですが、新しい操作の追加はすべてのクラスの修正が必要です。関数型（データと操作を分け、関数内で場合分けする）では逆に、新しい操作の追加は簡単で、新しい型の追加はすべての関数の修正が必要です（ただし網羅性検査で修正箇所を機械的に見つけられます）。どちらの軸が頻繁に拡張されるかで設計を選びます。

</details>

## さらに学ぶために

- Harold Abelson, Gerald Jay Sussman "Structure and Interpretation of Computer Programs"（邦訳『計算機プログラムの構造と解釈 第2版』和田英一訳、翔泳社）— 抽象の壁、クロージャ、ストリーム（遅延評価）、インタプリタの自作まで、第3部全体の考え方の源流。
- Peter Van Roy, Seif Haridi "Concepts, Techniques, and Models of Computer Programming"（MIT Press, 2004）— パラダイムを「言語が備える概念の組み合わせ」として体系的に比較する大著。
- Joshua Bloch "Effective Java" 第 3 版（邦訳『Effective Java 第3版』丸善出版）— 「継承よりコンポジション」「継承のために設計し文書化せよ」など、オブジェクト指向設計の実践的な指針。Java 以外でも通用する。
- Erich Gamma ほか "Design Patterns"（邦訳『オブジェクト指向における再利用のためのデザインパターン』ソフトバンククリエイティブ）— 合成の優先、Visitor パターンなど、オブジェクト指向の設計語彙の原典。
- John Hughes "Why Functional Programming Matters"（The Computer Journal, 1989）— 高階関数と遅延評価が「部品をつなぐ糊」としてモジュール性を高める理由を示した、短く読みやすい古典論文。
- Joe Duffy "The Error Model"（2016, ブログ記事）— 例外・エラーコード・Result・検査例外・panic を比較し、想定内のエラーとバグを区別する設計を論じた長文。
- Python 公式ドキュメント "Functional Programming HOWTO" — イテレータ、ジェネレータ、`itertools`、`functools` を体系的に解説している。

## まとめ

- **抽象化** は「詳細を隠して名前で扱う」こと。データ抽象では表現を少数の関数に閉じ込め、変わりそうな設計上の決定を隠す（情報隠蔽）。
- パラダイムは **制約の体系**。命令型は状態の書き換え、オブジェクト指向はカプセル化と動的ディスパッチ、関数型は純粋関数と不変性、宣言型は「何が欲しいか」の記述を中心に据える。
- 実装の継承は基底クラスの内部に依存し、**脆い基底クラス問題** を生む。is-a でなければ合成と委譲を使う。
- クロージャは変数そのものを捕まえるので、ループ内で作ると **遅延束縛** のバグになる。言語やバージョン（Go 1.22）で意味が違う。
- 純粋関数と不変データは、テスト・キャッシュ・並列化を容易にする。**関数型の核・命令型の殻** で I/O を境界に押し出す。ジェネレータは遅延評価の道具だが使い捨てである。
- エラー処理には例外・エラー値・Result 型のモデルがあり、どれでも **想定内の失敗とバグの区別** と、握りつぶさないことが最重要。
- **表現問題** が示すように、オブジェクト指向は型の追加、関数型は操作の追加に強い。どちらの軸が拡張されるかで選び、網羅性検査で弱点を補う。
- 現代の言語はマルチパラダイム。**どの部分をどのスタイルで書くかをチームで揃え、レビューとリンタで担保する** ことが、言語選択そのものより効く。
