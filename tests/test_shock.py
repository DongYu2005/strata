import unittest

from strata import Env, Game, World, load
from strata.config import ROOT

CFG = load()
SLOTS = {s["name"]: s["values"] for s in CFG["view"]["slots"]}


def world(seed=0, shock=(0.01, 0.02)):
    return World(seed, SLOTS, **{**CFG["world"], "shock": shock})


def config(seed=0, shock=(0.01, 0.05), **game):
    return {**CFG, "world": {**CFG["world"], "shock": list(shock)},
            "game": {**CFG["game"], "seed": seed, "lives": 3, "life": 30, "gap": 50, **game}}


def heard(cfg, far: bool):
    """玩一局，返回（听到的变故，活着的那些世界日，世界）。far：每天都翻山去别的地区。"""
    said, alive = [], set()
    game = Game(cfg, say=lambda kind, **kw: said.append((kw["day"], kw["node"], kw["slot"], kw["value"], game.world.day))
                if kind == "shock" else None)
    ask = game.start()
    while ask is not None:
        alive.add(ask.day)
        if ask.kind == "go":
            answer = next(v for v in game.world.villages if game.world.distance(ask.here, v)) if far else ask.here
        else:
            answer = None
        ask = game.step(answer)
    return said, alive, game.world


class TestShock(unittest.TestCase):
    def test_off_by_default(self):
        w = World(0, SLOTS, **CFG["world"])
        for _ in range(500):
            w.step()
        self.assertEqual(w.shocks, [])

    def test_everyone_below_follows(self):
        """出变故那天：这个节点换成一个新值，底下所有节点都随它；since 记下真变了的那些。"""
        w, seen = world(), 0
        for _ in range(600):
            before = {s: [w.value(n, s) for n in range(len(w.depth))] for s in SLOTS}
            w.step()
            today, seen = w.shocks[seen:], len(w.shocks)
            for day, n, s, v in today:
                self.assertEqual(day, w.day)
                self.assertLess(w.depth[n], 2)                  # 只有地区和村出变故
                if sum(x[2] == s for x in today) > 1:
                    continue                                    # 同一天同一样特质出了两回，可能上下两层撞上，不查
                self.assertNotEqual(before[s][n], v)
                self.assertEqual({w.value(m, s) for m in w.below[n]}, {v})
                self.assertTrue(all(w.source(m, s) == n for m in w.below[n]))
                for m in w.below[n]:
                    if before[s][m] != v:
                        self.assertEqual(w.since[s][m], day)
        self.assertGreater(len(w.shocks), 20)
        self.assertEqual({w.depth[n] for _, n, _, _ in w.shocks}, {0, 1})
        self.assertEqual({s for _, _, s, _ in w.shocks}, set(SLOTS))

    def test_fixed_by_seed_day_node(self):
        def when(seed, shock):
            w = world(seed, shock)
            for _ in range(400):
                w.step()
            return w.shocks

        self.assertEqual(when(1, (0.01, 0.02)), when(1, (0.01, 0.02)))
        self.assertNotEqual(when(1, (0.01, 0.02)), when(2, (0.01, 0.02)))
        rare = {(day, n) for day, n, _, _ in when(1, (0.005, 0.01))}
        often = {(day, n) for day, n, _, _ in when(1, (0.02, 0.04))}
        self.assertTrue(rare and rare < often)                  # 调大概率只会多出几回，原来的那几回还在

    def test_news_reaches_the_living_same_day(self):
        """活着的每一天出的变故，当天听到、只听到一次，走法不影响；死后那些天出的，没人告诉。"""
        for far in (False, True):
            said, alive, w = heard(config(), far)
            self.assertTrue(all(day == today for day, *_, today in said))
            self.assertEqual([x[:4] for x in said], [x for x in w.shocks if x[0] in alive])
            self.assertTrue(said)
            self.assertTrue(any(x[0] not in alive for x in w.shocks))

    def test_text(self):
        cfg = load(ROOT / "config" / "shock.toml")
        self.assertEqual(cfg["world"]["shock"], [0.002, 0.01])
        env = Env(config(shock=(0.05, 0.1)))
        obs, lines = env.reset(), []
        while not env.done:
            lines += [line for line in obs.splitlines() if "传来消息" in line]
            obs, _, _ = env.step("继续" if env.life_ended else "不做")
        self.assertTrue(lines)
        places = set(env.view.pools["region"]) | set(env.view.pools["village"])
        self.assertTrue(all(any(p in line for p in places) for line in lines))
        for path in (None, ROOT / "config" / "more-memory.toml"):    # 两份世界观：每样特质都得有一句变故的台词
            view = load(path)["view"]
            self.assertEqual(set(view["lines"]["shock"]), {s["name"] for s in view["slots"]})


if __name__ == "__main__":
    unittest.main()
