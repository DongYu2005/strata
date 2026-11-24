import copy
import json
import tomllib
import unittest

from strata import Env, load, play
from strata.config import ROOT
from strata.worldview import abstract, check, dump, generate, same_shape, understood
from stratabench import AGENTS

CFG = load()
VIEW = CFG["view"]


def broken(change) -> list[str]:
    view = copy.deepcopy(VIEW)
    change(view)
    return check(view)


class TestCheck(unittest.TestCase):
    def test_shipped_worldviews_pass(self):
        for path in sorted((ROOT / "config").glob("worldview*.toml")):
            self.assertEqual(check(tomllib.loads(path.read_text(encoding="utf-8"))), [], path.name)

    def test_catches_mistakes(self):
        cases = {
            "缺台词 skip": lambda v: v["lines"].pop("skip"),
            "缺台词 shock.守不守信": lambda v: v["lines"]["shock"].pop("守不守信"),
            "少了占位": lambda v: v["lines"].update(stall="摊上摆着{卖什么}"),
            "不该有的占位": lambda v: v["lines"].update(stall="{person}的摊上摆着{卖什么}，他{守不守信}"),
            "占位写法不对": lambda v: v["lines"].update(skip="今天没找着{人"),
            "分不出来": lambda v: v["lines"].update(fail=v["lines"]["done"]),
            "重复": lambda v: v["people"].append(v["villages"][0]),
            "认不出": lambda v: v["villages"].append("白 垩渡"),
            "以数字结尾": lambda v: v["people"].append("老秦2"),
            "至少要两个不同的值": lambda v: v["slots"][1].update(values=["守信"]),
            "不能用": lambda v: v["slots"][0].update(name="person"),
            "至少要一样看得见的特质和一样看不见的特质": lambda v: v["slots"][1].update(visible=True),
            "缺开场白": lambda v: v.update(intro=" "),
        }
        for expect, change in cases.items():
            problems = broken(change)
            self.assertTrue(any(expect in p for p in problems), (expect, problems))

    def test_two_hidden_fail_line_must_say_which(self):
        view = copy.deepcopy(load(ROOT / "config" / "more-memory.toml")["view"])
        view["lines"]["fail"] = "你从{person}手里买下{卖什么}，东家沉下了脸。"
        self.assertTrue(any("少了占位" in p for p in check(view)))


class TestAbstract(unittest.TestCase):
    def test_file_is_generated(self):
        """config/worldview-abstract.toml 就是 abstract(默认世界观)；改了生成器要重新生成。"""
        on_disk = tomllib.loads((ROOT / "config" / "worldview-abstract.toml").read_text(encoding="utf-8"))
        self.assertEqual(on_disk, abstract(VIEW))
        self.assertEqual(tomllib.loads(dump(VIEW)), VIEW)               # dump 再读回来不走样

    def test_same_shape_no_meaning_left(self):
        view = abstract(VIEW)
        self.assertEqual(same_shape(VIEW, view), [])
        text = dump(view)
        for word in [*VIEW["regions"], *VIEW["villages"], *VIEW["people"][:20], "守信", "短秤", "盐", "东家"]:
            self.assertNotIn(word, text)

    def test_same_world_under_new_skin(self):
        """换皮不换世界：同一个 seed，每种采办在两张皮上逐日成绩相同。"""
        skin = load(ROOT / "config" / "abstract.toml")
        short = lambda cfg: {**cfg, "game": {**cfg["game"], "seed": 1, "lives": 2, "life": 30, "gap": 100}}  # noqa: E731
        for make in AGENTS:
            self.assertEqual(play(short(skin), make), play(short(CFG), make), make.name)

    def test_text_game_runs(self):
        cfg = load(ROOT / "config" / "abstract.toml")
        env = Env({**cfg, "world": {**cfg["world"], "shock": [0.05, 0.1]},
                   "game": {**cfg["game"], "lives": 2, "life": 20, "gap": 30}})
        obs = env.reset()
        self.assertIn("任务：找一个 TA 是", obs)
        text = [obs]
        while not env.done:
            obs, _, info = env.step("继续" if env.life_ended else env.legal_actions()[0])
            self.assertTrue(info["parse_ok"])
            text.append(obs)
        self.assertRegex("\n".join(text), r"消息：[RV][A-Z]+变了")
        self.assertRegex("\n".join(text), r"结果：TB 是TB[ab]。(成了|没成)。")


class FakeLLM:
    """按顺序回放准备好的回答，记下收到的提示。"""

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0)


def station() -> dict:
    """一份手写的、合格的新皮，当作 LLM 的回答。"""
    view = copy.deepcopy(VIEW)
    view["intro"] = "你是空间站的补给员。"
    view["regions"] = [f"环区{c}" for c in "甲乙丙丁"]
    view["villages"] = [f"舱段{c}" for c in "子丑寅卯辰巳午未申酉戌亥"]
    view["people"] = [f"船员{a}{b}" for a in "甲乙丙丁戊己庚辛壬癸" for b in "子丑寅卯辰巳午未申酉戌亥"]
    view["slots"] = [{"name": "存货", "values": ["氧气", "燃料", "滤芯"], "visible": True},
                     {"name": "信誉", "values": ["可靠", "掺水"], "visible": False}]
    view["lines"] = {k: v.replace("卖什么", "存货").replace("守不守信", "信誉") if isinstance(v, str) else
                     {"存货": v["卖什么"], "信誉": v["守不守信"]} for k, v in VIEW["lines"].items()}
    return view


class TestGenerate(unittest.TestCase):
    def test_accepts_good_reply(self):
        ask = FakeLLM("好的：\n```toml\n" + dump(station()) + "```\n")
        view = generate("深海空间站", ask)
        self.assertEqual(view, station())
        self.assertIn("深海空间站", ask.prompts[0])
        self.assertIn("守不守信", ask.prompts[0])                         # 把原来那份给它照着改

    def test_retries_with_problems(self):
        bad = station()
        bad["lines"]["stall"] = "摊上摆着{存货}"
        fewer = station()
        fewer["slots"][0]["values"].pop()
        ask = FakeLLM("这不是 TOML = = =", dump(bad), dump(fewer), dump(station()))
        self.assertEqual(generate("深海空间站", ask, tries=4), station())
        self.assertIn("不是合法的 TOML", ask.prompts[1])
        self.assertIn("少了占位", ask.prompts[2])
        self.assertIn("形状不一样", ask.prompts[3])
        self.assertRaises(ValueError, generate, "深海空间站", FakeLLM(dump(bad), dump(bad)), tries=2)

    def test_readback(self):
        want = json.dumps({"卖什么": "盐", "守不守信": "守信"}, ensure_ascii=False)
        self.assertEqual(understood(VIEW, FakeLLM(want, "成了", "没成")), [])
        problems = understood(VIEW, FakeLLM(json.dumps({"卖什么": "铁", "守不守信": None}), "成了", "成了"))
        self.assertEqual(len(problems), 3)                              # 货读错、守信没读出、没成读成了成了


if __name__ == "__main__":
    unittest.main()
