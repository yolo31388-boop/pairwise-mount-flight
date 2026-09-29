"""坐骑飞行与空战系统"""
import math
import time
from dataclasses import dataclass, field

# 坐骑类型基础属性：耐力、基础飞行速度
MOUNT_BASE = {
    "sparrow": {"stamina": 60.0, "speed": 8.0},
    "horse": {"stamina": 80.0, "speed": 10.0},
    "eagle": {"stamina": 120.0, "speed": 14.0},
    "dragon": {"stamina": 200.0, "speed": 20.0},
}
DEFAULT_BASE = {"stamina": 100.0, "speed": 12.0}

# 空战技能：独立冷却(秒)与能量消耗
AIR_SKILLS = {
    "dive": {"cooldown": 8.0, "energy": 25.0},
    "barrage": {"cooldown": 12.0, "energy": 40.0},
    "ultimate": {"cooldown": 30.0, "energy": 80.0},
}
DEFAULT_SKILL = {"cooldown": 5.0, "energy": 20.0}

# 每张等级提供的耐力/速度成长
STAMINA_GROWTH = 0.02
SPEED_GROWTH = 0.5
SKILL_SPEED_BONUS = 1.5

# 地图边界与高度上限
MAP_BOUNDS = {
    "x": (-500.0, 500.0),
    "y": (0.0, 300.0),
    "z": (-500.0, 500.0),
}
MAX_HEIGHT = 300.0

# 碰撞后的速度倍率；深入障碍物过深时直接迫降
COLLISION_SLOW = 0.5
COLLISION_LAND_RATIO = 0.5

# 被击落地后的保护缓冲时间(秒)与免伤比例
FALL_PROTECTION_TIME = 3.0
ENERGY_REGEN = 5.0


@dataclass
class Mount:
    mid: str
    name: str
    level: int = 1
    stamina: float = 0.0
    flight_skills: dict = field(default_factory=dict)
    equipment: dict = field(default_factory=dict)


class FlightSystem:
    def __init__(self):
        self.mounts: dict[str, Mount] = {}
        self.map_height_limit: float = MAX_HEIGHT
        self.map_bounds: dict = {k: v for k, v in MAP_BOUNDS.items()}
        self.skill_cd: dict[str, float] = {}
        self.obstacles: list[dict] = []
        self.flight_state: dict[str, dict] = {}
        self.protection_duration: float = FALL_PROTECTION_TIME

    def add_mount(self, mount: Mount) -> None:
        self.mounts[mount.mid] = mount
        self.flight_state[mount.mid] = {
            "in_air": False,
            "x": 0.0, "y": 0.0, "z": 0.0,
            "energy": 100.0,
            "speed_multiplier": 1.0,
            "knocked": False,
            "knock_time": 0.0,
        }

    def _state(self, mid: str) -> dict:
        state = self.flight_state.get(mid)
        if state is None:
            state = {
                "in_air": True,
                "x": 0.0, "y": 0.0, "z": 0.0,
                "energy": 100.0,
                "speed_multiplier": 1.0,
                "knocked": False,
                "knock_time": 0.0,
            }
            self.flight_state[mid] = state
        return state

    def _base(self, mid: str) -> dict:
        mount = self.mounts.get(mid)
        if mount is None:
            return DEFAULT_BASE
        return MOUNT_BASE.get(mount.name, DEFAULT_BASE)

    # ---- 高度与地图边界 ----

    def get_max_height(self) -> float:
        return self.map_height_limit

    def in_map_bounds(self, x: float, y: float, z: float) -> bool:
        xmin, xmax = self.map_bounds["x"]
        ymin, ymax = self.map_bounds["y"]
        zmin, zmax = self.map_bounds["z"]
        return (xmin <= x <= xmax
                and ymin <= y <= ymax
                and zmin <= z <= zmax
                and y <= self.map_height_limit)

    def force_land(self, mid: str, reason: str = "") -> None:
        state = self._state(mid)
        state["in_air"] = False
        state["y"] = 0.0
        state["speed_multiplier"] = 1.0
        self._trigger_landing_cooldown()

    def _trigger_landing_cooldown(self) -> None:
        for skill, cfg in AIR_SKILLS.items():
            self.skill_cd[skill] = max(
                self.skill_cd.get(skill, 0.0), cfg["cooldown"]
            )

    # ---- 空战技能冷却与能量 ----

    def can_use_air_skill(self, mid: str, skill: str) -> bool:
        if self.skill_cd.get(skill, 0.0) > 0.0:
            return False
        cfg = AIR_SKILLS.get(skill, DEFAULT_SKILL)
        state = self._state(mid)
        if state["energy"] < cfg["energy"]:
            return False
        if not state["in_air"]:
            return False
        return True

    def use_air_skill(self, mid: str, skill: str) -> bool:
        if not self.can_use_air_skill(mid, skill):
            return False
        cfg = AIR_SKILLS.get(skill, DEFAULT_SKILL)
        state = self._state(mid)
        state["energy"] -= cfg["energy"]
        self.skill_cd[skill] = cfg["cooldown"]
        return True

    def is_air_skill_on_ground(self, mid: str, in_air: bool) -> bool:
        """空战技能是否可用：仅在空中返回 True。"""
        return bool(in_air)

    def takeoff(self, mid: str) -> bool:
        state = self._state(mid)
        if state["knocked"]:
            return False
        state["in_air"] = True
        return True

    def land(self, mid: str) -> None:
        state = self._state(mid)
        state["in_air"] = False
        self._trigger_landing_cooldown()

    # ---- 耐力与速度 ----

    def get_stamina(self, mid: str) -> float:
        base = self._base(mid)["stamina"]
        mount = self.mounts.get(mid)
        level = mount.level if mount else 1
        stamina = base * (1.0 + STAMINA_GROWTH * (level - 1))
        if mount:
            for equip in mount.equipment.values():
                if isinstance(equip, dict):
                    stamina += equip.get("stamina", 0.0)
        return stamina

    def get_flight_speed(self, mid: str) -> float:
        mount = self.mounts.get(mid)
        base = self._base(mid)["speed"]
        level = mount.level if mount else 1
        speed = base + SPEED_GROWTH * (level - 1)
        if mount:
            for equip in mount.equipment.values():
                if isinstance(equip, dict):
                    speed += equip.get("speed", 0.0)
            speed += sum(
                level_bonus * SKILL_SPEED_BONUS
                for level_bonus in mount.flight_skills.values()
            )
        return speed * self._state(mid)["speed_multiplier"]

    # ---- 碰撞检测 ----

    def check_collision(self, mid: str, x: float, y: float, z: float) -> bool:
        for obstacle in self.obstacles:
            dist = math.sqrt(
                (x - obstacle["x"]) ** 2
                + (y - obstacle["y"]) ** 2
                + (z - obstacle["z"]) ** 2
            )
            if dist <= float(obstacle["radius"]):
                return True
        return False

    def update_position(self, mid: str, x: float, y: float, z: float) -> bool:
        """移动到目标点；越界迫降，碰撞减速或迫降。"""
        if not self.in_map_bounds(x, y, z):
            self.force_land(mid, reason="out_of_bounds")
            return False
        state = self._state(mid)
        if self.check_collision(mid, x, y, z):
            hard_hit = any(
                math.sqrt(
                    (x - o["x"]) ** 2
                    + (y - o["y"]) ** 2
                    + (z - o["z"]) ** 2
                ) <= float(o["radius"]) * COLLISION_LAND_RATIO
                for o in self.obstacles
            )
            if hard_hit:
                self.force_land(mid, reason="collision")
                return False
            state["speed_multiplier"] = COLLISION_SLOW
            return False
        state["x"], state["y"], state["z"] = x, y, z
        return True

    # ---- 击落与落地保护 ----

    def knock_down(self, mid: str) -> None:
        state = self._state(mid)
        state["knocked"] = True
        state["knock_time"] = time.monotonic()
        state["in_air"] = False

    def get_fall_protection(self, mid: str) -> bool:
        """系统始终提供落地保护，缓冲期内掉落免伤。"""
        return True

    def is_fall_protected(self, mid: str) -> bool:
        state = self._state(mid)
        if not state["knocked"]:
            return True
        elapsed = time.monotonic() - state["knock_time"]
        return elapsed <= self.protection_duration

    def get_fall_damage(self, mid: str, fall_height: float) -> float:
        if self.get_fall_protection(mid) and self.is_fall_protected(mid):
            return 0.0
        return fall_height * 0.5

    # ---- 时间推进 ----

    def update(self, dt: float) -> None:
        for skill in list(self.skill_cd):
            self.skill_cd[skill] = max(0.0, self.skill_cd[skill] - dt)
        for state in self.flight_state.values():
            if state["in_air"]:
                state["energy"] = min(100.0, state["energy"] + ENERGY_REGEN * dt)
            if state["knocked"] and time.monotonic() - state["knock_time"] > self.protection_duration:
                state["knocked"] = False
