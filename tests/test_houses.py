import unittest

from strata import Env, World, load, play
from strata.config import ROOT
from strata.worldview import abstract, check
from stratabench.agents import Anyone, Inference

CFG = load(ROOT / "config" / "houses.toml")
SLOTS = {s["name"]: s["values"] for s in CFG["view"]["slots"]}


def short(seed=0):
    return {**CFG, "game": {**CFG["game"], "seed": seed, "lives": 2, "life": 20, "gap": 100}}


class TestHouses(unittest.TestCase):
    def test_four_layers(self):
        w = World(0, SLOTS, **CFG["world"])
        self.assertEqual((w.layers, len(w.villages), len(w.people)), (4, 9, 72))
        for v in w.villages:
            self.assertEqual(len(w.residents[v]), 8)
            houses = {w.parent[p] for p in w.residents[v]}
            self.assertEqual(len(houses), 4)
            self.assertEqual({w.parent[h] for h in houses}, {v})
            self.assertEqual({w.depth[h] for h in houses}, {2})
        for p in w.people:
            self.assertEqual([w.depth[n] for n in w.chain(p)], [0, 1, 2, 3])
        for taus in w.tau.values():                                 # 每往上一层都更慢
            layer = [[t for n, t in enumerate(taus) if w.depth[n] == d] for d in range(4)]
            for lower, upper in zip(layer[1:], layer, strict=False):
                self.assertLess(max(lower), min(upper))
        self.assertRaises(ValueError, World, 0, SLOTS, **{**CFG["world"], "size": [3, 4]})

    def test_family_alike(self):
        """一家人比同村的别家人更像：继承多了一层，证据能在户里传。"""
        w = World(1, SLOTS, **CFG["world"])
        same = other = same_n = other_n = 0
        for _ in range(300):
            w.step()
            for v in w.villages:
                people = w.residents[v]
                for i, a in enumerate(people):
                    for b in people[i + 1:]:
                        agree = sum(w.value(a, s) == w.value(b, s) for s in SLOTS)
                        if w.parent[a] == w.parent[b]:
                            same, same_n = same + agree, same_n + len(SLOTS)
                        else:
                            other, other_n = other + agree, other_n + len(SLOTS)
        self.assertGreater(same / same_n, other / other_n + 0.05)

    def test_text_game(self):
        self.assertEqual(check(CFG["view"]), [])
        self.assertEqual(check(abstract(CFG["view"])), [])
        env = Env(short())
        obs = env.reset()
        self.assertIn("一家人往往一个样", env.instructions)
        stalls = next(line for line in obs.splitlines() if "摊上摆着" in line)
        self.assertEqual(stalls.count("家——"), 4)                   # 一个村四户，一户一户地说
        self.assertEqual(stalls.count("摊上摆着"), 8)
        while not env.done:
            obs, _, info = env.step("继续" if env.life_ended else env.legal_actions()[0])
            self.assertTrue(info["parse_ok"])
        t, w = env.truth(), env.world
        self.assertEqual({n["layer"] for n in t["nodes"].values()}, {"地区", "村", "户", "人"})
        here = {w.parent[p] for p in w.residents[env.game.here]}
        self.assertTrue(all(t["nodes"][h]["layer"] == "户" and t["nodes"][h]["name"].endswith("家") for h in here))

    def test_house_shock(self):
        """四层时变故可以写第三个概率：一户整个换样，消息里说的是这一户。"""
        cfg = short()
        env = Env({**cfg, "world": {**cfg["world"], "shock": [0, 0, 0.05]}})
        obs, lines = env.reset(), []
        while not env.done:
            lines += [line for line in obs.splitlines() if "传来消息" in line]
            obs, _, _ = env.step("继续" if env.life_ended else "不做")
        self.assertTrue(lines)
        self.assertTrue(all("家" in line for line in lines))
        self.assertEqual({env.world.depth[n] for _, n, _, _ in env.world.shocks}, {2})

    def test_baselines_still_ordered(self):
        score = {make: sum(sum(log) for seed in range(3) for log in play(short(seed), make)) for make in (Anyone, Inference)}
        self.assertLess(score[Anyone], score[Inference])


if __name__ == "__main__":
    unittest.main()
