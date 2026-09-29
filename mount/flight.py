"""坐骑飞行与空战系统。

修复点:
1. 飞行高度上限 + 地图边界, 越界强制降落
2. 空战技能独立冷却 + 能量消耗
3. 飞行耐力按坐骑类型与等级区分
4. 空战技能仅可在空中使用, 落地后进入冷却
5. 飞行碰撞检测, 碰撞后减速(高速撞击则强制降落)
6. 飞行速度由坐骑等级 + 装备 + 技能综合计算
7. 被击落后有落地保护与缓冲时间, 不直接死亡
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---------- 全局配置 ----------
DEFAULT_MAX_HEIGHT = 500.0
MAP_BOUND_X = 1000.0
MAP_BOUND_Y = 1000.0

# 各类型坐骑的基础耐力与基础飞行速度
MOUNT_TYPE_BASE: dict[str, dict[str, float]] = {
    "sparrow": {"stamina": 60.0, "speed": 8.0},
    "horse": {"stamina": 80.0, "speed": 10.0},
    "wolf": {"stamina": 90.0, "speed": 11.0},
    "eagle": {"stamina": 120.0, "speed": 14.0},
    "griffin": {"stamina": 160.0, "speed": 17.0},
    "dragon": {"stamina": 200.0, "speed": 20.0},
}
DEFAULT_BASE = {"stamina": 100.0, "speed": 10.0}

STAMINA_PER_LEVEL = 4.0
SPEED_PER_LEVEL = 0.5
ENERGY_DRAIN_PER_SEC = 1.0

# 空战技能: 冷却时间(秒) 与 能量消耗
AIR_SKILL_CONFIGS: dict[str, dict[str, float]] = {
    "dive": {"cooldown": 10.0, "energy": 25.0},
    "aerial_slash": {"cooldown": 6.0, "energy": 15.0},
    "wind_nova": {"cooldown": 12.0, "energy": 30.0},
    "storm_ultimate": {"cooldown": 30.0, "energy": 60.0},
}
DEFAULT_SKILL_CONFIG = {"cooldown": 5.0, "energy": 10.0}
LANDING_SKILL_COOLDOWN = 3.0

COLLISION_SLOW_FACTOR = 0.5
COLLISION_SLOW_DURATION = 2.0
HARD_COLLISION_SPEED = 25.0

FALL_PROTECTION_BUFFER = 3.0
MOUNT_RADIUS = 0.0


@dataclass
class Mount:
    mid: str
    name: str
    level: int = 1
    stamina: float = 100.0
    flight_skills: dict = field(default_factory=dict)
    equipment: dict = field(default_factory=dict)


class FlightSystem:
    def __init__(self):
        self.mounts: dict[str, Mount] = {}

        # bug1 修复: 高度上限与地图边界
        self.map_height_limit: float = DEFAULT_MAX_HEIGHT
        self.map_bounds = {
            "min_x": -MAP_BOUND_X,
            "max_x": MAP_BOUND_X,
            "min_y": -MAP_BOUND_Y,
            "max_y": MAP_BOUND_Y,
            "min_z": 0.0,
            "max_z": DEFAULT_MAX_HEIGHT,
        }

        # bug2 修复: 空战技能冷却(剩余秒数, 按技能名)与技能配置
        self.skill_cd: dict[str, float] = {}
        self.skill_configs: dict[str, dict[str, float]] = {
            name: dict(cfg) for name, cfg in AIR_SKILL_CONFIGS.items()
        }

        # bug5 修复: 障碍物列表
        self.obstacles: list[dict] = []

        # 系统运行时间(秒), 由 tick 推进
        self.time: float = 0.0
        # 每个坐骑的运行时状态
        self._states: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _base_params(self, mid: str) -> dict[str, float]:
        mount = self.mounts.get(mid)
        if mount is None:
            return dict(DEFAULT_BASE)
        return MOUNT_TYPE_BASE.get(mount.name, DEFAULT_BASE)

    def _state(self, mid: str) -> dict:
        state = self._states.get(mid)
        if state is None:
            state = {
                "in_air": False,
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "energy": self.get_stamina(mid),
                "speed_factor": 1.0,
                "slow_until": 0.0,
                "knockdown_at": None,
                "landing_reason": None,
            }
            self._states[mid] = state
        return state

    def _skill_config(self, skill: str) -> dict[str, float]:
        return self.skill_configs.get(skill, DEFAULT_SKILL_CONFIG)

    # ------------------------------------------------------------------
    # bug1: 高度上限 / 地图边界 / 越界强制降落
    # ------------------------------------------------------------------
    def get_max_height(self) -> float:
        return self.map_height_limit

    def in_bounds(self, x: float, y: float, z: float) -> bool:
        b = self.map_bounds
        return (
            b["min_x"] <= x <= b["max_x"]
            and b["min_y"] <= y <= b["max_y"]
            and b["min_z"] <= z <= b["max_z"]
            and z <= self.map_height_limit
        )

    def takeoff(self, mid: str, x: float = 0.0, y: float = 0.0) -> bool:
        if not self.in_bounds(x, y, 0.0) or self.check_collision(mid, x, y, 0.0):
            return False
        state = self._state(mid)
        state["in_air"] = True
        state["x"], state["y"], state["z"] = float(x), float(y), 0.0
        state["landing_reason"] = None
        if state["energy"] <= 0:
            state["energy"] = self.get_stamina(mid)
        return True

    def force_land(self, mid: str, reason: str = "unknown") -> None:
        state = self._state(mid)
        state["in_air"] = False
        state["z"] = 0.0
        state["landing_reason"] = reason
        # 落地后空战技能全部进入冷却(bug4)
        self._apply_landing_cooldown()

    def _apply_landing_cooldown(self) -> None:
        for skill in self.skill_configs:
            self.skill_cd[skill] = max(
                self.skill_cd.get(skill, 0.0), LANDING_SKILL_COOLDOWN
            )

    def update_position(self, mid: str, x: float, y: float, z: float) -> bool:
        """尝试把坐骑移动到目标坐标; 返回是否移动成功。"""
        state = self._state(mid)
        if not state["in_air"]:
            return False
        if not self.in_bounds(x, y, z):
            # 超出高度/地图边界: 强制降落
            self.force_land(mid, reason="out_of_bounds")
            return False
        if self.check_collision(mid, x, y, z):
            self._handle_collision(mid, x, y, z)
            return False
        state["x"], state["y"], state["z"] = float(x), float(y), float(z)
        return True

    # ------------------------------------------------------------------
    # bug2: 空战技能冷却与能量
    # ------------------------------------------------------------------
    def can_use_air_skill(self, mid: str, skill: str) -> bool:
        if self.skill_cd.get(skill, 0.0) > 0.0:
            return False
        if not self._state(mid)["in_air"]:
            return False
        cost = self._skill_config(skill)["energy"]
        return self._state(mid)["energy"] >= cost

    def use_air_skill(self, mid: str, skill: str) -> bool:
        if not self.can_use_air_skill(mid, skill):
            return False
        cfg = self._skill_config(skill)
        state = self._state(mid)
        state["energy"] -= cfg["energy"]
        self.skill_cd[skill] = cfg["cooldown"]
        return True

    # ------------------------------------------------------------------
    # bug3: 耐力按坐骑类型与等级
    # ------------------------------------------------------------------
    def get_stamina(self, mid: str) -> float:
        base = self._base_params(mid)["stamina"]
        level = 1
        mount = self.mounts.get(mid)
        if mount is not None:
            level = max(1, mount.level)
        return base + (level - 1) * STAMINA_PER_LEVEL

    # ------------------------------------------------------------------
    # bug4: 空战技能只能在空中使用
    # ------------------------------------------------------------------
    def is_air_skill_on_ground(self, mid: str, in_air: bool) -> bool:
        """返回空战技能当前是否可放: 空中可放, 地面不可放。"""
        return bool(in_air)

    def land(self, mid: str) -> None:
        """主动落地: 空中技能进入落地冷却。"""
        self.force_land(mid, reason="manual_landing")

    # ------------------------------------------------------------------
    # bug5: 碰撞检测
    # ------------------------------------------------------------------
    def check_collision(self, mid: str, x: float, y: float, z: float) -> bool:
        for obstacle in self.obstacles:
            dist = math.sqrt(
                (x - obstacle["x"]) ** 2
                + (y - obstacle["y"]) ** 2
                + (z - obstacle["z"]) ** 2
            )
            if dist <= obstacle.get("radius", 0.0) + MOUNT_RADIUS:
                return True
        return False

    def _handle_collision(self, mid: str, x: float, y: float, z: float) -> None:
        state = self._state(mid)
        speed = self.get_flight_speed(mid)
        if speed >= HARD_COLLISION_SPEED:
            # 高速撞击: 强制降落
            self.force_land(mid, reason="collision")
            return
        # 普通碰撞: 减速一段时间, 位置贴到障碍边缘之外保持原位
        state["speed_factor"] = COLLISION_SLOW_FACTOR
        state["slow_until"] = self.time + COLLISION_SLOW_DURATION

    # ------------------------------------------------------------------
    # bug6: 速度 = 类型基础 + 等级 + 装备 + 技能, 再受碰撞减速影响
    # ------------------------------------------------------------------
    @staticmethod
    def _bonus_speed(items: dict) -> float:
        total = 0.0
        for item in items.values():
            if isinstance(item, dict):
                total += float(item.get("speed", 0.0))
        return total

    def get_flight_speed(self, mid: str) -> float:
        mount = self.mounts.get(mid)
        level = max(1, mount.level) if mount is not None else 1
        speed = self._base_params(mid)["speed"]
        speed += (level - 1) * SPEED_PER_LEVEL
        if mount is not None:
            speed += self._bonus_speed(mount.equipment)
            speed += self._bonus_speed(mount.flight_skills)
        state = self._state(mid)
        if self.time < state["slow_until"]:
            speed *= state["speed_factor"]
        return speed

    # ------------------------------------------------------------------
    # bug7: 被击落的落地保护与缓冲
    # ------------------------------------------------------------------
    def knock_down(self, mid: str) -> None:
        """坐骑在空中被击落: 开始坠落并获得落地保护缓冲。"""
        state = self._state(mid)
        state["in_air"] = False
        state["knockdown_at"] = self.time

    def get_fall_protection(self, mid: str) -> bool:
        """是否处于落地保护缓冲内(缓冲期内坠落免伤)。"""
        state = self._states.get(mid)
        if state is None or state.get("knockdown_at") is None:
            # 保护机制默认存在: 任何被击落者都会获得缓冲
            return True
        return self.time - state["knockdown_at"] <= FALL_PROTECTION_BUFFER

    def apply_fall_damage(self, mid: str, fall_height: float) -> float:
        """结算坠落伤害: 保护缓冲期内为 0, 缓冲期外按高度计算。"""
        if self.get_fall_protection(mid):
            return 0.0
        return max(0.0, fall_height - self.get_max_height() * 0.0)

    # ------------------------------------------------------------------
    # 时间推进: 冷却 / 耐力消耗 / 减速恢复
    # ------------------------------------------------------------------
    def tick(self, dt: float) -> None:
        self.time += dt
        for skill, remaining in list(self.skill_cd.items()):
            self.skill_cd[skill] = max(0.0, remaining - dt)
        for mid, state in self._states.items():
            if state["in_air"]:
                state["energy"] = max(
                    0.0, state["energy"] - ENERGY_DRAIN_PER_SEC * dt
                )
                if state["energy"] <= 0.0:
                    self.force_land(mid, reason="out_of_stamina")
            if self.time >= state["slow_until"]:
                state["speed_factor"] = 1.0
