"""分层推断（上限参照）：对一个槽位，每个人、每个村、每个地区各一个隐马尔可夫，各自从记录里估计自己变得多快。

    每一层的节点：观察是它下面所有人的见闻，隔几层继承，证据就按比例打几次折；
    跳变时多半随上一层（此刻对上一层的估计），少数换成自己的值；最上层均匀地跳。
各层快慢都在一组候选值上积分（在线贝叶斯），所以一条旧记录打多少折，由这个对象自己的善变程度决定。
只用世界的结构（谁住哪）和 mu，不看真值。
"""

import math

# 候选的变化间隔（天）。只用到「宏观慢、微观快」这条宗旨：人在短的一头，村和地区在长的一头
PERSON_RATES = [2.0 ** -k for k in range(10)]               # 1 ~ 512 天
GROUP_RATES = [2.0 ** -k for k in range(2, 15)]             # 4 ~ 16384 天


class Track:
    """一个节点表现值的隐马尔可夫，跳变速度在候选值上积分。"""

    def __init__(self, rates):
        self.rates = rates
        self.belief = [None] * len(rates)
        self.logw = [0.0] * len(rates)
        self.t = None

    def _prior(self, i, day, jump):
        if self.t is None:
            return dict(jump)
        stay = math.exp(-self.rates[i] * (day - self.t))
        return {g: stay * self.belief[i][g] + (1 - stay) * x for g, x in jump.items()}

    def predictive(self, day, jump):
        if self.t is None:
            return dict(jump)
        top = max(self.logw)
        weights = [math.exp(lw - top) for lw in self.logw]
        z = sum(weights)
        out = dict.fromkeys(jump, 0.0)
        for i, w in enumerate(weights):
            for g, x in self._prior(i, day, jump).items():
                out[g] += w / z * x
        return out

    def update(self, day, emission, jump):
        for i in range(len(self.rates)):
            like = {g: x * emission[g] for g, x in self._prior(i, day, jump).items()}
            z = sum(like.values())
            self.logw[i] += math.log(z)
            self.belief[i] = {g: x / z for g, x in like.items()}
        self.t = day


class Hier:
    """一个槽位的分层推断。"""

    def __init__(self, world, slot: str):
        self.world, self.mu = world, world.mu
        self.goods = world.slots[slot]
        self.uniform = {g: 1 / len(self.goods) for g in self.goods}
        self.tracks, self.memo = {}, {}

    def _track(self, node):
        if node not in self.tracks:
            self.tracks[node] = Track(PERSON_RATES if self.world.depth[node] == 2 else GROUP_RATES)
        return self.tracks[node]

    def _emission(self, seen, hops):
        """隔 hops 层继承：这条见闻有 (1 − mu)^hops 的概率反映这一层的值，其余像随机。"""
        keep, n = (1 - self.mu) ** hops, len(self.goods)
        return {g: keep * (g == seen) + (1 - keep) / n for g in self.goods}

    def _jump(self, node, day):
        """跳变的去向：多半随上一层（此刻对它的估计），少数换成自己的值（均匀）；最上层均匀地跳。"""
        parent = self.world.parent[node]
        if parent is None:
            return self.uniform
        up = self.dist(parent, day)
        return {g: (1 - self.mu) * up[g] + self.mu / len(self.goods) for g in self.goods}

    def dist(self, node, day):
        """此刻对某个节点表现值的估计，自上而下。"""
        if (node, day) not in self.memo:
            self.memo[node, day] = self._track(node).predictive(day, self._jump(node, day))
        return self.memo[node, day]

    def observe(self, day, p, seen):
        chain = self.world.chain(p)
        for hops, node in zip(range(len(chain) - 1, -1, -1), chain, strict=True):
            self._track(node).update(day, self._emission(seen, hops), self._jump(node, day))
            self.memo.clear()
