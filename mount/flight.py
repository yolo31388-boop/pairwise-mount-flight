"""坐骑飞行与空战系统 - 含7个bug"""
from dataclasses import dataclass, field

@dataclass
class Mount:
    mid: str
    name: str
    level: int = 1
    stamina: float = 100  # bug3: 固定耐力
    flight_skills: dict = field(default_factory=dict)
    equipment: dict = field(default_factory=dict)

class FlightSystem:
    def __init__(self):
        self.mounts: dict[str, Mount] = {}
        self.map_height_limit: float = 1000  # bug1: 无限制
        self.skill_cd: dict[str, float] = {}  # bug2: 无冷却

    def get_max_height(self) -> float:
        # bug1: 无高度限制
        return float("inf")

    def can_use_air_skill(self, mid: str, skill: str) -> bool:
        # bug2: 无冷却
        return True

    def get_stamina(self, mid: str) -> float:
        # bug3: 固定耐力
        return 100.0

    def is_air_skill_on_ground(self, mid: str, in_air: bool) -> bool:
        # bug4: 地面也能放空战技能
        return True

    def check_collision(self, mid: str, x: float, y: float, z: float) -> bool:
        # bug5: 无碰撞
        return False

    def get_flight_speed(self, mid: str) -> float:
        # bug6: 固定速度
        return 10.0

    def get_fall_protection(self, mid: str) -> bool:
        # bug7: 无落地保护
        return False
