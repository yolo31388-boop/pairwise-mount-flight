"""坐骑飞行与空战系统 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mount.flight import FlightSystem, Mount

class TestHeightLimit:
    def test_flight_has_height_limit(self):
        fs = FlightSystem()
        h = fs.get_max_height()
        assert h < float("inf") and h > 0

class TestAirSkillCooldown:
    def test_air_skill_has_cooldown(self):
        fs = FlightSystem()
        fs.skill_cd["dive"] = 10.0
        assert fs.can_use_air_skill("m1", "dive") == False

class TestStaminaByMount:
    def test_different_mounts_different_stamina(self):
        fs = FlightSystem()
        fs.mounts["m1"] = Mount("m1", "sparrow", level=1)
        fs.mounts["m2"] = Mount("m2", "dragon", level=50)
        s1 = fs.get_stamina("m1")
        s2 = fs.get_stamina("m2")
        assert s2 > s1

class TestAirSkillOnlyInAir:
    def test_cannot_use_air_skill_on_ground(self):
        fs = FlightSystem()
        assert fs.is_air_skill_on_ground("m1", in_air=False) == False
        assert fs.is_air_skill_on_ground("m1", in_air=True) == True

class TestCollision:
    def test_flight_has_collision_detection(self):
        fs = FlightSystem()
        # 应该有障碍物列表
        assert hasattr(fs, "obstacles")
        fs.obstacles = [{"x": 100, "y": 100, "z": 100, "radius": 10}]
        assert fs.check_collision("m1", 100, 100, 100) == True

class TestFlightSpeed:
    def test_speed_depends_on_level_and_equip(self):
        fs = FlightSystem()
        fs.mounts["m1"] = Mount("m1", "horse", level=1)
        fs.mounts["m2"] = Mount("m2", "dragon", level=50, equipment={"wings": {"speed": 20}})
        s1 = fs.get_flight_speed("m1")
        s2 = fs.get_flight_speed("m2")
        assert s2 > s1

class TestFallProtection:
    def test_knocked_down_has_protection(self):
        fs = FlightSystem()
        assert fs.get_fall_protection("m1") == True
