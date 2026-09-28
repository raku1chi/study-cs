"""9.1 ソフトウェアアーキテクチャの基礎 — テスト

実行: python3 tools/check.py 9.1   （またはこのディレクトリで python3 -m unittest -v）
"""
import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

from archcheck import (
    DependencyGraph,
    Rules,
    build_graph,
    check_rules,
    cycle_example,
    find_cycles,
    format_report,
    imports_of,
    layer_of,
    load_rules,
    main,
    module_name,
    resolve_relative,
    run_check,
)

DATA = Path(__file__).parent / "data" / "shop_app"
RULES_PATH = DATA / "rules.json"


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(text), encoding="utf-8")


class TestExercise1Names(unittest.TestCase):
    def test_module_name(self):
        root = Path("/src")
        self.assertEqual(module_name(Path("/src/shop/domain/order.py"), root), "shop.domain.order")
        self.assertEqual(module_name(Path("/src/shop/domain/__init__.py"), root), "shop.domain")
        self.assertEqual(module_name(Path("/src/tool.py"), root), "tool")

    def test_module_name_root_init_is_error(self):
        with self.assertRaises(ValueError):
            module_name(Path("/src/__init__.py"), Path("/src"))

    def test_resolve_relative_from_module(self):
        self.assertEqual(resolve_relative("shop.domain.order", False, 1, "money"), "shop.domain.money")
        self.assertEqual(resolve_relative("shop.domain.order", False, 1, None), "shop.domain")
        self.assertEqual(resolve_relative("shop.domain.order", False, 2, None), "shop")
        self.assertEqual(resolve_relative("shop.domain.order", False, 2, "adapters.db"), "shop.adapters.db")

    def test_resolve_relative_from_package(self):
        # shop/domain/__init__.py の中の "from . import x" は shop.domain.x
        self.assertEqual(resolve_relative("shop.domain", True, 1, "money"), "shop.domain.money")
        self.assertEqual(resolve_relative("shop.domain", True, 2, None), "shop")
        self.assertEqual(resolve_relative("shop", True, 1, "main"), "shop.main")

    def test_resolve_relative_beyond_top_level(self):
        with self.assertRaises(ValueError):
            resolve_relative("shop.domain.order", False, 3, None)
        with self.assertRaises(ValueError):
            resolve_relative("tool", False, 1, "x")  # トップレベルのモジュールには親パッケージがない
        with self.assertRaises(ValueError):
            resolve_relative("shop.domain", True, 0, "x")


class TestExercise2Imports(unittest.TestCase):
    def test_absolute_imports(self):
        src = """
        import os
        import xml.etree.ElementTree as ET
        from collections import OrderedDict, deque
        from shop.domain import order
        from shop.domain.money import *
        """
        self.assertEqual(
            imports_of(textwrap.dedent(src), "shop.app"),
            {"os", "xml.etree.ElementTree", "collections.OrderedDict", "collections.deque",
             "shop.domain.order", "shop.domain.money"},
        )

    def test_relative_imports(self):
        src = "from . import order\nfrom .money import Money\nfrom ..adapters import db\n"
        self.assertEqual(
            imports_of(src, "shop.domain.customer"),
            {"shop.domain.order", "shop.domain.money.Money", "shop.adapters.db"},
        )
        # 同じ文でも、パッケージ（__init__.py）の中では基準が変わる
        self.assertEqual(
            imports_of("from .money import Money\n", "shop.domain", is_package=True),
            {"shop.domain.money.Money"},
        )

    def test_nested_imports_are_found(self):
        src = """
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            from shop.adapters.db import Database
        try:
            import ujson as json_impl
        except ImportError:
            import json as json_impl
        class Service:
            def run(self):
                from shop.main import app_config
                return app_config()
        """
        found = imports_of(textwrap.dedent(src), "shop.application.service")
        for name in ("typing.TYPE_CHECKING", "shop.adapters.db.Database", "ujson", "json", "shop.main.app_config"):
            self.assertIn(name, found)

    def test_imports_inside_strings_and_comments_are_ignored(self):
        src = 'text = "import secret_module"\n# import commented_out\nimport real\n'
        self.assertEqual(imports_of(src, "m"), {"real"})

    def test_future_import_is_not_a_dependency(self):
        self.assertEqual(imports_of("from __future__ import annotations\nimport os\n", "m"), {"os"})

    def test_syntax_error_propagates(self):
        with self.assertRaises(SyntaxError):
            imports_of("def broken(:\n", "m")


class TestExercise3Graph(unittest.TestCase):
    def setUp(self):
        self.graph = build_graph(DATA)

    def test_all_modules_are_keys(self):
        expected = {
            "shop", "shop.main", "shop.legacy_helpers",
            "shop.domain", "shop.domain.money", "shop.domain.order", "shop.domain.customer",
            "shop.domain.pricing", "shop.application", "shop.application.place_order",
            "shop.adapters", "shop.adapters.db", "shop.adapters.web",
        }
        self.assertEqual(set(self.graph.internal), expected)
        self.assertEqual(set(self.graph.external), expected)

    def test_internal_edges(self):
        g = self.graph.internal
        self.assertEqual(g["shop.domain.order"], {"shop.domain.money", "shop.domain.customer"})
        self.assertEqual(g["shop.domain.customer"], {"shop.domain.order"})
        self.assertEqual(g["shop.domain"], {"shop.domain.money"})
        self.assertEqual(g["shop.domain.money"], set())
        self.assertEqual(
            g["shop.application.place_order"],
            {"shop.domain.order", "shop.domain.pricing", "shop.domain.money",
             "shop.legacy_helpers", "shop.adapters.db"},
        )
        self.assertEqual(g["shop.main"], {"shop.adapters.db", "shop.adapters.web", "shop.application.place_order"})
        self.assertEqual(g["shop.adapters.web"], {"shop.application.place_order", "shop.main"})

    def test_external_dependencies(self):
        ext = self.graph.external
        self.assertEqual(ext["shop.domain.pricing"], {"sqlite3"})
        self.assertEqual(ext["shop.adapters.db"], {"sqlite3"})
        self.assertEqual(ext["shop.adapters.web"], {"json"})
        self.assertEqual(ext["shop.application.place_order"], {"typing"})
        self.assertEqual(ext["shop.domain.money"], {"dataclasses"})

    def test_no_self_edges(self):
        for m, targets in self.graph.internal.items():
            self.assertNotIn(m, targets, m)

    def test_skips_pycache_and_hidden_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(root, {
                "app/__init__.py": "",
                "app/core.py": "import app.util\nfrom app.util import helper\n",
                "app/util.py": "import os.path\n",
                "app/__pycache__/junk.py": "import nothing\n",
                "app/.hidden/secret.py": "import nothing\n",
            })
            g = build_graph(root)
            self.assertEqual(set(g.internal), {"app", "app.core", "app.util"})
            self.assertEqual(g.internal["app.core"], {"app.util"})
            self.assertEqual(g.external["app.util"], {"os"})


def fixture_rules() -> Rules:
    return load_rules(RULES_PATH)


class TestExercise4Rules(unittest.TestCase):
    def test_layer_of_uses_dot_boundaries(self):
        rules = Rules.from_dict({
            "layers": {"domain": "shop.domain", "domain_events": "shop.domain.events", "app": "shop.app"},
            "allowed": {},
        })
        self.assertEqual(layer_of("shop.domain", rules), "domain")
        self.assertEqual(layer_of("shop.domain.order", rules), "domain")
        self.assertEqual(layer_of("shop.domain.events.placed", rules), "domain_events")  # 最長一致
        self.assertIsNone(layer_of("shop.domainx", rules))
        self.assertIsNone(layer_of("shop", rules))

    def test_fixture_violations(self):
        violations = check_rules(build_graph(DATA), fixture_rules())
        got = [(v.kind, v.source, v.target) for v in violations]
        self.assertEqual(got, [
            ("external", "shop.domain.pricing", "sqlite3"),
            ("layer", "shop.adapters.web", "shop.main"),
            ("layer", "shop.application.place_order", "shop.adapters.db"),
            ("layer", "shop.domain.pricing", "shop.adapters.db"),
            ("unassigned", "shop.legacy_helpers", ""),
        ])
        for v in violations:
            self.assertTrue(v.message, "message には人が読める説明を入れる")

    def test_same_layer_and_allowed_dependencies_pass(self):
        rules = Rules.from_dict({
            "layers": {"domain": "p.domain", "app": "p.app"},
            "allowed": {"app": ["domain"]},
        })
        graph = DependencyGraph(
            internal={"p.domain.a": {"p.domain.b"}, "p.domain.b": set(), "p.app.x": {"p.domain.a"}},
            external={"p.domain.a": set(), "p.domain.b": set(), "p.app.x": set()},
        )
        self.assertEqual(check_rules(graph, rules), [])

    def test_ignore_and_unassigned(self):
        rules = Rules.from_dict({
            "layers": {"domain": "p.domain"}, "allowed": {}, "ignore": ["p"],
        })
        graph = DependencyGraph(
            internal={"p": {"p.domain.a"}, "p.domain.a": {"p.misc"}, "p.misc": set()},
            external={"p": set(), "p.domain.a": set(), "p.misc": set()},
        )
        got = [(v.kind, v.source) for v in check_rules(graph, rules)]
        # p は ignore、p.misc は unassigned（p.domain.a → p.misc の辺は layer 違反としては報告しない）
        self.assertEqual(got, [("unassigned", "p.misc")])

    def test_forbidden_external_is_per_layer(self):
        rules = Rules.from_dict({
            "layers": {"domain": "p.domain", "infra": "p.infra"},
            "allowed": {"infra": ["domain"]},
            "forbidden_external": {"domain": ["sqlite3"]},
        })
        graph = DependencyGraph(
            internal={"p.domain.a": set(), "p.infra.db": {"p.domain.a"}},
            external={"p.domain.a": {"sqlite3", "json"}, "p.infra.db": {"sqlite3"}},
        )
        got = [(v.kind, v.source, v.target) for v in check_rules(graph, rules)]
        self.assertEqual(got, [("external", "p.domain.a", "sqlite3")])


class TestExercise5Cycles(unittest.TestCase):
    def test_fixture_cycles(self):
        self.assertEqual(find_cycles(build_graph(DATA).internal), [
            ["shop.adapters.db", "shop.domain.pricing"],
            ["shop.adapters.web", "shop.main"],
            ["shop.domain.customer", "shop.domain.order"],
        ])

    def test_dag_has_no_cycles(self):
        edges = {"a": {"b", "c"}, "b": {"d"}, "c": {"d"}, "d": set()}
        self.assertEqual(find_cycles(edges), [])

    def test_multiple_components_and_nodes_only_as_targets(self):
        edges = {"a": {"b"}, "b": {"c"}, "c": {"a", "x"}, "x": {"y"}, "y": {"x", "z"}}
        self.assertEqual(find_cycles(edges), [["a", "b", "c"], ["x", "y"]])

    def test_self_loop_is_a_cycle(self):
        self.assertEqual(find_cycles({"a": {"a"}, "b": {"a"}}), [["a"]])

    def test_large_cycle_does_not_hit_recursion_limit(self):
        n = 3000
        names = [f"m{i:04d}" for i in range(n)]
        edges = {names[i]: {names[(i + 1) % n]} for i in range(n)}
        cycles = find_cycles(edges)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(len(cycles[0]), n)

    def test_cycle_example_simple(self):
        edges = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
        self.assertEqual(cycle_example(edges, ["c", "a", "b"]), ["a", "b", "c", "a"])
        self.assertEqual(cycle_example({"a": {"a"}}, ["a"]), ["a", "a"])

    def test_cycle_example_is_shortest_and_stays_inside(self):
        # a → b → a（長さ2）と a → c → d → a（長さ3）。a → z は成分の外
        edges = {"a": {"z", "c", "b"}, "b": {"a"}, "c": {"d"}, "d": {"a"}, "z": set()}
        self.assertEqual(cycle_example(edges, ["a", "b", "c", "d"]), ["a", "b", "a"])

    def test_cycle_example_is_valid_path_for_fixture(self):
        graph = build_graph(DATA).internal
        for members in find_cycles(graph):
            path = cycle_example(graph, members)
            self.assertEqual(path[0], min(members))
            self.assertEqual(path[0], path[-1])
            for a, b in zip(path, path[1:]):
                self.assertIn(b, graph[a], f"{a} → {b} は存在しない辺です")
                self.assertIn(b, members)

    def test_cycle_example_errors(self):
        with self.assertRaises(ValueError):
            cycle_example({"a": {"b"}}, [])
        with self.assertRaises(ValueError):
            cycle_example({"a": {"b"}, "b": set()}, ["a", "b"])


class TestExercise6Cli(unittest.TestCase):
    def test_run_check_on_fixture(self):
        report = run_check(DATA, fixture_rules())
        self.assertFalse(report.ok)
        self.assertEqual(len(report.violations), 5)
        self.assertEqual(len(report.cycles), 3)

    def test_format_report(self):
        report = run_check(DATA, fixture_rules())
        text = format_report(report, build_graph(DATA).internal)
        self.assertIn("[layer] ", text)
        self.assertIn("[unassigned] ", text)
        self.assertIn("[cycle] shop.domain.customer → shop.domain.order → shop.domain.customer", text)
        self.assertEqual(text.splitlines()[-1], "NG: 違反 5 件 / 循環 3 件")
        self.assertIn("[cycle] shop.adapters.web, shop.main", format_report(report))

    def test_main_exit_codes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main([str(DATA), str(RULES_PATH)]), 1)
        self.assertIn("NG:", out.getvalue())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(root, {
                "clean/__init__.py": "",
                "clean/domain/__init__.py": "",
                "clean/domain/model.py": "from dataclasses import dataclass\n",
                "clean/app/__init__.py": "",
                "clean/app/service.py": "from clean.domain.model import dataclass\n",
                "rules.json": '{"layers": {"domain": "clean.domain", "app": "clean.app"},'
                              ' "allowed": {"app": ["domain"]}, "ignore": ["clean"]}',
            })
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([str(root), str(root / "rules.json")]), 0)
            self.assertIn("OK", out.getvalue())

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(main([]), 2)


if __name__ == "__main__":
    unittest.main()
