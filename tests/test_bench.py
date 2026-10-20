import unittest

from strata import load, play
from stratabench import AGENTS
from stratabench.agents import Anyone, Inference, Oracle

CFG = load()


def short(seed):
    return {**CFG, "game": {**CFG["game"], "seed": seed, "lives": 2, "life": 60, "gap": 200}}


class TestBench(unittest.TestCase):
    def test_every_agent_lives_every_day(self):
        for make in AGENTS:
            self.assertEqual([len(log) for log in play(short(0), make)], [60, 60])

    def test_ordering(self):
        score = {make: sum(sum(log) for seed in range(4) for log in play(short(seed), make))
                 for make in (Anyone, Inference, Oracle)}
        self.assertLess(score[Anyone], score[Inference])
        self.assertLess(score[Inference], score[Oracle])


if __name__ == "__main__":
    unittest.main()
