"""采办这一局。

每天：在昨天落脚的村子醒来，看见本村每个人的可见特质；接一单（可见的特质随便要一样，隐藏的总是要第一个值，
例如「找一个卖铁、守信的人」）；留下或去别村（同一地区当天就到，别的地区走一天）；挑一个人做这单（也可以不做），
各方面都对上就成了，做完才知道他的隐藏特质；挑了不卖这样货的人，就等于不做。
一世活满就死，世间空转一段时间，带着全部记忆在随便哪个村重生。
世界和订单各用独立的随机数，所以所有采办面对的是同一个世界、同一串订单。"""

import random

from .world import World


def play(cfg: dict, make_agent, say=None) -> list[list]:
    """返回每一世每天成没成单（在路上的那天算没成）。say(种类, **字段) 用来把发生的事写成文字。"""
    g, slots = cfg["game"], cfg["view"]["slots"]
    world = World(g["seed"], {s["name"]: s["values"] for s in slots}, **cfg["world"])
    visible = [s["name"] for s in slots if s["visible"]]
    hidden = [s["name"] for s in slots if not s["visible"]]
    agent = make_agent(world, visible)
    orders = random.Random(f"{g['seed']}:orders")
    say = say or (lambda kind, **kw: None)

    def look(village):
        stalls = {p: {s: world.value(p, s) for s in visible} for p in world.residents[village]}
        for p, seen in stalls.items():
            agent.observe(world.day, p, seen)
        return stalls

    lives = []
    for life in range(1, g["lives"] + 1):
        if life > 1:
            say("rebirth", life=life)
        here, log = orders.choice(world.villages), []
        while len(log) < g["life"]:
            world.step()
            stalls = look(here)
            want = {s["name"]: orders.choice(s["values"]) if s["visible"] else s["values"][0] for s in slots}
            say("order", day=world.day, village=world.villages.index(here), **want)
            say("stalls", stalls=stalls)
            dest = agent.go(world.day, here, want, stalls)
            if dest != here:
                days = world.distance(here, dest)
                say("travel" if days else "walk", village=world.villages.index(dest), days=days)
                for _ in range(days):
                    world.step()
                log += [False] * days
                here = dest
                if len(log) >= g["life"]:
                    break
                stalls = look(here)
                say("stalls", stalls=stalls)
            p = agent.choose(world.day, want, stalls)
            if p is not None and any(stalls[p][s] != want[s] for s in visible):
                p = None                                        # 他不卖你要的货，这单做不了，也就打听不到什么
            if p is None:
                log.append(False)
                say("skip")
                continue
            log.append(all(world.value(p, s) == v for s, v in want.items()))
            seen = {s: world.value(p, s) for s in hidden}
            agent.observe(world.day, p, seen)
            say("done" if log[-1] else "fail", person=p, **(want | seen))
        lives.append(log[:g["life"]])
        say("death", gap=g["gap"])
        for _ in range(g["gap"]):
            world.step()
    return lives
