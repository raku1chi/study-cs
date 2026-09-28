# 3.2 型システム

> 型は「このデータは何で、何をしてよいか」をコンピュータと人間の両方に伝える仕組みです。型検査は、実行する前にプログラムの一部の誤りを機械的に見つけてくれる、最も安価な検証手段でもあります。この章では、静的・動的、強い・弱いといった言葉を正確に使い分けられるようにしたうえで、型推論・構造的型付け・変性・代数的データ型を原理から理解し、小さな言語の型検査器と型推論器を自作します。そして「不正な状態を表現できない型」で、障害をそもそも起こせない設計を学びます。

| 項目 | 内容 |
|---|---|
| 学習時間の目安 | 本文 3h ＋ 演習 6h |
| 前提となる章 | [1.1 情報の表現](../../01-computer-systems/01-data-representation/README.md)、[3.1 プログラミングパラダイムと抽象化](../01-paradigms/README.md) |
| 演習 | [exercises/](exercises/)（Python） |
| キーワード | 静的型付け, 型推論, 単一化, 構造的型付け, 変性, 代数的データ型, 網羅性検査, newtype, 漸進的型付け, 健全性 |

## この章のゴール

- [ ] 型を「値の集合と、許される操作」として説明し、静的・動的と、強い・弱い（暗黙の型変換）を区別できる
- [ ] 型付け規則を読み、小さな言語の型検査器を実装できる
- [ ] 単一化による型推論の仕組みを説明し、実装できる
- [ ] 名前的型付けと構造的型付け、ジェネリクスの共変・反変・不変を具体例で説明できる
- [ ] 代数的データ型・パターンマッチ・網羅性検査を使い、不正な状態を表現できない型を設計できる
- [ ] newtype や単位付きの型で、ID・金額・物理量の取り違えを防げる
- [ ] 漸進的型付けと健全性の限界を理解し、システムの境界で実行時の検証を設計できる

## なぜ学ぶのか

型の取り違えは、ときに取り返しのつかない結果を招きます。

- **単位の取り違え**: 1999 年 9 月、NASA の火星探査機マーズ・クライメイト・オービターは、火星周回軌道への投入時に失われました。NASA の事故調査委員会の報告書（1999 年 11 月）によれば、根本原因は、地上ソフトウェアのあるファイルが、インタフェース仕様で定められたメートル法の単位（ニュートン・秒）ではなく、ヤード・ポンド法の単位（ポンド重・秒）で力積を出力していたことでした。1 ポンド重は約 4.45 ニュートンなので、軌道の計算がずれ、探査機は想定よりはるかに低い高度で火星に接近しました。数値に単位が付いていれば、この取り違えは機械的に検出できたはずです。
- **値の範囲の前提**: 1996 年、欧州のロケット アリアン 5 の初号機は、打ち上げから約 40 秒後に空中で分解しました。調査委員会の報告書によれば、アリアン 4 から流用した慣性基準装置のソフトウェアで、64 ビット浮動小数点数を 16 ビット符号付き整数に変換する際に値が範囲を超えて例外が発生し、主系・待機系の両方が停止しました。その変数は「アリアン 4 の飛行経路では範囲に収まる」という前提で、変換の保護が省かれていました。**型が値の範囲の前提を表していなかった** 例です（整数の範囲は [1.1 情報の表現](../../01-computer-systems/01-data-representation/README.md) を参照）。
- **null**: ヌル参照を発明した Tony Hoare は、2009 年の QCon London での講演で、1965 年に ALGOL W の型システムを設計した際、実装が簡単だという理由でヌル参照を入れてしまったことを「10 億ドルの過ち（billion-dollar mistake）」と呼びました。null がありうるかどうかが型に表れないことが、無数のクラッシュの原因になってきました。
- **型検査の効果**: Gao・Bird・Barr の研究 "To Type or Not to Type"（ICSE 2017）は、公開されている JavaScript プロジェクトのバグを調べ、TypeScript や Flow の型注釈を付けていれば、その約 15% が検出できたと報告しています。型は万能ではありませんが、安価に一定割合のバグを消せる手段です。

## 1. 型とは何か

### 1.1 値の集合と、許される操作

**型（type）** は、値の集合と、それに対して許される操作の組です。`int` は整数の集合で、足し算や比較ができます。`str` は文字列の集合で、連結や部分文字列の取り出しができます。**型エラー（type error）** とは、操作をその定義域の外の値に適用することです。`"abc" - 1` は、引き算が文字列に対して定義されていないので型エラーです。

[1.1 情報の表現](../../01-computer-systems/01-data-representation/README.md) で見たように、メモリ上の値はただのビット列で、それ自体は「自分が何か」を知りません。型はビット列の **解釈のルール** であり、型システムはそのルールが守られているかを検査する仕組みです。型は検査のほかにも、ドキュメント（関数が何を受け取り何を返すか）、エディタの補完やリファクタリング、コンパイラの最適化（メモリ配置の決定など）に使われます。

### 1.2 静的型付けと動的型付け

型の検査を **いつ** 行うかで、言語は大きく 2 つに分かれます。

- **静的型付け（static typing）**: 実行前（コンパイル時）に検査する。Java、C、Go、Rust、TypeScript など。
- **動的型付け（dynamic typing）**: 実行時に、操作を行う直前に検査する。Python、JavaScript、Ruby など。値そのものが型の情報を持っている。

動的型付けでも型の検査は行われます。違いは、**実行されなかったコードの誤りは見つからない** ことです。

```python
def describe(n: int) -> str:
    if n > 1000:
        return "big: " + n      # この行が実行されるまで、誰も気付かない
    return "small"

print(describe(5))              # small（エラーにならない）
```

型検査器 mypy にかけると、実行せずに見つかります（mypy 2.3 での出力）。

```text
describe.py:3: error: Unsupported operand types for + ("str" and "int")  [operator]
Found 1 error in 1 file (checked 1 source file)
```

静的型付けは、実行されにくいエラー処理の分岐や、めったに来ない入力のケースの誤りを事前に見つけられるのが強みです。動的型付けは、書き始めが速く、型で表しにくい柔軟な構造を扱いやすいのが強みです。後で見る **漸進的型付け** は、その中間を狙います。

### 1.3 強い型付けと弱い型付け — 暗黙の型変換

「強い型付け・弱い型付け」は、よく使われるのに定義があいまいな言葉です。多くの場合、**暗黙の型変換（implicit coercion）がどれだけ行われるか** を指します。JavaScript は暗黙の変換が多い言語です（Node.js 22 で実行）。

```javascript
console.log("5" - 2);          // 3          数値に変換して引き算
console.log("5" + 2);          // 52         文字列に変換して連結
console.log([1, 2] + [3]);     // 1,23       配列を文字列に変換して連結
console.log(0 == "");          // true       == は型を変換してから比べる
console.log("0" == false);     // true
console.log(null == 0, null >= 0);   // false true
console.log([10, 9, 1].sort());      // [ 1, 10, 9 ]  既定では文字列として並べ替える
```

C は静的型付けですが、暗黙の変換が多く、しかも危険です。

```c
int balance = -1;
unsigned int limit = 100;
if (balance < limit) printf("-1 < 100\n");
else                 printf("-1 >= 100 ?!\n");   /* こちらが表示される */
```

`int` と `unsigned int` を比べると、`-1` が符号なしに変換されて 4294967295 になるためです（`gcc -Wall -Wextra` なら警告が出ます）。Python は、暗黙の変換が少ない言語です。`"5" + 2` は `TypeError: can only concatenate str (not "int") to str` になります。ただし、`True + True` が `2` になる（`bool` は `int` のサブクラス）、`1 + 2.0` が `3.0` になる、といった数値の間の変換はあります。

| 言語 | 型検査の時期 | 暗黙の型変換 |
|---|---|---|
| C | 静的 | 多い（整数の昇格、符号付き・符号なしの変換など） |
| JavaScript | 動的 | 多い（`+` や `==` での文字列・数値の変換） |
| Java | 静的 | 少なめ（数値の拡大変換、`"a" + 1` の文字列化） |
| Python | 動的 | 少ない（数値の型の間、`bool` → `int`） |
| Go, Rust | 静的 | ほとんどない（`int` と `int64` の間でも明示的な変換が必要） |

このように、静的・動的と、強い・弱いは **独立した 2 つの軸** です。議論では「強い型付け」という言葉より、「どの変換が暗黙に行われるか」を具体的に言う方が誤解がありません。

## 2. 型検査と型推論

### 2.1 型付け規則

型検査器は、**型付け規則（typing rule）** に従って、式の型を部分式の型から組み立てます。規則は、次のように「横線の上の前提がすべて成り立てば、下の結論が成り立つ」という形で書くのが慣例です。`Γ` は「変数名 → 型」の対応（**型環境**）で、`Γ ⊢ e : T` は「環境 Γ のもとで式 e は型 T を持つ」と読みます。

```text
Γ ⊢ c : bool    Γ ⊢ a : T    Γ ⊢ b : T              Γ ⊢ f : A -> B    Γ ⊢ x : A
─────────────────────────────────────── (If)        ─────────────────────────── (App)
      Γ ⊢ if c then a else b : T                            Γ ⊢ f x : B
```

If の規則は「条件が bool で、両方の分岐が **同じ型** T なら、if 式全体の型は T」と言っています。App（関数適用）の規則は「f が A を受け取り B を返す関数で、引数 x が A 型なら、結果は B 型」です。演習 3 では、次のような小さな言語の型検査器を実装します（演習では構文解析はせず、構文木を直接組み立てます）。

```text
let inc = fn (x: int) => x + 1 in        -- inc : int -> int
let twice = fn (f: int -> int) => fn (x: int) => f (f x) in
  (twice inc 5, "n=" ++ "7")             -- (int, str)
```

規則をそのままコードにすると、型検査器は **構文木をたどる再帰関数** になります。

```python
# 解答例を簡略化した抜粋
def check(expr, env):
    match expr:
        case If(cond, then, else_):
            expect(check(cond, env), BOOL, "if の条件")
            t1, t2 = check(then, env), check(else_, env)
            if t1 != t2:
                raise TypeCheckError(f"if の両分岐の型が一致しません: {show_type(t1)} と {show_type(t2)}")
            return t1
        case App(func, arg):
            ...
```

大事なのは **エラーメッセージ** です。「型エラー」とだけ言う検査器は使われません。「どこで」「何を期待し」「実際は何だったか」を伝えることが、型検査器の品質の半分を占めます。

### 2.2 局所的な型推論

型を毎回書くのは面倒です。**型推論（type inference）** は、書かれていない型を処理系が補う仕組みです。多くの言語は、変数の初期値や関数の戻り値から型を決める **局所的な型推論** を備えています（Java の `var`、C++ の `auto`、Go の `:=`、TypeScript、Rust、Kotlin など）。TypeScript が推論した型は、宣言ファイルを出力すると確認できます（TypeScript 6.0 で `tsc --declaration` を実行）。

```typescript
export const nums = [1, 2, 3];
export const labels = nums.map(n => `#${n}`);
export function twice<T>(f: (x: T) => T, x: T) { return f(f(x)); }
export const r = twice(n => n * 2, 5);
```

```text
export declare const nums: number[];
export declare const labels: string[];
export declare function twice<T>(f: (x: T) => T, x: T): T;
export declare const r: number;
```

### 2.3 Hindley–Milner 型推論と単一化

ML や Haskell、OCaml は、関数の引数にも型を書かずに済む、より強力な推論を持っています。その基礎が **Hindley–Milner 型推論** です（Hindley 1969、Milner 1978）。考え方は、論理型プログラミング（[3.1](../01-paradigms/README.md)）と同じく **連立方程式を解く** ことです。

1. 型の分からない変数に、**型変数**（`'a`, `'b`, …）を割り当てる。
2. 式をたどりながら、型付け規則から「この 2 つの型は等しい」という **制約** を集める。
3. 制約を **単一化（unification）** で解き、型変数に何が入るか（**代入**）を求める。

`fn f => fn x => f (f x)`（関数を 2 回適用する関数）で追ってみましょう。

```text
1. f : 'a,  x : 'b （新しい型変数を割り当てる）
2. f x      : f の型 'a と「'b -> 'c」を単一化        → 'a := 'b -> 'c。f x の型は 'c
3. f (f x)  : f の型 'b -> 'c と「'c -> 'd」を単一化  → 'b := 'c, 'c := 'd。結果の型は 'd
4. 全体の型 'a -> 'b -> 'd に代入を適用すると ('d -> 'd) -> 'd -> 'd
   名前を付け直して ('a -> 'a) -> 'a -> 'a
```

単一化は、2 つの型を「同じ形」にする型変数の割り当てを見つける操作で、次の場合分けだけでできています。

- 同じ型なら何もしない。
- 片方が型変数なら、その型変数にもう片方を割り当てる。
- 両方が関数型なら、引数どうし・結果どうしを単一化する（組の型も同様）。
- それ以外（`int` と `bool`、`int` と関数型など）は型エラー。

1 つ落とし穴があります。`fn x => x x`（自分自身に自分を適用する）では、`x : 'a` と「`'a -> 'b`」を単一化することになり、`'a = 'a -> 'b = ('a -> 'b) -> 'b = …` と無限に続く型になってしまいます。これを防ぐのが **出現検査（occurs check）** で、型変数を、その型変数自身を含む型に割り当てようとしたら型エラーにします。演習 4 では、この単一化による型推論を実装します。

実際の HM 型推論には、さらに **let 多相**（`let id = fn x => x in (id 1, id true)` のように、let で束縛した関数を別々の型で使えるようにする仕組み）があります。演習 4 では扱いませんが、推論した型の中の型変数を「どの型でもよい」と一般化（generalize）し、使うたびに新しい型変数で具体化（instantiate）することで実現します。Milner は 1978 年の論文で「**型の付いたプログラムは誤動作しない**（Well-typed programs cannot go wrong）」という標語とともにこの体系を示しました。

## 3. 型の互換性 — 名前的型付けと構造的型付け

ある型の値を、別の型が期待される場所で使ってよいか。これを決める方式が 2 つあります。

- **名前的型付け（nominal typing）**: 型の **名前と宣言された関係** で決める。Java では、`class Rect implements Shape` と宣言しない限り、`Rect` は `Shape` として使えない。
- **構造的型付け（structural typing）**: 型の **構造**（持っているプロパティやメソッド）で決める。TypeScript、Go のインタフェース、Python の Protocol がこの方式。

TypeScript では、宣言なしに構造が合えば互換です（TypeScript 6.0、`--strict` で検査）。

```typescript
interface Point { x: number; y: number }
function norm(p: Point): number { return Math.sqrt(p.x ** 2 + p.y ** 2); }

class Vec2 { constructor(public x: number, public y: number) {} }  // Point を implements していない
const v3 = { x: 3, y: 4, z: 12 };

norm(new Vec2(3, 4));            // OK: 構造が合う
norm(v3);                        // OK: 余分なプロパティがあっても構わない
norm({ x: 3, y: 4, z: 12 });     // エラー: オブジェクトリテラルを直接渡すときだけ、余分なプロパティを検査する
// error TS2353: Object literal may only specify known properties, and 'z' does not exist in type 'Point'.
```

Go のインタフェースも、メソッドを持っていれば「実装している」とみなされます（`implements` の宣言はありません）。

```go
type Shape interface{ Area() float64 }
type Rect struct{ W, H float64 } // Shape を実装すると宣言していない
func (r Rect) Area() float64     { return r.W * r.H }

func main() {
	var s Shape = Rect{2, 3} // Area() を持つので Shape として使える
	fmt.Println(s.Area())    // 6
}
```

Python では、実行時には **ダックタイピング**（「アヒルのように鳴くならアヒル」: 必要なメソッドがあれば使える）で動き、静的には `typing.Protocol` で構造的な型を表せます（mypy 2.3 での出力）。

```python
from typing import Protocol

class SupportsClose(Protocol):
    def close(self) -> None: ...

class File:                      # SupportsClose を継承していない
    def close(self) -> None: ...
class Door:
    def shut(self) -> None: ...

def cleanup(resource: SupportsClose) -> None:
    resource.close()

cleanup(File())                  # OK: close() を持つので構造的に適合する
cleanup(Door())
# error: Argument 1 to "cleanup" has incompatible type "Door"; expected "SupportsClose"  [arg-type]
```

| 方式 | 長所 | 短所 |
|---|---|---|
| 名前的 | 意図しない互換がない。「この型はこの契約を満たす」と宣言で明示される | 既存の型（ライブラリのクラスなど）に後からインタフェースを実装させにくい |
| 構造的 | 既存の型にも後から適用できる。疎結合なモジュール間で便利 | 形が同じなら意味が違っても互換になる（`{ id: string }` のユーザー ID と注文 ID など） |

構造的型付けの「形が同じなら通ってしまう」問題への対策が、6 章で扱う **newtype** やブランド型です。

## 4. ジェネリクスと変性

### 4.1 ジェネリクス

**ジェネリクス（generics）** は、型を引数に取るパラメトリック多相（[3.1](../01-paradigms/README.md)）の仕組みです。`list[int]` と `list[str]` を同じ `list` の定義で扱えます。実装方式は言語によって異なり、Java は型引数をコンパイル後に消す **型消去（type erasure）**、C++ のテンプレートや Rust は型ごとにコードを複製する **単相化（monomorphization）** を採用しています。単相化は実行時のコストがない代わりに、バイナリが大きくなりコンパイルが遅くなります。

### 4.2 共変・反変・不変

`Dog` が `Animal` のサブタイプ（`Dog <: Animal`）のとき、`list[Dog]` は `list[Animal]` のサブタイプでしょうか。これを決めるのが **変性（variance）** です。

- **共変（covariant）**: `Dog <: Animal` なら `F[Dog] <: F[Animal]`（向きが同じ）。
- **反変（contravariant）**: `Dog <: Animal` なら `F[Animal] <: F[Dog]`（向きが逆）。
- **不変（invariant）**: どちらの関係も成り立たない。

答えは「**読むだけなら共変、書き込むなら不変**」です。もし `list[Dog]` を `list[Animal]` として渡せたら、受け取った側が `Cat` を追加でき、元の `list[Dog]` に猫が混入します。mypy はこれを拒否します（mypy 2.3 での出力）。

```python
from typing import Callable, Sequence

class Animal: ...
class Dog(Animal):
    def bark(self) -> str: return "わん"

def feed_all(animals: list[Animal]) -> None: ...
def count_all(animals: Sequence[Animal]) -> int: return len(animals)

dogs: list[Dog] = [Dog()]
feed_all(dogs)          # エラー: list は不変（invariant）
count_all(dogs)         # OK: Sequence は読み取り専用なので共変（covariant）
```

```text
error: Argument 1 to "feed_all" has incompatible type "list[Dog]"; expected "list[Animal]"  [arg-type]
note: "list" is invariant -- see https://mypy.readthedocs.io/en/stable/common_issues.html#variance
note: Consider using "Sequence" instead, which is covariant
```

Java はこの点で歴史的な妥協をしています。**配列は共変** なので、コンパイルは通り、実行時の検査で初めて失敗します。

```java
String[] strings = new String[1];
Object[] objects = strings;      // 配列は共変: String[] を Object[] として扱える
objects[0] = 42;                 // コンパイルは通る
// 実行結果: Exception in thread "main" java.lang.ArrayStoreException: java.lang.Integer
```

後から導入されたジェネリクス（Java 5）は不変で、`List<Object> objects = ints;`（`ints` は `List<Integer>`）はコンパイルエラー（`incompatible types: List<Integer> cannot be converted to List<Object>`）になります。読むだけの引数には `List<? extends Number>`、書き込むだけの引数には `List<? super Integer>` と書いて変性を指定します（『Effective Java』の "PECS: Producer Extends, Consumer Super"）。

**関数の型** では、引数は反変、戻り値は共変です。「動物を受け取れる関数」は「犬を受け取る関数」が必要な場所で使えます（犬は動物なので）が、逆はできません（猫を渡されたら `bark()` できない）。

```python
def on_animal(a: Animal) -> None: ...
def on_dog(d: Dog) -> None: print(d.bark())

dog_handler: Callable[[Dog], None] = on_animal     # OK: 引数は反変
animal_handler: Callable[[Animal], None] = on_dog  # エラー
```

変性を正しく扱えることは、型システムの **健全性** に直結します。TypeScript は利便性のために、配列を共変として扱い、メソッド記法で宣言したメソッドの引数を双変（どちら向きでも可）として扱っています。どちらも `--strict` でコンパイルが通り、実行時に失敗しうる例です（7.2 節）。

## 5. 代数的データ型とパターンマッチ

### 5.1 直積型と直和型

型を組み合わせる基本的な方法は 2 つあります。

- **直積型（product type）**: 複数の値を **すべて** 持つ型。タプル、レコード、構造体、データクラス。`(bool, bool)` の値は 2 × 2 = 4 通り。
- **直和型（sum type）**: 複数の型の **どれか 1 つ** の値を持つ型。タグ付き共用体（tagged union）とも呼ぶ。`bool | Color`（Color が 3 通り）の値は 2 + 3 = 5 通り。

値の数が掛け算と足し算で決まるので、これらを組み合わせた型を **代数的データ型（ADT: algebraic data type）** と呼びます。直和型は Rust の `enum`、Haskell・OCaml のデータ型、Swift の関連値付き `enum`、TypeScript の判別可能な共用体（discriminated union）、Python のデータクラスの `Union`、Java 17 の sealed クラスなどで表せます。

### 5.2 null と Option

Hoare の「10 億ドルの過ち」の本質は、**null があらゆる参照型に暗黙に含まれている** ことでした。`String` 型の変数に null が入りうるなら、`String` は実は「`String` または null」という直和型であり、すべての使用箇所で null の確認が必要なのに、型はそれを要求しません。現代の言語は、null の可能性を型に明示します。

| 言語 | 「値がないかもしれない」の表し方 |
|---|---|
| Rust | `Option<T>`（`Some(x)` か `None`）。null は存在しない |
| Haskell / OCaml | `Maybe a` / `'a option` |
| Kotlin, Swift, C# 8 以降 | `String?` のように型に `?` を付ける（付けなければ null 不可） |
| TypeScript（`strictNullChecks`） | `string \| null` |
| Python（型ヒント） | `str \| None`（`Optional[str]`） |

型に表れていれば、検査器が確認漏れを見つけます（mypy 2.3 での出力）。

```python
def find_user(user_id: int) -> str | None:
    return "alice" if user_id == 1 else None

name = find_user(2)
print(name.upper())          # error: Item "None" of "str | None" has no attribute "upper"  [union-attr]
if name is not None:
    print(name.upper())      # OK: ここでは str に絞り込まれている（narrowing）
```

### 5.3 パターンマッチと網羅性検査

直和型の値は、**パターンマッチ** で種類ごとに分解して扱います。そして直和型の最大の利点は、処理系が **すべての場合を扱ったか（網羅性, exhaustiveness）** を検査できることです。Rust で、後から `Triangle` を追加して `match` を直し忘れると、コンパイルエラーになります（rustc 1.94 での出力の抜粋）。

```rust
enum Shape {
    Circle { r: f64 },
    Rect { w: f64, h: f64 },
    Triangle { base: f64, height: f64 },   // 後から追加した
}

fn area(s: &Shape) -> f64 {
    match s {
        Shape::Circle { r } => std::f64::consts::PI * r * r,
        Shape::Rect { w, h } => w * h,
    }
}
// error[E0004]: non-exhaustive patterns: `&Shape::Triangle { .. }` not covered
```

Python でも、`match` 文と `typing.assert_never`（3.11 以降）を組み合わせると、mypy が同じ検査をします。

```python
Shape = Circle | Rect | Triangle      # それぞれデータクラス

def area(s: Shape) -> float:
    match s:
        case Circle(r):
            return 3.14159 * r * r
        case Rect(w, h):
            return w * h
        case _:
            assert_never(s)  # ここに到達しうる型が残っていれば、mypy がエラーにする
# error: Argument 1 to "assert_never" has incompatible type "Triangle"; expected "Never"  [arg-type]
```

[3.1 の表現問題](../01-paradigms/README.md) で見たとおり、この検査があるので「新しい種類を追加したときに直すべき場所」をツールが列挙してくれます。

### 5.4 不正な状態を表現できなくする

**「不正な状態を表現できなくする（make illegal states unrepresentable）」** は、Jane Street の Yaron Minsky が広めた標語です。ネットワーク接続の状態を、次のように表したとします。

```python
@dataclass
class Connection:
    state: str                  # "disconnected" / "connecting" / "connected"
    attempt: int | None         # 接続中のときだけ意味がある
    session_id: str | None      # 接続済みのときだけ意味がある
```

この型は「接続済みなのに `session_id` が `None`」「未接続なのに `attempt` が 3」「`state` が `"conected"`（綴り間違い）」といった **ありえない状態** を表せてしまいます。すべての使用箇所で「この組み合わせは正しいか」を確認しなければならず、確認漏れがバグになります。直和型で書き直すと、ありえない状態は **そもそも作れません**。

```python
@dataclass(frozen=True)
class Disconnected:
    pass

@dataclass(frozen=True)
class Connecting:
    attempt: int               # 接続中のときだけ存在する

@dataclass(frozen=True)
class Connected:
    session_id: str            # 接続済みのときだけ存在する

Connection = Disconnected | Connecting | Connected

def describe(c: Connection) -> str:
    match c:
        case Disconnected():
            return "未接続"
        case Connecting(attempt):
            return f"接続中（{attempt} 回目）"
        case Connected(session_id):
            return f"接続済み（{session_id}）"
```

値の数で考えると、元の型は「文字列 × (int または None) × (str または None)」という巨大な直積で、その大半が不正な組み合わせです。新しい型は「1 ＋ int ＋ str」で、正しい状態とぴったり一致します。**型の値の集合を、正しい状態の集合に近づける** ことが、型による設計の本質です。

## 6. ドメインを型で表す — newtype と単位

ユーザー ID も注文 ID も `int`、金額も個数も `int`、メートルもフィートも `float` で表すと、型検査器は取り違えを見つけられません。これを防ぐのが **newtype**（既存の型を包んで、別の名前の型にしたもの）です。Python の `typing.NewType` は、静的検査の段階だけで区別される軽量な newtype です（mypy 2.3 での出力）。

```python
from typing import NewType

UserId = NewType("UserId", int)
OrderId = NewType("OrderId", int)

def cancel_order(order_id: OrderId) -> None: ...

uid = UserId(42)
cancel_order(uid)            # error: Argument 1 to "cancel_order" has incompatible type "UserId"; expected "OrderId"
cancel_order(OrderId(42))    # OK
print(type(uid))             # <class 'int'>（実行時にはただの int）
```

Rust の newtype（`struct UserId(u64);`）は実行時のコストがゼロで、しかも型として完全に区別されます。TypeScript では、構造的型付けのもとで区別を作るために `string & { readonly __brand: "UserId" }` のような **ブランド型** を使う手法が広く使われています。

金額や物理量は、さらに **振る舞い** を型に持たせる価値があります。

- **金額**: 通貨が違う金額は足せない。小数倍（税率など）には丸め方の決定が必要。分配しても合計が変わってはいけない。演習 1 の `Money` は、これらを型の操作として実装します（金額を最小単位の整数で持つ理由は [1.1](../../01-computer-systems/01-data-representation/README.md) を参照）。
- **物理量**: 長さと時間は足せないが、割ると速度になる。演習 2 の `Quantity` は、値と一緒に **次元**（kg・m・s などの指数）を持ち、足し算では次元の一致を検査し、掛け算・割り算では次元を合成します。マーズ・クライメイト・オービターの事故は、ポンド重・秒とニュートン・秒という **同じ次元（力積）の異なる単位** の取り違えでした。値を常に SI 単位で内部に持ち、生成時に単位を付けさせれば、換算は自動で正しく行われ、単位のない「裸の数値」を混ぜることは型エラーになります。

```python
impulse = 100 * POUND_FORCE * SECOND          # 演習 2 の Quantity で
print(impulse.to(NEWTON * SECOND))            # 444.82216152604997（自動で換算される）
impulse + 100                                 # DimensionError: 単位のない数値は足せない
```

F# のように、単位（units of measure）を言語の型システムに組み込み、コンパイル時に検査する言語もあります。

## 7. 漸進的型付けと健全性

### 7.1 漸進的型付け

**漸進的型付け（gradual typing）** は、1 つのプログラムの中で、型を書いた部分は静的に検査し、書いていない部分は動的に扱うという方式です（Siek と Taha が 2006 年に定式化）。TypeScript と、Python の型ヒント（PEP 484）＋ 型検査器（mypy、pyright など）が代表例です。型の分からない部分は `any`（Python では `Any`）という「何とでも互換な型」として扱われ、検査の対象外になります。

漸進的型付けは、既存の動的型付けのコードベースに **少しずつ型を導入できる** ことが最大の価値です。一方で、`any` が混ざった部分では検査が働かないので、「型が付いているのにバグが素通りする」状態になりえます。導入時は、新しいコードから厳格な設定（mypy の `--strict`、TypeScript の `strict`）を適用し、モジュール単位で厳格な範囲を広げていくのが定石です。

Python の型ヒントは **実行時には検査されない** ことにも注意してください。`def f(x: int)` に文字列を渡しても、Python は何も言いません。型ヒントは、型検査器やエディタのための情報です。

### 7.2 健全性

型システムが **健全（sound）** であるとは、「型検査を通ったプログラムは、実行時に型エラーを起こさない」ことです。完全に健全な型システムは、正しいプログラムの一部も拒否してしまうため（型検査は保守的な近似です）、実用言語は健全性と使いやすさの間で妥協しています。TypeScript は、設計目標の文書で「健全な、証明可能な正しさを持つ型システム」を目標としないと明記し、正しさと生産性のバランスを取ると述べています。次のコードは `tsc --strict` でエラーなくコンパイルされ、実行時に失敗します（TypeScript 6.0、Node.js 22）。

```typescript
class Animal { name = "animal"; }
class Dog extends Animal { bark() { return "わん"; } }
class Cat extends Animal { meow() { return "にゃー"; } }

const dogs: Dog[] = [new Dog()];
const animals: Animal[] = dogs;               // (1) 配列は共変として扱われる
animals.push(new Cat());                      //     Dog[] に Cat が入る
const d = JSON.parse('{"name": "x"}') as Dog; // (2) 型アサーション（as）は検査されない約束
const nums: number[] = [];
const first: number = nums[0];                // (3) 添字アクセスは要素があるものとして扱われる

console.log(first);                                              // undefined（型は number のはず）
try { dogs[1].bark(); } catch (e) { console.log(String(e)); }   // TypeError: dogs[1].bark is not a function
try { d.bark(); } catch (e) { console.log(String(e)); }         // TypeError: d.bark is not a function
```

(3) はコンパイラオプション `noUncheckedIndexedAccess` を有効にすると `number | undefined` として扱われ、検出できるようになります。(2) の `as` や `any` は、**型検査器に「私を信じろ」と言う抜け穴** です。抜け穴の数は、コードベースの型の信頼性を測る指標になります。

### 7.3 境界では実行時に検証する — Parse, don't validate

どれほど型を整えても、**プログラムの外から来るデータには型がありません**。HTTP リクエストの JSON、環境変数、設定ファイル、データベースの行、外部 API の応答は、すべて「何が入っているか分からないバイト列」です。上の `JSON.parse(...) as Dog` のように、外部データを検証せずに型付きの値として扱うのが、健全性の最大の抜け穴です。

Alexis King は 2019 年のブログ記事 "Parse, don't validate" で、検証の結果を真偽値として捨てるのではなく、**検証済みであることが型で分かる値に変換（parse）せよ** と説きました。システムの **境界で一度だけ** 解析し、内部のコードは解析済みの型だけを扱います。

```python
import json
from dataclasses import dataclass

@dataclass(frozen=True)
class ServerConfig:          # この型の値があれば「検証済み」であることが保証される
    host: str
    port: int
    debug: bool

def parse_config(raw: object) -> ServerConfig:
    """境界で一度だけ解析する。以降のコードは ServerConfig だけを扱う。"""
    if not isinstance(raw, dict):
        raise ValueError("設定は JSON オブジェクトである必要があります")
    host, port, debug = raw.get("host"), raw.get("port"), raw.get("debug", False)
    if not isinstance(host, str) or not host:
        raise ValueError("host は空でない文字列です")
    if type(port) is not int or not 1 <= port <= 65535:   # bool は int のサブクラスなので type で判定
        raise ValueError(f"port は 1〜65535 の整数です: {port!r}")
    if type(debug) is not bool:
        raise ValueError(f"debug は true か false です: {debug!r}")
    return ServerConfig(host, port, debug)

print(parse_config(json.loads('{"host": "db.internal", "port": 5432}')))
# ServerConfig(host='db.internal', port=5432, debug=False)
parse_config(json.loads('{"host": "db.internal", "port": "5432"}'))
# ValueError: port は 1〜65535 の整数です: '5432'
```

実務では、Python の pydantic、TypeScript の zod のようなライブラリや、JSON Schema・OpenAPI・Protocol Buffers などのスキーマから型と検証コードを生成する方法が使われます（[9.4 API設計](../../09-architecture/04-api-design/README.md)）。[3.1 の演習 4](../01-paradigms/README.md) の `validate_signup` も同じ考え方です。

### 7.4 さらに表現力の高い型

型で表せる性質には限りがあり、「リストが整列済み」「インデックスが範囲内」「残高が 0 以上」といった性質は、普通の型では表せません。**篩型（refinement type）** は `{v: int | v > 0}` のように述語で値を絞り込んだ型で、Liquid Haskell などが実装しています。**依存型（dependent type）** は型が値に依存できる型で（「長さ n のベクトル」など）、Idris・Agda・Lean などが備えており、プログラムの性質を証明することもできます。業務のコードでこれらを使うことはまだ少ないですが、**スマートコンストラクタ**（検査を通った場合だけ値を作れる関数。`parse_config` もその一種）で、同じ効果の一部を普通の言語で得られます。

## よくある落とし穴

1. **型注釈を書けば実行時にも検査されると思う**。Python の型ヒントも TypeScript の型も、実行時には消える。外部から来るデータは、境界で実行時に検証する。
2. **`any`・`as`・`cast`・`# type: ignore` で型エラーを黙らせる**。型検査器に嘘をつくと、そこから先の検査はすべて信用できなくなる。使うなら理由をコメントに書き、数を監視する。
3. **外部データを検証せずに型付きの値として扱う**。`JSON.parse(body) as User` は、「User であってほしい」という願望にすぎない。スキーマで解析する。
4. **null / None に複数の意味を持たせる**。「未設定」「不明」「エラー」「該当なし」を全部 `None` で表すと、呼び出し側が区別できない。意味ごとに直和型の別の場合として表す。
5. **何でも文字列や整数で表す（stringly typed）**。状態を `"active"` のような文字列で持つと、綴り間違いが型検査を通る。列挙型や直和型、newtype を使う。
6. **可変なコレクションを共変として扱う**。Java の配列や TypeScript の配列では型検査が通ってしまい、実行時に別の型の要素が混入する。読むだけなら読み取り専用の型（`Sequence`、`ReadonlyArray`）を使う。
7. **Python で `isinstance(x, int)` を整数の検証に使う**。`bool` は `int` のサブクラスなので `True` が通ってしまう。JSON の `true` が「1」として受け入れられる。`type(x) is int` を使うか、`bool` を先に除外する。
8. **型が通れば正しいと思い込む**。型は「一部の誤り」を消すだけで、ロジックの誤りは検出しない。テスト（[8.2 テスト戦略](../../08-software-engineering/02-testing/README.md)）と組み合わせる。

## CTOの視点

1. **型の導入は段階的な投資として計画する**。動的型付けの大規模コードベースに型を入れる判断では、「新しいコードは厳格モード必須」「変更したファイルには型を付ける」「CI で型検査を必須にし、厳格なモジュールの割合を指標にする」のように、機能開発を止めない段階的な計画を立てます。一度に全体を移行する計画は、ほぼ確実に途中で止まります。効果は、バグの減少だけでなく、リファクタリングの安全性、新メンバーの立ち上がりの速さ、エディタの補完による生産性にも現れます。
2. **システムの境界の型を組織の標準にする**。サービス間の API、イベントのスキーマ、設定ファイルは、OpenAPI・Protocol Buffers・JSON Schema などで定義し、型と検証コードを生成する方針にします。境界で型が保証されていれば、サービス内部の型も信頼できます。設計レビューでは「外部から来るデータは、どこで、何によって検証されますか？」と必ず問いましょう。
3. **ドメインの型を共通ライブラリとして提供する**。金額（通貨付き）、ID（種類ごとの newtype）、日時（タイムゾーン付き）、物理量といった型を組織で 1 つ用意し、「金額は Money 型以外で扱わない」といった規約にすれば、マーズ・クライメイト・オービター型の事故の一群を、個人の注意力に頼らずに防げます。作るコストは小さく、効果は全チームに及びます。
4. **型の抜け穴を指標として監視する**。`any`・`as`・`# type: ignore`・`cast` の数を CI で計測し、増加をレビューで確認します。コードレビューでは「この `as` が安全だと言える根拠は何ですか？」と問う文化を作ります。抜け穴がゼロである必要はありませんが、理由なく増えていくのは型の信頼性が崩れていく兆候です。
5. **設計レビューで「不正な状態を表現できるか」を問う**。データモデルや API のスキーマに、組み合わせによっては意味をなさない nullable なフィールドが並んでいたら、直和型（判別可能な共用体、`oneOf`）で書き直せないか検討させます。この視点を持つエンジニアは、障害の少ない設計をする傾向があり、シニア以上の評価や採用面接で見極める価値があります。

## 演習

演習コードは [exercises/units.py](exercises/units.py) と [exercises/typechecker.py](exercises/typechecker.py) にあります。docstring の仕様に従って `raise NotImplementedError(...)` を実装に置き換えてください。解答例は [solutions/](solutions/) にあります。

```bash
python3 tools/check.py 3.2        # リポジトリのルートで実行
python3 tools/check.py -v 3.2     # 詳しい出力

# 演習ごとに実行する（exercises/ ディレクトリで）
python3 -m unittest -v test_units.TestExercise1Money
python3 -m unittest -v test_typechecker.TestExercise3Check
```

| # | 難易度 | 内容 | 関数・クラス |
|---|---|---|---|
| 1 | ★☆☆ | 通貨付きの金額（通貨の検査、整数倍のみ、合計を保つ分配、誤差のない文字列解析） | `Money` |
| 2 | ★★☆ | 次元付きの物理量（次元の検査と合成、単位換算、マーズ・クライメイト・オービターの再現） | `Quantity` |
| 3 | ★★★ | 小さな言語の型検査器（演算子・if・let・型注釈付きの関数・関数適用・組、分かりやすいエラーメッセージ） | `check` |
| 4 | ★★★ | 発展: 単一化による型推論（型変数、代入、出現検査） | `infer` |
| 5 | ★★☆ | 記述: 不正な状態を表現できない型への設計変更（下記） | — |

演習 3 から始めても構いません。演習 4 は演習 3 と同じ構造で書けますが、「型が等しいか比べる」処理がすべて「単一化する」に置き換わります。型変数の名前は最後に `normalize_type_vars`（与えられた関数）で `'a`, `'b`, … に付け直してから返してください。

### 演習 5（記述）: 注文の状態を型で表す

EC サイトの注文を、次の TypeScript の型で管理しています。

```typescript
interface Order {
  id: string;
  status: string;              // "pending" | "paid" | "shipped" | "cancelled"
  paidAt?: Date;               // 支払い済み以降に設定
  trackingNumber?: string;     // 発送済みのときだけ設定
  cancelReason?: string;       // キャンセル時のみ
  refundedAmount?: number;     // 支払い後のキャンセルで返金したとき
}
```

(1) この型で表現できてしまう「ありえない状態」を 3 つ以上挙げてください。(2) 不正な状態を表現できない型に設計し直してください（TypeScript の判別可能な共用体か、Python のデータクラスの共用体で）。(3) データベースや JSON API でこの設計を表すとき、どのような工夫が必要ですか。

<details>
<summary>解答例</summary>

(1) ありえない状態の例:

- `status` が `"shipped"` なのに `paidAt` も `trackingNumber` もない。
- `status` が `"pending"` なのに `trackingNumber` や `refundedAmount` がある。
- `status` が `"cancelled"` なのに `cancelReason` がない。支払い前にキャンセルしたのに `refundedAmount` がある。
- `status` が `"shiped"`（綴り間違い）や `"PAID"`。
- `refundedAmount` が負の数、または支払額を超えている（金額が `number` なので通貨も分からない）。

(2) 設計例（TypeScript）:

```typescript
type Money = { amount: bigint; currency: "JPY" | "USD" };     // 金額は通貨付き・整数
type OrderId = string & { readonly __brand: "OrderId" };

type Order =
  | { status: "pending"; id: OrderId }
  | { status: "paid"; id: OrderId; paidAt: Date }
  | { status: "shipped"; id: OrderId; paidAt: Date; trackingNumber: string }
  | { status: "cancelled"; id: OrderId; reason: string; refund: Refund };

type Refund =
  | { kind: "none" }                                  // 支払い前のキャンセル
  | { kind: "refunded"; paidAt: Date; amount: Money }; // 支払い後のキャンセル
```

`status` が判別子（discriminant）になり、`switch (order.status)` の各分岐では、その状態に存在するフィールドだけが型として見えます。網羅性検査で、状態を追加したときの修正漏れも見つかります。

(3) データベースでは、状態ごとに必須となる列の組み合わせを CHECK 制約で表す（例: `status = 'shipped'` なら `tracking_number IS NOT NULL`）、または状態ごとの履歴テーブルに分ける方法があります。JSON API では、OpenAPI の `oneOf` と `discriminator` で同じ構造を表し、受信側は境界でスキーマに従って解析します（Parse, don't validate）。状態遷移（pending → paid → shipped など）の規則は型だけでは表しきれないので、遷移を行う関数を 1 か所にまとめ、そこでテストします。

採点の観点: ありえない状態を具体的に挙げられているか、状態ごとに存在するフィールドを分けた直和型になっているか、境界（DB・API）で型の保証をどう保つかまで考えられているか。

</details>

## 理解度チェック

**Q1. Python、JavaScript、C、Rust を「型検査の時期（静的・動的）」と「暗黙の型変換の多さ」の 2 つの軸で分類してください。**

<details>
<summary>解答</summary>

- Python: 動的・暗黙の変換は少ない（`"5" + 2` は TypeError。数値の型の間や `bool` → `int` の変換はある）。
- JavaScript: 動的・暗黙の変換が多い（`"5" - 2` が 3、`"5" + 2` が `"52"`、`0 == ""` が true）。
- C: 静的・暗黙の変換が多い（`int` と `unsigned int` の比較で -1 が大きな正の数になるなど）。
- Rust: 静的・暗黙の変換はほとんどない（数値の型の間でも `as` などで明示が必要）。

静的・動的と、変換の多さは独立した軸であることがポイントです。

</details>

**Q2. `list[Dog]` を `list[Animal]` 型の引数に渡せないのはなぜですか。`Sequence[Dog]` なら渡せるのはなぜですか。**

<details>
<summary>解答</summary>

`list` は書き込み可能なので、`list[Dog]` を `list[Animal]` として渡せると、受け取った関数が `Cat` を追加でき、呼び出し側の犬のリストに猫が混入します。そのため `list` は不変（invariant）です。`Sequence` は読み取り専用のインタフェースなので、要素を追加される心配がなく、犬のリストを「動物を読み出せる列」として扱っても安全です。そのため共変（covariant）になります。Java の配列はこの点で共変にしてしまったため、実行時の `ArrayStoreException` で守る設計になっています。

</details>

**Q3. `Callable[[Animal], Dog]`（動物を受け取り犬を返す関数）は、`Callable[[Dog], Animal]`（犬を受け取り動物を返す関数）が期待される場所で使えますか。理由も答えてください。**

<details>
<summary>解答</summary>

使えます。関数の型は、引数について反変、戻り値について共変です。期待される側は「犬を渡し、動物が返ってくる」ことを前提にしています。実際の関数は動物なら何でも受け取れるので犬も受け取れ（引数は反変）、返すのは犬なので動物として扱えます（戻り値は共変）。したがって安全に代用できます。逆向き（`Callable[[Dog], Animal]` を `Callable[[Animal], Dog]` として使う）は、猫を渡される可能性と、犬以外が返る可能性の両方があるので使えません。

</details>

**Q4. 単一化による型推論で、`fn f => fn x => f x + 1` の型を求めてください。途中の制約も書いてください。**

<details>
<summary>解答</summary>

1. `f : 'a`、`x : 'b` とする。
2. `f x`: `'a` と `'b -> 'c` を単一化 → `'a := 'b -> 'c`。`f x` の型は `'c`。
3. `f x + 1`: `+` の左辺は int なので `'c` と `int` を単一化 → `'c := int`。右辺の `1` は int で問題なし。結果は `int`。
4. 全体は `'a -> 'b -> int` に代入を適用して `('b -> int) -> 'b -> int`。名前を付け直すと **`('a -> int) -> 'a -> int`**。

「int を返す関数と、その関数の引数を受け取り、int を返す」関数で、引数の型は何でもよい（多相）ことが分かります。

</details>

**Q5. `fn x => x x` の型推論が失敗するのはなぜですか。**

<details>
<summary>解答</summary>

`x : 'a` とすると、`x x` は「`x` を `x` に適用する」ので、`'a` と `'a -> 'b` を単一化する必要があります。`'a := 'a -> 'b` とすると、右辺にも `'a` が含まれるため、`'a = ('a -> 'b) -> 'b = (('a -> 'b) -> 'b) -> 'b = …` と無限に展開される型になります。有限の型では表せないので、出現検査（occurs check）で型エラーとします。

</details>

**Q6. 「Parse, don't validate」とは何ですか。`def is_valid_email(s: str) -> bool` と比べて説明してください。**

<details>
<summary>解答</summary>

`is_valid_email` は検証の結果を真偽値で返すだけなので、検証後も値の型は `str` のままです。後続のコードは「この文字列は検証済みか」を型から判断できず、検証し忘れたり、何度も検証したりします。「Parse, don't validate」は、検証と同時に **検証済みであることを表す型の値**（例: `Email` 型、`ServerConfig` 型）に変換し、失敗なら例外や Result で拒否する、という考え方です。システムの境界で一度だけ解析すれば、内部のコードは型によって「検証済み」を前提にでき、検証漏れが型エラーとして見つかるようになります。

</details>

**Q7. TypeScript の型システムが健全でない例を 2 つ挙げ、それぞれの対策を答えてください。**

<details>
<summary>解答</summary>

- 配列の共変: `Dog[]` を `Animal[]` に代入して `Cat` を追加できる。対策は、読み取り専用の `ReadonlyArray<Animal>`（`readonly Animal[]`）を引数の型に使うこと。
- 型アサーション `as` と `any`: 検証せずに任意の型として扱える。対策は、外部データはスキーマに基づく解析（zod など）で型付けし、`as` と `any` をリンタで制限すること。
- 添字アクセス: `nums[0]` が空配列でも `number` として扱われる。対策は `noUncheckedIndexedAccess` を有効にすること。
- メソッド記法の引数の双変: 対策は、関数型のプロパティとして宣言する（`strictFunctionTypes` で反変に検査される）こと。

いずれか 2 つが挙げられていれば正解です。

</details>

## さらに学ぶために

- Benjamin C. Pierce "Types and Programming Languages"（邦訳『型システム入門 プログラミング言語と型の理論』オーム社）— 型付け規則、健全性の証明、型推論、サブタイピングまで、型システムの標準的な教科書。演習 3・4 の理論的な背景がすべて書かれている。
- Luca Cardelli, Peter Wegner "On Understanding Types, Data Abstraction, and Polymorphism"（ACM Computing Surveys, 1985）— ポリモーフィズムの分類を確立した古典論文。
- Alexis King "Parse, don't validate"（2019, ブログ記事）— 境界での解析と、型で検証済みを表す設計を、短く明快に説明している。
- Scott Wlaschin "Domain Modeling Made Functional"（Pragmatic Bookshelf, 2018）— 直和型と「不正な状態を表現できなくする」設計を、業務システムのドメインモデリングに適用する実践書（F# を使用）。
- TypeScript Handbook（公式ドキュメント）— 構造的型付け、判別可能な共用体、`strict` 系のコンパイラオプションの解説。TypeScript を使うなら必読。
- mypy 公式ドキュメント — Protocol、ジェネリクスと変性、段階的な導入方法（既存コードへの型の追加）の解説が実務的。

## まとめ

- 型は **値の集合と許される操作** の組。静的・動的（検査の時期）と、暗黙の型変換の多さは **独立した軸** である。
- 型検査器は **型付け規則** をそのまま再帰関数にしたもの。エラーメッセージの質が使いやすさを決める。
- **Hindley–Milner 型推論** は、型変数を置き、等式の制約を **単一化** で解く。出現検査で無限の型を防ぐ。
- 名前的型付けは宣言で、構造的型付けは形で互換性を決める。ジェネリクスは **読むだけなら共変、書き込むなら不変**、関数の引数は反変。
- **代数的データ型** とパターンマッチの網羅性検査で、「不正な状態を表現できない」型を設計できる。null は型で明示する（Option）。
- ID・金額・物理量は **newtype や単位付きの型** で表し、取り違えを機械的に防ぐ。
- 漸進的型付けは段階的な導入を可能にするが、`any` や `as` の抜け穴があり、TypeScript などは意図的に **健全ではない**。外部データは **境界で解析** する（Parse, don't validate）。
