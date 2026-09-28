"""5.1 階層モデルとIP — テスト（ipnet）

実行: python3 tools/check.py 5.1   （またはこのディレクトリで python3 -m unittest -v）

答え合わせの「正解」として、テストの中でだけ標準ライブラリの ipaddress を使っています。
"""
import ipaddress
import random
import unittest

from ipnet import (
    Network,
    RoutingTable,
    aggregate,
    format_ipv4,
    netmask_to_prefix,
    parse_ipv4,
    plan_vpc,
    prefix_to_netmask,
    subnet_prefix_for_hosts,
)

N = Network.parse


def random_network(rng: random.Random, min_prefix: int = 0) -> Network:
    prefix = rng.randrange(min_prefix, 33)
    address = rng.getrandbits(32) & prefix_to_netmask(prefix)
    return Network(address, prefix)


class TestExercise1Addresses(unittest.TestCase):
    def test_parse_examples(self):
        self.assertEqual(parse_ipv4("0.0.0.0"), 0)
        self.assertEqual(parse_ipv4("255.255.255.255"), 2**32 - 1)
        self.assertEqual(parse_ipv4("192.168.1.10"), 0xC0A8010A)
        self.assertEqual(parse_ipv4("10.0.0.1"), 0x0A000001)

    def test_parse_matches_ipaddress(self):
        rng = random.Random(51)
        for _ in range(500):
            value = rng.getrandbits(32)
            text = str(ipaddress.IPv4Address(value))
            self.assertEqual(parse_ipv4(text), value, text)

    def test_parse_rejects_invalid(self):
        bad = [
            "", "1.2.3", "1.2.3.4.5", "256.0.0.1", "1.2.3.-4", "1..2.3", "a.b.c.d",
            "1.2.3.4 ", " 1.2.3.4", "01.2.3.4", "1.2.3.04", "1.2.3.0x4", "+1.2.3.4",
            "1.2.3.4/24", "１.2.3.4", "1.2.3.²", "1000.1.1.1",
        ]
        for text in bad:
            with self.assertRaises(ValueError, msg=repr(text)):
                parse_ipv4(text)

    def test_format(self):
        self.assertEqual(format_ipv4(0), "0.0.0.0")
        self.assertEqual(format_ipv4(0xC0A8010A), "192.168.1.10")
        self.assertEqual(format_ipv4(2**32 - 1), "255.255.255.255")
        rng = random.Random(52)
        for _ in range(500):
            value = rng.getrandbits(32)
            self.assertEqual(format_ipv4(value), str(ipaddress.IPv4Address(value)))
            self.assertEqual(parse_ipv4(format_ipv4(value)), value)
        for bad in (-1, 2**32):
            with self.assertRaises(ValueError, msg=str(bad)):
                format_ipv4(bad)

    def test_prefix_and_netmask(self):
        for prefix in range(33):
            expected = int(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)
            self.assertEqual(prefix_to_netmask(prefix), expected, prefix)
            self.assertEqual(netmask_to_prefix(expected), prefix, prefix)
        self.assertEqual(prefix_to_netmask(24), 0xFFFFFF00)
        for bad in (-1, 33):
            with self.assertRaises(ValueError):
                prefix_to_netmask(bad)

    def test_non_contiguous_netmask_is_rejected(self):
        for mask in ("255.0.255.0", "255.255.255.1", "0.255.255.255", "255.255.254.255"):
            with self.assertRaises(ValueError, msg=mask):
                netmask_to_prefix(parse_ipv4(mask))


class TestExercise2Network(unittest.TestCase):
    def test_parse_and_str(self):
        net = N("192.168.10.0/24")
        self.assertEqual((net.address, net.prefix), (0xC0A80A00, 24))
        self.assertEqual(str(net), "192.168.10.0/24")
        self.assertEqual(str(N("10.0.0.1")), "10.0.0.1/32", "「/」がなければ /32")
        self.assertEqual(str(N("0.0.0.0/0")), "0.0.0.0/0")

    def test_strict_host_bits(self):
        with self.assertRaises(ValueError, msg="ホスト部に 1 がある"):
            N("192.168.10.5/24")
        self.assertEqual(str(N("192.168.10.5/24", strict=False)), "192.168.10.0/24")
        with self.assertRaises(ValueError):
            Network(0x0A000001, 8)

    def test_parse_rejects_invalid(self):
        for text in ("10.0.0.0/33", "10.0.0.0/-1", "10.0.0.0/", "10.0.0.0/a", "10.0.0/8", "10.0.0.0/8/8"):
            with self.assertRaises(ValueError, msg=text):
                N(text)

    def test_properties(self):
        net = N("172.16.0.0/12")
        self.assertEqual(format_ipv4(net.netmask), "255.240.0.0")
        self.assertEqual(format_ipv4(net.broadcast), "172.31.255.255")
        self.assertEqual(net.num_addresses, 2**20)
        self.assertEqual(net.host_count, 2**20 - 2)

    def test_host_count_edge_cases(self):
        self.assertEqual(N("10.0.0.0/24").host_count, 254)
        self.assertEqual(N("10.0.0.0/30").host_count, 2)
        self.assertEqual(N("10.0.0.0/31").host_count, 2, "RFC 3021: /31 は 2 点間リンクで 2 台とも使える")
        self.assertEqual(N("10.0.0.7/32").host_count, 1)
        self.assertEqual(N("0.0.0.0/0").host_count, 2**32 - 2)

    def test_properties_match_ipaddress(self):
        rng = random.Random(53)
        for _ in range(500):
            net = random_network(rng)
            ref = ipaddress.IPv4Network(str(net))
            self.assertEqual(net.netmask, int(ref.netmask), str(net))
            self.assertEqual(net.broadcast, int(ref.broadcast_address), str(net))
            self.assertEqual(net.num_addresses, ref.num_addresses, str(net))

    def test_contains(self):
        net = N("10.1.0.0/16")
        self.assertTrue(net.contains(parse_ipv4("10.1.0.0")))
        self.assertTrue(net.contains(parse_ipv4("10.1.255.255")))
        self.assertFalse(net.contains(parse_ipv4("10.2.0.0")))
        self.assertFalse(net.contains(parse_ipv4("10.0.255.255")))
        self.assertTrue(N("0.0.0.0/0").contains(parse_ipv4("203.0.113.9")))
        rng = random.Random(54)
        for _ in range(500):
            net = random_network(rng, min_prefix=8)
            addr = rng.getrandbits(32) if rng.random() < 0.5 else net.address | rng.getrandbits(32 - net.prefix)
            ref = ipaddress.IPv4Address(addr) in ipaddress.IPv4Network(str(net))
            self.assertEqual(net.contains(addr), ref, (str(net), format_ipv4(addr)))

    def test_overlaps(self):
        self.assertTrue(N("10.0.0.0/8").overlaps(N("10.20.0.0/16")))
        self.assertTrue(N("10.20.0.0/16").overlaps(N("10.0.0.0/8")))
        self.assertFalse(N("10.0.0.0/16").overlaps(N("10.1.0.0/16")))
        self.assertTrue(N("172.31.0.0/16").overlaps(N("172.31.0.0/16")))
        rng = random.Random(55)
        for _ in range(1000):
            a, b = random_network(rng, 4), random_network(rng, 4)
            if rng.random() < 0.5:  # 重なる組を作りやすくする
                b = Network(a.address & prefix_to_netmask(min(a.prefix, b.prefix)) & b.netmask, b.prefix)
            ref = ipaddress.IPv4Network(str(a)).overlaps(ipaddress.IPv4Network(str(b)))
            self.assertEqual(a.overlaps(b), ref, (str(a), str(b)))

    def test_subnet_of(self):
        self.assertTrue(N("10.1.2.0/24").subnet_of(N("10.1.0.0/16")))
        self.assertTrue(N("10.1.0.0/16").subnet_of(N("10.1.0.0/16")))
        self.assertFalse(N("10.1.0.0/16").subnet_of(N("10.1.2.0/24")))
        self.assertFalse(N("10.2.0.0/24").subnet_of(N("10.1.0.0/16")))

    def test_subnets(self):
        self.assertEqual(
            [str(s) for s in N("10.0.0.0/24").subnets(26)],
            ["10.0.0.0/26", "10.0.0.64/26", "10.0.0.128/26", "10.0.0.192/26"],
        )
        self.assertEqual([str(s) for s in N("10.0.0.0/24").subnets(24)], ["10.0.0.0/24"])
        self.assertEqual(len(N("10.0.0.0/16").subnets(24)), 256)
        for bad in (23, 33):
            with self.assertRaises(ValueError, msg=str(bad)):
                N("10.0.0.0/24").subnets(bad)

    def test_aggregate_examples(self):
        def agg(*cidrs):
            return [str(n) for n in aggregate([N(c) for c in cidrs])]

        self.assertEqual(agg("10.0.0.0/25", "10.0.0.128/25"), ["10.0.0.0/24"])
        self.assertEqual(agg("10.0.1.0/24", "10.0.2.0/24"), ["10.0.1.0/24", "10.0.2.0/24"],
                         "隣接していても親の境界にそろっていなければ併合できない")
        self.assertEqual(agg("10.0.0.0/24", "10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"), ["10.0.0.0/22"])
        self.assertEqual(agg("10.0.0.0/8", "10.20.0.0/16", "10.0.0.0/8"), ["10.0.0.0/8"], "重複と包含は取り除く")
        self.assertEqual(agg("10.0.0.0/25", "10.0.0.128/26", "10.0.0.192/26"), ["10.0.0.0/24"], "併合は連鎖する")
        self.assertEqual(agg("192.168.1.0/24", "10.0.0.0/8"), ["10.0.0.0/8", "192.168.1.0/24"], "アドレス順に並べる")
        self.assertEqual(agg("0.0.0.0/1", "128.0.0.0/1"), ["0.0.0.0/0"])
        self.assertEqual(agg(), [])

    def test_aggregate_matches_collapse_addresses(self):
        rng = random.Random(56)
        for _ in range(400):
            nets = []
            for _ in range(rng.randrange(1, 16)):
                prefix = rng.randrange(20, 33)
                addr = (0x0A000000 | rng.getrandbits(12) << 8 | rng.getrandbits(8)) & prefix_to_netmask(prefix)
                nets.append(Network(addr, prefix))
            ref = ipaddress.collapse_addresses(ipaddress.IPv4Network(str(n)) for n in nets)
            self.assertEqual([str(n) for n in aggregate(nets)], [str(r) for r in ref], [str(n) for n in nets])


class TestExercise3RoutingTable(unittest.TestCase):
    def setUp(self):
        self.table = RoutingTable()
        self.table.add("0.0.0.0/0", "isp")
        self.table.add("10.0.0.0/8", "corp")
        self.table.add("10.1.0.0/16", "tokyo")
        self.table.add("10.1.2.0/24", "tokyo-db")
        self.table.add("10.1.2.3/32", "special")

    def hop(self, address):
        route = self.table.lookup(address)
        return None if route is None else route[1]

    def test_longest_prefix_wins(self):
        self.assertEqual(self.hop("10.1.2.3"), "special")
        self.assertEqual(self.hop("10.1.2.4"), "tokyo-db")
        self.assertEqual(self.hop("10.1.3.4"), "tokyo")
        self.assertEqual(self.hop("10.200.0.1"), "corp")
        self.assertEqual(self.hop("8.8.8.8"), "isp", "どれにも一致しなければデフォルトルート")

    def test_lookup_returns_matched_route(self):
        self.assertEqual(self.table.lookup("10.1.9.9"), (N("10.1.0.0/16"), "tokyo"))

    def test_no_default_route(self):
        table = RoutingTable()
        table.add("192.168.0.0/16", "lan")
        self.assertIsNone(table.lookup("8.8.8.8"))
        self.assertEqual(len(table), 1)

    def test_replace_and_remove(self):
        self.table.add("10.1.0.0/16", "osaka")  # 同じ宛先は上書き
        self.assertEqual(self.hop("10.1.3.4"), "osaka")
        self.assertEqual(len(self.table), 5)
        self.table.remove("10.1.0.0/16")
        self.assertEqual(self.hop("10.1.3.4"), "corp")
        with self.assertRaises(KeyError):
            self.table.remove("10.1.0.0/16")
        with self.assertRaises(ValueError):
            self.table.add("10.1.2.3/24", "x")  # ホスト部に 1 がある

    def test_routes_are_sorted(self):
        routes = [(str(n), hop) for n, hop in self.table.routes()]
        self.assertEqual(routes[0], ("0.0.0.0/0", "isp"))
        self.assertEqual(len(routes), 5)

    def test_matches_brute_force(self):
        rng = random.Random(57)
        table = RoutingTable()
        routes = {}
        for i in range(300):
            prefix = rng.choice([8, 12, 16, 20, 22, 24, 26, 28, 32])
            net = Network((0x0A000000 | rng.getrandbits(24)) & prefix_to_netmask(prefix), prefix)  # 10.0.0.0/8 の中
            routes[str(net)] = f"hop{i}"  # 同じ宛先が再び出たら上書き（テーブル側も上書きされる）
            table.add(str(net), f"hop{i}")
        refs = [(ipaddress.IPv4Network(c), h) for c, h in routes.items()]
        for _ in range(500):
            addr = ipaddress.IPv4Address(0x0A000000 | rng.getrandbits(24) if rng.random() < 0.9 else rng.getrandbits(32))
            matches = [(net.prefixlen, h) for net, h in refs if addr in net]
            expected = max(matches)[1] if matches else None
            route = table.lookup(str(addr))
            self.assertEqual(None if route is None else route[1], expected, str(addr))


class TestExercise4VpcPlanner(unittest.TestCase):
    AZS = ["ap-northeast-1a", "ap-northeast-1c", "ap-northeast-1d"]

    def test_subnet_prefix_for_hosts(self):
        self.assertEqual(subnet_prefix_for_hosts(251), 24, "251 + 予約 5 = 256 → /24")
        self.assertEqual(subnet_prefix_for_hosts(252), 23)
        self.assertEqual(subnet_prefix_for_hosts(1000), 22)
        self.assertEqual(subnet_prefix_for_hosts(1), 28, "小さすぎるサブネットは /28 に切り上げる")
        self.assertEqual(subnet_prefix_for_hosts(254, reserved_per_subnet=2), 24)
        self.assertEqual(subnet_prefix_for_hosts(1, reserved_per_subnet=0, smallest_prefix=32), 32)
        with self.assertRaises(ValueError):
            subnet_prefix_for_hosts(0)

    def test_example_plan(self):
        plan = plan_vpc("10.0.0.0/16", self.AZS, [("public", 200), ("app", 1000), ("db", 50)])
        got = {tier: {az: str(net) for az, net in subnets.items()} for tier, subnets in plan.items()}
        self.assertEqual(got, {
            "public": {"ap-northeast-1a": "10.0.12.0/24", "ap-northeast-1c": "10.0.13.0/24", "ap-northeast-1d": "10.0.14.0/24"},
            "app": {"ap-northeast-1a": "10.0.0.0/22", "ap-northeast-1c": "10.0.4.0/22", "ap-northeast-1d": "10.0.8.0/22"},
            "db": {"ap-northeast-1a": "10.0.15.0/26", "ap-northeast-1c": "10.0.15.64/26", "ap-northeast-1d": "10.0.15.128/26"},
        })
        self.assertEqual(list(plan), ["public", "app", "db"], "戻り値の階層は入力の順序")
        self.assertEqual(list(plan["db"]), self.AZS, "AZ も入力の順序")

    def test_random_plans_are_valid(self):
        rng = random.Random(58)
        for _ in range(200):
            vpc = N(f"10.{rng.randrange(256)}.0.0/16", strict=False)
            azs = [f"az{i}" for i in range(rng.randrange(1, 5))]
            tiers = [(f"t{i}", rng.choice([1, 10, 27, 100, 250, 500, 2000, 4000])) for i in range(rng.randrange(1, 5))]
            sizes = [len(azs) * N(f"0.0.0.0/{subnet_prefix_for_hosts(h)}").num_addresses for _, h in tiers]
            try:
                plan = plan_vpc(str(vpc), azs, tiers)
            except ValueError:
                self.assertGreater(sum(sizes), vpc.num_addresses, "合計が VPC に収まるなら割り当てに成功すること")
                continue
            subnets = [(name, hosts, plan[name][az]) for name, hosts in tiers for az in azs]
            for name, hosts, net in subnets:
                self.assertTrue(net.subnet_of(vpc), f"{net} は VPC {vpc} の内側")
                self.assertGreaterEqual(net.num_addresses - 5, hosts, f"{name}: {net}")
                self.assertEqual(net.prefix, subnet_prefix_for_hosts(hosts), "必要最小限の大きさ")
            nets = [net for _, _, net in subnets]
            for i in range(len(nets)):
                for j in range(i + 1, len(nets)):
                    self.assertFalse(nets[i].overlaps(nets[j]), f"{nets[i]} と {nets[j]} が重なっている")

    def test_not_enough_space(self):
        with self.assertRaises(ValueError):
            plan_vpc("10.0.0.0/24", self.AZS, [("app", 100)])  # /25 × 3 は /24 に入らない
        with self.assertRaises(ValueError):
            plan_vpc("10.0.0.0/24", ["a"], [("big", 1000)])  # /22 は /24 より大きい
        plan = plan_vpc("10.0.0.0/24", ["a", "b"], [("app", 100)])  # /25 × 2 はちょうど入る
        self.assertEqual([str(n) for n in plan["app"].values()], ["10.0.0.0/25", "10.0.0.128/25"])

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            plan_vpc("10.0.0.0/16", [], [("app", 10)])
        with self.assertRaises(ValueError):
            plan_vpc("10.0.0.0/16", ["a", "a"], [("app", 10)])
        with self.assertRaises(ValueError):
            plan_vpc("10.0.0.0/16", ["a"], [("app", 10), ("app", 20)])
        with self.assertRaises(ValueError):
            plan_vpc("10.0.0.1/16", ["a"], [("app", 10)])


if __name__ == "__main__":
    unittest.main()
