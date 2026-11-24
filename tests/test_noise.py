import unittest

from strata import Env, Game, load, play
from strata.config import ROOT
from stratabench.agents import Oracle

CFG = load()


def config(noise, seed=0, **game):
    return {**CFG, "game": {**CFG["game"], "seed": seed, "lives": 2, "life": 30, "gap": 100, "noise": noise, **game}}


def deals(cfg):
    """留在原地、每天找第一个卖这样货的人。记下每一单：(验出来的, 本性, 成没成)。"""
    out, events = [], []
    game = Game(cfg, say=lambda kind, **kw: events.append((kind, kw)))
    ask = game.start()
    while ask is not None:
        answer, nature = None, None
        if ask.kind == "go":
            answer = ask.here
        elif ask.kind == "choose":
            answer = next((p for p, seen in ask.stalls.items() if all(seen[s] == ask.want[s] for s in seen)), None)
            nature = answer is not None and {s: game.world.value(answer, s) for s in game.hidden}
        before = len(events)
        ask = game.step(answer)
        out += [({s: kw[s] for s in game.hidden}, nature, kind == "done")
                for kind, kw in events[before:] if kind in ("done", "fail")]
    return out, game


def slips(cfg, deal: bool):
    """逐日走完一局，记下每天每个人会不会失手。deal：每天做一单，还是天天不做。"""
    out, game = set(), Game(cfg)
    ask = game.start()
    while ask is not None:
        if ask.kind != "death":
            out |= {(ask.day, p) for p in game.world.people
                    if game.shown(p) != {s: game.world.value(p, s) for s in game.hidden}}
        answer = ask.here if ask.kind == "go" else next(iter(ask.stalls)) if ask.kind == "choose" and deal else None
        ask = game.step(answer)
    return out, game


class TestNoise(unittest.TestCase):
    def test_no_noise_shows_nature(self):
        """noise = 0：验出来的就是本性。（各基线成绩不变由 test_env 的指纹查。）"""
        got, _ = deals(config(0))
        self.assertTrue(got)
        self.assertTrue(all(seen == nature for seen, nature, _ in got))
        unset = {**CFG, "game": {k: v for k, v in config(0)["game"].items() if k != "noise"}}
        self.assertEqual(play(unset, Oracle), play(config(0), Oracle))      # 不写 noise 等于 0

    def test_always_slips(self):
        """noise = 1：每一单都和本性相反，全知也一单做不成。"""
        got, _ = deals(config(1))
        self.assertTrue(got)
        self.assertTrue(all(seen[s] != nature[s] for seen, nature, _ in got for s in seen))
        self.assertEqual(sum(map(sum, play(config(1), Oracle))), 0)

    def test_outcome_follows_what_is_shown(self):
        """成不成、记进成绩的、说出来的，都按这一回的表现。"""
        got, game = deals(config(0.3, life=60))
        want = {s["name"]: s["values"][0] for s in game.slots if not s["visible"]}
        self.assertEqual([seen == want for seen, _, _ in got], [ok for *_, ok in got])
        self.assertEqual(sum(ok for *_, ok in got), sum(map(sum, game.lives)))
        self.assertTrue(any(seen != nature for seen, nature, _ in got))     # 真有失手
        self.assertTrue(any(seen == nature for seen, nature, _ in got))

    def test_slips_fixed_by_seed_day_person(self):
        """哪天谁失手和走法无关：天天做单和天天不做，看到的失手一模一样；换 seed 才换。"""
        a, _ = slips(config(0.2), deal=True)
        b, game = slips(config(0.2), deal=False)
        self.assertEqual(a, b)
        self.assertNotEqual(a, slips(config(0.2, seed=1), deal=False)[0])
        days = sum(map(len, game.lives))
        self.assertAlmostEqual(len(a) / (days * len(game.world.people)), 0.2, delta=0.03)

    def test_bad_noise(self):
        for bad in (-0.1, 1.5, "0.1", True):
            self.assertRaises(ValueError, Game, config(bad))

    def test_noise_config(self):
        cfg = load(ROOT / "config" / "noise.toml")
        self.assertEqual(cfg["game"]["noise"], 0.1)
        self.assertEqual(cfg["view"]["lines"], CFG["view"]["lines"])        # [view] 只盖写了的那几项
        self.assertNotIn("失手", CFG["view"]["intro"])
        self.assertIn("失手", Env(cfg).instructions)


if __name__ == "__main__":
    unittest.main()
