"""世界观的校验和生成。世界观只是一层皮：换了皮，规律和每一天发生的事都不变。

check(view)            一份世界观能不能用：缺什么、哪句台词的占位写错了、名字会不会撞。返回问题列表，空的就是能用。
same_shape(a, b)       两份世界观是不是同一个形状（几样特质、哪些看得见、各有几个值）。形状一样才能做换皮对比。
abstract(view)         纯抽象皮：名字、特质、台词全换成没有含义的记号。不用 LLM。
generate(theme, ask)   让 LLM 照着一份现成的世界观，按主题重写一份；写得不合格就把问题告诉它重写。
understood(view, ask)  回读：把台词念给 LLM，看它能不能读出要什么、成没成。防止皮写得好看但意思丢了。
dump(view)             写成 worldview.toml 的格式。

ask(prompt) -> str 由调用方给；命令行里用 OpenAI 兼容的接口（默认 DeepSeek，key 读环境变量 DEEPSEEK_API_KEY）：
  python -m strata.worldview check config/worldview.toml
  python -m strata.worldview abstract -o config/worldview-abstract.toml
  python -m strata.worldview generate --theme "深海空间站" -o config/worldview-station.toml
"""

import argparse
import json
import os
import re
import string
import sys
import tomllib
import urllib.request
from pathlib import Path

from .config import ROOT

POOLS = ("regions", "villages", "people")
RESERVED = {"day", "days", "village", "person", "house", "map", "gap", "life", "place", "value", "node", "slot",
            "stalls"}
BAD_IN_NAME = re.compile(r"[\s。．.！!，,；;「」“”\"'`{}]")       # 文本接口按名字认人认村，这些字符会让动作解析不了


def _fields(line: str) -> set[str] | None:
    """一句台词里用到的占位；写法不对（括号不配对、用了 {0} 或 {a.b}）返回 None。"""
    try:
        names = {name for _, name, _, _ in string.Formatter().parse(line) if name is not None}
    except ValueError:
        return None
    return None if any(not n or not n.isidentifier() for n in names) else names


def check(view: dict) -> list[str]:
    """返回这份世界观的问题；空列表就是能用。"""
    out = []
    if not isinstance(view.get("intro"), str) or not view["intro"].strip():
        out.append("缺开场白 intro")

    seen = {}
    for pool in (*POOLS, *(["houses"] if "houses" in view else [])):    # houses：四层的世界才要
        names = view.get(pool)
        if not isinstance(names, list) or not names or not all(isinstance(n, str) and n for n in names):
            out.append(f"{pool} 要是一串非空的名字")
            continue
        for n in names:
            if BAD_IN_NAME.search(n):
                out.append(f"{pool} 里的「{n}」带空白或标点，文本接口认不出")
            if n[-1].isdigit():
                out.append(f"{pool} 里的「{n}」以数字结尾：名字不够用时会自动加编号，会和别的名字撞")
            if n in seen:
                out.append(f"名字「{n}」重复了（{seen[n]} 和 {pool}）")
            seen[n] = pool

    slots = view.get("slots")
    if not isinstance(slots, list) or not slots:
        return out + ["缺特质 slots"]
    names = [s.get("name") for s in slots]
    for s in slots:
        name, values = s.get("name"), s.get("values")
        if not isinstance(name, str) or not name.isidentifier() or name in RESERVED:
            out.append(f"特质名「{name}」不能用：要能写进台词的占位里，也不能和 {sorted(RESERVED)} 重名")
        if not isinstance(values, list) or len(values) < 2 or len(set(values)) != len(values):
            out.append(f"特质「{name}」至少要两个不同的值")
        if not isinstance(s.get("visible"), bool):
            out.append(f"特质「{name}」要写明 visible = true / false")
    if len(set(names)) != len(names):
        out.append("特质名重复了")
    visible = [s["name"] for s in slots if s.get("visible") is True]
    hidden = [s["name"] for s in slots if s.get("visible") is False]
    if not visible or not hidden:
        out.append("至少要一样看得见的特质和一样看不见的特质")
    if out:
        return out

    lines = view.get("lines")
    if not isinstance(lines, dict):
        return ["缺台词 lines"]
    every = set(visible) | set(hidden)
    spec = {                                                    # 种类 -> （必须有的占位，还可以有的占位）
        "map": ({"map"}, set()),
        "order": ({"day", "village", *visible}, set(hidden)),
        "walk": ({"village"}, {"days"}),
        "travel": ({"village", "days"}, set()),
        "stall": ({"person", *visible}, set()),
        "done": ({"person"}, every),
        "fail": ({"person"} | (set(hidden) if len(hidden) > 1 else set()), every),
        "skip": (set(), set()),
        "death": ({"gap"}, set()),
        "rebirth": ({"life"}, set()),
    }
    if "houses" in view:
        spec["house"] = ({"house", "stalls"}, set())
    todo = [(kind, lines.get(kind), need, may) for kind, (need, may) in spec.items()]
    shock = lines.get("shock") if isinstance(lines.get("shock"), dict) else {}
    todo += [(f"shock.{s}", shock.get(s), {"place", "value"}, set()) for s in names]
    for kind, line, need, may in todo:
        if not isinstance(line, str) or not line.strip():
            out.append(f"缺台词 {kind}")
            continue
        used = _fields(line)
        if used is None:
            out.append(f"台词 {kind} 的占位写法不对：{line}")
            continue
        if need - used:
            out.append(f"台词 {kind} 少了占位 {sorted(need - used)}")
        if used - need - may:
            out.append(f"台词 {kind} 用了不该有的占位 {sorted(used - need - may)}")
    if isinstance(lines.get("done"), str) and lines.get("done") == lines.get("fail"):
        out.append("成了和没成的台词一样，采办分不出来")
    return out


def same_shape(a: dict, b: dict) -> list[str]:
    """换皮对比要求两份世界观形状一样：特质一一对应，看得见与否、值的个数都相同；名字只能多不能少。"""
    out = []
    shape = lambda v: [(s["visible"], len(s["values"])) for s in v["slots"]]  # noqa: E731
    if shape(a) != shape(b):
        out.append(f"特质的形状不一样：{shape(a)} 和 {shape(b)}（每样特质：看不看得见、几个值）")
    out += [f"{pool} 的名字比原来少：{len(b[pool])} < {len(a[pool])}" for pool in POOLS if len(b[pool]) < len(a[pool])]
    return out


def _code(prefix: str, i: int) -> str:
    """不带数字的记号：PA、PB……PZ、PAA。名字不够用时自动加的编号就不会和它撞。"""
    out = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(ord("A") + r) + out
    return prefix + out


def abstract(view: dict) -> dict:
    """纯抽象皮：形状和原来一样，名字、特质、取值、台词都换成没有含义的记号。"""
    slots = [{"name": _code("T", i), "values": [f"{_code('T', i)}{_code('', j).lower()}" for j in range(len(s["values"]))],
              "visible": s["visible"]} for i, s in enumerate(view["slots"])]
    visible = [s["name"] for s in slots if s["visible"]]
    hidden = [s["name"] for s in slots if not s["visible"]]
    said = lambda names: "、".join(f"{n} 是{{{n}}}" for n in names)  # noqa: E731
    return {
        "intro": (
            "这是一个由地区、村、人组成的世界。每个人有几样特质："
            f"{'、'.join(visible)} 走到跟前就看得见，{'、'.join(hidden)} 要和他做过一单才知道。\n"
            "每天你在昨天所在的村醒来，接到一个任务：找一个特质符合要求的人做一单。别村的人现在什么样，只能凭记忆。\n"
            "同一地区里换村，当天就到；去别的地区，路上要走一天。\n"
            "人的特质会变，村的会变，地区的也会变，只是越大的变得越慢。\n"
            "一世到头，世界照常运转；你会在随便哪个村重新开始，之前的事都还记得。"
        ),
        "regions": [_code("R", i) for i in range(len(view["regions"]))],
        "villages": [_code("V", i) for i in range(len(view["villages"]))],
        "people": [_code("P", i) for i in range(len(view["people"]))],
        **({"houses": [_code("H", i) for i in range(len(view["houses"]))]} if "houses" in view else {}),
        "slots": slots,
        "lines": {
            "map": "地图——{map}。",
            "order": f"第 {{day}} 天，你在{{village}}。任务：找一个 {said(visible + hidden)} 的人做一单。",
            "walk": "你走到{village}。",
            "travel": "你去{village}，路上走了 {days} 天。",
            "stall": f"{{person}}：{said(visible)}",
            **({"house": "{house} 这一户——{stalls}"} if "houses" in view else {}),
            "done": f"你和{{person}}做了一单。结果：{said(hidden)}。成了。",
            "fail": f"你和{{person}}做了一单。结果：{said(hidden)}。没成。",
            "skip": "今天没有合适的人，没做。",
            "death": "这一世结束了。世界又过了 {gap} 天。",
            "rebirth": "第 {life} 世开始。之前的事，你都还记得。",
            "shock": {s["name"]: f"消息：{{place}}变了，现在那里人人 {s['name']} 是{{value}}。" for s in slots},
        },
    }


def dump(view: dict) -> str:
    """写成 worldview.toml 的格式；load 回来和原来一样。"""
    q = lambda x: json.dumps(x, ensure_ascii=False)  # noqa: E731
    key = lambda k: k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else q(k)  # noqa: E731
    out = [f"intro = {q(view['intro'])}", ""]
    out += [f"{pool} = [{', '.join(map(q, view[pool]))}]" for pool in (*POOLS, "houses") if pool in view]
    for s in view["slots"]:
        out += ["", "[[slots]]", f"name = {q(s['name'])}", f"values = [{', '.join(map(q, s['values']))}]",
                f"visible = {'true' if s['visible'] else 'false'}"]
    out += ["", "[lines]"] + [f"{key(k)} = {q(v)}" for k, v in view["lines"].items() if isinstance(v, str)]
    out += ["", "[lines.shock]"] + [f"{key(k)} = {q(v)}" for k, v in view["lines"].get("shock", {}).items()]
    return "\n".join(out) + "\n"


PROMPT = """下面是一个文字世界的「世界观」文件（TOML）。它只管名字和台词，世界的规律不由它决定。
请按主题「{theme}」重写一份，格式完全一样。要求：
1. 特质（[[slots]]）的个数、顺序、visible、每样特质有几个值，都不能变；名字和取值换成符合主题的词。
   看不见的特质，第一个值是任务想要的那个。特质名只能用汉字、字母、下划线，不能带空格和标点。
2. regions、villages、people 的名字个数不能比原来少，互相不能重复，不能带空格、标点，不能以数字结尾。
3. [lines] 里每一句都要重写，花括号里的占位只能用原来那一句里出现过的那几种，并把特质名换成你的新特质名。
   [lines.shock] 里每样特质一句，用 {{place}} 和 {{value}}。
4. intro 要把这几条规则用新主题讲清楚：每天醒来接一个任务；看得见的特质走到跟前就知道，看不见的要做过才知道；
   同一地区里换地方当天到，去别的地区要走一天；人、村、地区都会变，越大的变得越慢；一世结束后世界照常运转，
   重新开始时之前的事都还记得。
5. 只输出 TOML，放在 ```toml 代码块里，不要解释。

{base}"""


def _toml(reply: str) -> dict:
    m = re.search(r"```(?:toml)?\s*\n(.*?)```", reply, re.S)
    return tomllib.loads(m.group(1) if m else reply)


def generate(theme: str, ask, base: dict | None = None, tries: int = 3) -> dict:
    """让 LLM 按主题重写一份和 base 同形状的世界观。不合格就把问题告诉它再写，最多 tries 次。"""
    base = base or tomllib.loads((ROOT / "config" / "worldview.toml").read_text(encoding="utf-8"))
    prompt = PROMPT.format(theme=theme, base=dump(base))
    problems = []
    for _ in range(tries):
        reply = ask(prompt if not problems else
                    prompt + "\n\n你上一次写的有这些问题，请改正后重新输出完整的 TOML：\n" + "\n".join(f"- {p}" for p in problems))
        try:
            view = _toml(reply)
        except tomllib.TOMLDecodeError as e:
            problems = [f"不是合法的 TOML：{e}"]
            continue
        problems = check(view)
        problems = problems or same_shape(base, view)
        if not problems:
            return view
    raise ValueError("生成的世界观不合格：\n" + "\n".join(problems))


def understood(view: dict, ask) -> list[str]:
    """回读：只把台词念给 LLM，看它能不能读出任务要什么、这一单成没成。返回读错的地方。"""
    out = []
    sample = {s["name"]: s["values"][0] for s in view["slots"]}
    names = {"person": view["people"][0], "village": view["villages"][0], "day": 7}
    order = view["lines"]["order"].format(**names, **sample)
    reply = ask("下面是一个文字世界里的一句话。只根据这句话回答：任务要找什么样的人？\n"
                f"用 JSON 回答，键是这几样特质：{list(sample)}，值是这句话里要求的取值；这句话没提到的特质填 null。只输出 JSON。\n\n"
                f"{order}")
    try:
        got = json.loads(re.search(r"\{.*\}", reply, re.S).group(0))
    except (AttributeError, json.JSONDecodeError):
        got = {}
    for name, value in sample.items():                          # 看不见的特质写死在句子里也得读得出来
        if got.get(name) != value:
            out.append(f"任务那句读不出「{name}」要「{value}」（读成了 {got.get(name)!r}）：{order}")
    for kind, want in (("done", "成了"), ("fail", "没成")):
        # 没成的那句：看不见的特质换成不想要的值
        values = sample if kind == "done" else sample | {s["name"]: s["values"][1] for s in view["slots"] if not s["visible"]}
        line = view["lines"][kind].format(**names, **values)
        reply = ask(f"下面是一个文字世界里的一句话。只根据这句话回答：这一单是成了还是没成？只回答「成了」或「没成」。\n\n{line}")
        other = "没成" if want == "成了" else "成了"
        if want not in reply or other in reply:
            out.append(f"{kind} 那句读不出这一单{want}（回答：{reply.strip()[:40]}）：{line}")
    return out


def chat(model: str, base_url: str, key: str):
    """OpenAI 兼容接口上的 ask(prompt) -> str。"""
    def ask(prompt: str) -> str:
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", body,
                                     {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]
    return ask


def main():
    ap = argparse.ArgumentParser(prog="strata.worldview", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="查一份世界观能不能用")
    c.add_argument("file")
    a = sub.add_parser("abstract", help="生成纯抽象皮")
    g = sub.add_parser("generate", help="让 LLM 按主题生成")
    g.add_argument("--theme", required=True)
    g.add_argument("--model", default="deepseek-chat")
    g.add_argument("--base-url", default="https://api.deepseek.com")
    g.add_argument("--key-env", default="DEEPSEEK_API_KEY", help="存 API key 的环境变量名")
    g.add_argument("--tries", type=int, default=3)
    g.add_argument("--no-readback", action="store_true", help="不做回读检查")
    for p in (a, g):
        p.add_argument("--base", default=str(ROOT / "config" / "worldview.toml"), help="照着哪一份改")
        p.add_argument("-o", "--output", required=True)
    args = ap.parse_args()

    if args.cmd == "check":
        problems = check(tomllib.loads(Path(args.file).read_text(encoding="utf-8")))
        print("\n".join(problems) if problems else "能用。")
        sys.exit(bool(problems))
    base = tomllib.loads(Path(args.base).read_text(encoding="utf-8"))
    if args.cmd == "abstract":
        view = abstract(base)
    else:
        if not os.environ.get(args.key_env):
            sys.exit(f"先在环境变量 {args.key_env} 里放好 API key")
        ask = chat(args.model, args.base_url, os.environ[args.key_env])
        view = generate(args.theme, ask, base, args.tries)
        misread = [] if args.no_readback else understood(view, ask)
        if misread:
            print("回读有问题，文件照样写出，请人工看一眼：", *misread, sep="\n", file=sys.stderr)
    Path(args.output).write_text(dump(view), encoding="utf-8", newline="\n")
    print(f"写好了：{args.output}")


if __name__ == "__main__":
    main()
