"""世界：只管规律。唯一的宗旨是宏观变得慢，微观变得快。参数见 config/default.toml 的 [world]。

默认三层：地区 → 村 → 人；size 写四个数就是四层，地区 → 村 → 户 → 人。每个节点有若干槽位（特质），每个槽位各自：
  继承：要么有自己的值，要么随上一层；最上层总有自己的值。
  重抽：有一个时钟，时钟响时，以概率 mu 换成自己的一个值，否则改回随上一层。
快慢：人的时钟平均隔 tau ~ tau·ratio 天响一次，每往上一层再慢 ratio 倍；具体落在哪，因节点而异。
真值可追溯：任何时刻都能查到一个值由哪个节点决定（source），以及它上次变是哪天（since）。只给评测用，不影响规律。
变故（默认关）：宗旨之外唯一的例外。一个地区或一个村突然在一样特质上整个换了样，底下的人全都跟着变；
之后各人照常按自己的时钟慢慢再分化。哪天哪里出变故按 seed、世界日和节点固定，不动世界自己的随机数。
"""

import random


class World:
    def __init__(self, seed, slots: dict, size, tau, ratio, mu, shock=(0, 0)):
        """slots：槽位名 -> 取值列表；size：地区数、每个地区几个村、（每个村几户、）每个村或每户几个人；
        shock：每天每个地区、每个村（、每户）出变故的概率。"""
        self.seed, self.rng = seed, random.Random(seed)
        self.shock, self.shocks = tuple(shock), []              # shocks：出过的变故 (哪天, 节点, 槽位, 新值)
        self.slots = {k: tuple(v) for k, v in slots.items()}
        self.mu, self.parent, self.depth = mu, [], []
        if len(size) not in (3, 4):
            raise ValueError("size 要三个数（地区、村、人）或四个数（地区、村、户、人）")
        self.layers = len(size)                                 # 一共几层；人在最下面一层

        def grow(parent, counts):
            for _ in range(counts[0]):
                n = self._add(parent)
                if len(counts) > 1:
                    grow(n, counts[1:])

        grow(None, list(size))
        nodes, leaf = range(len(self.depth)), self.layers - 1
        # 每个（节点，槽位）的平均变化间隔：落在 tau·ratio^k 到 tau·ratio^(k+1) 之间，k 是离最下层几层
        self.tau = {s: [tau * ratio ** (leaf - self.depth[n] + self.rng.random()) for n in nodes] for s in self.slots}
        self.own = {s: [self._draw(n, s) for n in nodes] for s in self.slots}
        self.villages = [n for n in nodes if self.depth[n] == 1]
        self.people = [n for n in nodes if self.depth[n] == leaf]
        self.below = {n: [n] for n in nodes}                    # 每个节点连同它下面的所有节点
        for n in reversed(nodes):                               # 下层的编号总比上层大，所以倒着收
            if self.parent[n] is not None:
                self.below[self.parent[n]] += self.below[n]
        self.residents = {v: sorted(p for p in self.below[v] if self.depth[p] == leaf) for v in self.villages}
        self.since = {s: [0] * len(nodes) for s in self.slots}  # 每个节点在每个槽位上表现出来的值，上次变是哪天
        self.day = 0

    def _add(self, parent) -> int:
        self.parent.append(parent)
        self.depth.append(0 if parent is None else self.depth[parent] + 1)
        return len(self.depth) - 1

    def _draw(self, n, s):
        """最上层总有自己的值；其余以概率 mu 有自己的值，否则随上一层（None）。"""
        if self.depth[n] == 0 or self.rng.random() < self.mu:
            return self.rng.choice(self.slots[s])
        return None

    def source(self, n, s) -> int:
        """n 在槽位 s 上表现出来的值由哪个节点决定：从 n 往上数，第一个有自己值的。"""
        own = self.own[s]
        while own[n] is None:
            n = self.parent[n]
        return n

    def value(self, n, s) -> str:
        return self.own[s][self.source(n, s)]

    def step(self):
        """过一天：每个（节点，槽位）的时钟以 1/τ 的概率响一次。顺手记下谁表现出来的值变了。"""
        self.day += 1
        for s, taus in self.tau.items():
            for n, t in enumerate(taus):
                if self.rng.random() < 1 / t:
                    before = [self.value(m, s) for m in self.below[n]]
                    self.own[s][n] = self._draw(n, s)
                    self._mark(n, s, before)
        for n, d in enumerate(self.depth):
            if d < len(self.shock) and self.shock[d]:
                rng = random.Random(f"{self.seed}:shock:{self.day}:{n}")
                if rng.random() < self.shock[d]:
                    self._shock(n, rng)

    def _mark(self, n, s, before):
        for m, v in zip(self.below[n], before, strict=True):
            if self.value(m, s) != v:
                self.since[s][m] = self.day

    def _shock(self, n, rng):
        """变故：n 在随便一样特质上换成一个和现在不同的值，底下所有节点都改回随上一层。"""
        s = rng.choice(list(self.slots))
        before = [self.value(m, s) for m in self.below[n]]
        value = rng.choice([v for v in self.slots[s] if v != before[0]])
        for m in self.below[n]:
            self.own[s][m] = None
        self.own[s][n] = value
        self._mark(n, s, before)
        self.shocks.append((self.day, n, s, value))

    def chain(self, n) -> list[int]:
        """从最上层到 n 的一串节点。"""
        out = [n]
        while self.parent[out[-1]] is not None:
            out.append(self.parent[out[-1]])
        return out[::-1]

    def distance(self, a, b) -> int:
        """从村 a 到村 b 路上走几天：同一地区里串村当天就到，去别的地区走一天。"""
        return 0 if self.parent[a] == self.parent[b] else 1
