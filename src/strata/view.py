"""世界观：只在显示边界把世界节点编号翻成名字，把事件写成文字。

四层的世界多一层「户」：世界观里要有 houses（户的名字）和台词 house（一户的摊子怎么说，占位 {house}、{stalls}）。
"""

KINDS = {3: ("region", "village", "person"), 4: ("region", "village", "house", "person")}


class View:
    def __init__(self, view: dict, world):
        self.world = world
        self.lines, self.intro = view["lines"], view["intro"]
        self.kinds = KINDS[world.layers]
        self.pools = {"region": view["regions"], "village": view["villages"], "person": view["people"]}
        if "house" in self.kinds:
            self.pools["house"] = view["houses"]
        self.names = {k: {} for k in self.pools}
        self.regions = [n for n, d in enumerate(world.depth) if d == 0]
        layers = [[n for n, d in enumerate(world.depth) if d == i] for i in range(world.layers - 1)]
        self._indices = {n: i for nodes in layers for i, n in enumerate(nodes)}   # 人以外的节点：同一层里排第几

    def name(self, n: int) -> str:
        """输入统一为节点编号；人名按节点固定，地区、村和户按地图顺序起名。"""
        kind = self.kinds[self.world.depth[n]]
        names, pool = self.names[kind], self.pools[kind]
        if n not in names:
            index = n if kind == "person" else self._indices[n]
            names[n] = pool[index % len(pool)] + (str(index // len(pool) + 1) if index >= len(pool) else "")
        return names[n]

    def map(self) -> str:
        """哪个地区有哪些村。"""
        places = []
        for r in self.regions:
            villages = [self.name(v) for v in self.world.villages if self.world.parent[v] == r]
            places.append(self.name(r) + "：" + "、".join(villages))
        return self.lines["map"].format(map="；".join(places))

    def say(self, kind: str, **kw) -> str:
        if kind == "stalls":
            stall = lambda p, seen: self.lines["stall"].format(person=self.name(p), **seen)  # noqa: E731
            if "house" not in self.kinds:
                return "，".join(stall(p, seen) for p, seen in kw["stalls"].items()) + "。"
            houses = {}                                         # 四层：一户一户地说，谁和谁是一家看得出来
            for p, seen in kw["stalls"].items():
                houses.setdefault(self.world.parent[p], []).append(stall(p, seen))
            return "；".join(self.lines["house"].format(house=self.name(h), stalls="，".join(said))
                            for h, said in houses.items()) + "。"
        if kind == "shock":                                     # 每样特质一句：[lines.shock] 里按槽位名找
            return self.lines["shock"][kw["slot"]].format(place=self.name(kw["node"]), value=kw["value"])
        for k in ("village", "person"):
            if k in kw:
                kw[k] = self.name(kw[k])
        return self.lines[kind].format(**kw)
