"""Ecos do Abismo: Panteão.

Jogo de ação 2D autocontido em Python + Pygame.
Não usa imagens, fontes, música ou sons externos: tudo é desenhado ou
gerado proceduralmente para continuar fácil de baixar e executar.
"""

from __future__ import annotations

import json
import math
import random
from array import array
from dataclasses import dataclass
from pathlib import Path

import pygame
from pygame import Rect, Surface
from pygame.math import Vector2


WIDTH, HEIGHT = 960, 540
FPS = 60
GROUND_Y = 468
WORLD_WIDTH = 1900
SAVE_FILE = Path("panteao_save.json")

Color = tuple[int, int, int]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def smoothstep(value: float) -> float:
    value = clamp(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def draw_glow(surface: Surface, center: tuple[int, int], color: Color, radius: int, alpha: int = 90) -> None:
    """Cheap layered glow that stays crisp at any resolution."""
    radius = max(2, radius)
    layer = Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
    cx = layer.get_width() // 2
    for ring in range(4, 0, -1):
        ring_radius = int(radius * ring / 4)
        ring_alpha = int(alpha * (0.10 + ring * 0.08))
        pygame.draw.circle(layer, (*color, ring_alpha), (cx, cx), ring_radius)
    # Normal alpha compositing is portable across pygame 2.x and Windows builds.
    # The additive alpha flag is not exposed by every pygame version.
    surface.blit(layer, (center[0] - cx, center[1] - cx))


def draw_text(
    surface: Surface,
    text: str,
    position: tuple[int, int],
    size: int,
    color: Color,
    *,
    center: bool = False,
    bold: bool = False,
) -> None:
    font = pygame.font.SysFont("dejavusans", size, bold=bold)
    image = font.render(text, True, color)
    rect = image.get_rect()
    rect.center = position if center else rect.topleft
    if not center:
        rect.topleft = position
    surface.blit(image, rect)


def land_on_platform(
    position: Vector2,
    previous_bottom: float,
    velocity_y: float,
    width: int,
    height: int,
    platforms: list[Rect],
) -> Rect | None:
    """Resolve only downward crossings, preventing sticky platform hitboxes."""
    if velocity_y < 0:
        return None
    current = Rect(int(position.x), int(position.y), width, height)
    candidates = [
        platform
        for platform in platforms
        if current.right > platform.left
        and current.left < platform.right
        and previous_bottom <= platform.top + 4
        and current.bottom >= platform.top
    ]
    return min(candidates, key=lambda platform: platform.top) if candidates else None


class AudioSystem:
    """Efeitos e uma faixa de rock pesado gerados em tempo real."""

    RATE = 44100

    def __init__(self) -> None:
        self.enabled = False
        self.master_volume = 0.62
        self.muted = False
        self.channel: pygame.mixer.Channel | None = None
        self.effects: dict[str, pygame.mixer.Sound] = {}
        self.tracks: dict[str, pygame.mixer.Sound] = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=self.RATE, size=-16, channels=1, buffer=512)
            self.effects = {
                "attack": self._tone(0.13, 270, 1050, 0.25, 0.04),
                "impact": self._tone(0.18, 180, 48, 0.46, 0.22),
                "hurt": self._tone(0.25, 220, 74, 0.34, 0.15),
                "transform": self._tone(0.9, 100, 28, 0.5, 0.08),
                "select": self._tone(0.08, 460, 720, 0.2, 0.0),
            }
            self.tracks = {
                "menu": self._ambient((55, 82.5, 110), 0.16),
                "cavern": self._ambient((43, 64.5, 86), 0.2),
                "rock": self._rock_track(),
            }
            for style in ("abyss", "storm", "crystal", "fungus", "forge",
                          "tide", "clock", "eclipse", "thorn", "inferno", "mecha"):
                self.tracks[f"phase_{style}"] = self._phase_track(style)
            self.enabled = True
            self._apply()
        except pygame.error:
            self.enabled = False

    @property
    def audible_volume(self) -> float:
        return 0.0 if self.muted else self.master_volume

    @staticmethod
    def _bytes(samples: array) -> bytes:
        return samples.tobytes()

    def _tone(self, duration: float, start: float, end: float, volume: float, noise: float) -> pygame.mixer.Sound:
        count = int(self.RATE * duration)
        samples = array("h")
        phase = 0.0
        rng = random.Random(int(start + end))
        for index in range(count):
            t = index / max(1, count - 1)
            frequency = start + (end - start) * t
            phase += math.tau * frequency / self.RATE
            value = math.sin(phase) + math.sin(phase * 2.01) * 0.22
            value += rng.uniform(-noise, noise) if noise else 0
            envelope = min(1.0, t / 0.04, (1.0 - t) / max(0.05, duration * 0.28))
            samples.append(int(clamp(value * volume * envelope, -1, 1) * 32767))
        return pygame.mixer.Sound(buffer=self._bytes(samples))

    def _ambient(self, frequencies: tuple[float, ...], volume: float) -> pygame.mixer.Sound:
        count = int(self.RATE * 8)
        samples = array("h")
        for index in range(count):
            t = index / self.RATE
            value = sum(math.sin(math.tau * frequency * t) * (0.52 / (i + 1)) for i, frequency in enumerate(frequencies))
            pulse = 0.82 + math.sin(t * 0.7) * 0.18
            samples.append(int(clamp(value * volume * pulse, -1, 1) * 32767))
        return pygame.mixer.Sound(buffer=self._bytes(samples))

    def _rock_track(self) -> pygame.mixer.Sound:
        """Cria um loop simples de bateria e riffs distorcidos após a primeira transformação."""
        duration = 8.0
        count = int(self.RATE * duration)
        samples = array("h")
        bpm = 154
        beat_seconds = 60 / bpm
        notes = (82.4, 98.0, 110.0, 123.5, 146.8, 164.8)
        for index in range(count):
            t = index / self.RATE
            beat = t / beat_seconds
            step = int(beat * 2)
            note = notes[step % len(notes)]
            phase = math.tau * note * t
            guitar = math.copysign(1.0, math.sin(phase)) * 0.11
            guitar += math.sin(phase * 2.01) * 0.08
            kick_phase = t % (beat_seconds * 2)
            kick = math.sin(math.tau * (110 - kick_phase * 80) * kick_phase) * math.exp(-kick_phase * 19) * 0.55
            snare_phase = (t - beat_seconds) % (beat_seconds * 2)
            snare_noise = random.uniform(-1, 1) * math.exp(-snare_phase * 27) * 0.2 if snare_phase >= 0 else 0
            hat_phase = t % (beat_seconds / 2)
            hat = random.uniform(-1, 1) * math.exp(-hat_phase * 65) * 0.075
            value = (guitar + kick + snare_noise + hat) * 0.62
            samples.append(int(clamp(value, -1, 1) * 32767))
        return pygame.mixer.Sound(buffer=self._bytes(samples))

    def _phase_track(self, style: str) -> pygame.mixer.Sound:
        """Short procedural leitmotifs: each apotheosis gets its own genre pulse."""
        profiles = {
            "abyss": ((58.3, 73.4, 87.3), 142, "choir"),
            "storm": ((110, 146.8, 220), 176, "pulse"),
            "crystal": ((261.6, 329.6, 392), 128, "glass"),
            "fungus": ((73.4, 92.5, 116.5), 116, "swamp"),
            "forge": ((55, 69.3, 82.4), 184, "metal"),
            "tide": ((65.4, 98, 130.8), 132, "wave"),
            "clock": ((196, 246.9, 293.7), 104, "tick"),
            "eclipse": ((46.2, 58.3, 69.3), 88, "void"),
            "thorn": ((164.8, 207.7, 246.9), 152, "dance"),
            "inferno": ((55.0, 73.4, 110.0), 168, "metal"),
            "mecha": ((43.7, 65.4, 98.0), 118, "pulse"),
        }
        notes, bpm, texture = profiles[style]
        duration = 6.0
        count = int(self.RATE * duration)
        samples = array("h")
        beat_seconds = 60 / bpm
        rng = random.Random(sum(ord(char) for char in style) * 97)
        for index in range(count):
            t = index / self.RATE
            beat = t / beat_seconds
            step = int(beat * 2)
            note = notes[step % len(notes)]
            phase = math.tau * note * t
            lead = math.sin(phase) * 0.15 + math.sin(phase * 2.01) * 0.08
            sub = math.sin(math.tau * note * 0.5 * t) * 0.12
            pulse = t % beat_seconds
            kick = math.sin(math.tau * (110 - pulse * 95) * pulse) * math.exp(-pulse * 24) * 0.38
            if texture in {"glass", "tick"}:
                tick = math.sin(math.tau * (880 + (step % 4) * 110) * t) * math.exp(-pulse * 32) * 0.13
            else:
                tick = rng.uniform(-1, 1) * math.exp(-pulse * 40) * 0.08
            if texture in {"wave", "choir", "void"}:
                swell = (0.55 + 0.45 * math.sin(math.tau * t / 3.0)) * 0.16
            else:
                swell = 0.0
            value = (lead + sub + kick + tick + swell) * 0.72
            envelope = min(1.0, t / 0.18, (duration - t) / 0.22)
            samples.append(int(clamp(value * envelope, -1, 1) * 32767))
        return pygame.mixer.Sound(buffer=self._bytes(samples))

    def _apply(self) -> None:
        if not self.enabled:
            return
        for effect in self.effects.values():
            effect.set_volume(self.audible_volume)
        for name, track in self.tracks.items():
            track.set_volume(self.audible_volume * (0.50 if name == "rock" or name.startswith("phase_") else 0.34))

    def play(self, name: str) -> None:
        if self.enabled and name in self.effects:
            self.effects[name].set_volume(self.audible_volume)
            self.effects[name].play()

    def start(self, track_name: str) -> None:
        if not self.enabled or track_name not in self.tracks:
            return
        if self.channel is not None:
            self.channel.fadeout(420)
        track = self.tracks[track_name]
        track.set_volume(self.audible_volume * (0.50 if track_name == "rock" or track_name.startswith("phase_") else 0.34))
        self.channel = track.play(loops=-1, fade_ms=600)

    def adjust(self, delta: float) -> None:
        self.master_volume = clamp(self.master_volume + delta, 0, 1)
        self._apply()

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        self._apply()
        return self.muted

    def shutdown(self) -> None:
        if self.enabled:
            pygame.mixer.stop()


@dataclass
class Particle:
    position: Vector2
    velocity: Vector2
    color: Color
    radius: float
    lifetime: float
    gravity: float = 0

    def update(self, dt: float) -> bool:
        self.position += self.velocity * dt
        self.velocity.y += self.gravity * dt
        self.lifetime -= dt
        self.radius *= 0.985
        return self.lifetime > 0 and self.radius > 0.5

    def draw(self, surface: Surface, camera_x: float) -> None:
        alpha = int(clamp(self.lifetime / 1.2, 0, 1) * 255)
        layer = Surface((20, 20), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*self.color, alpha), (10, 10), max(1, int(self.radius)))
        surface.blit(layer, (int(self.position.x - camera_x - 10), int(self.position.y - 10)))


@dataclass
class HealthPotion:
    position: Vector2
    age: float = 0.0
    collected: bool = False

    @property
    def rect(self) -> Rect:
        return Rect(int(self.position.x - 13), int(self.position.y - 22), 26, 44)

    def update(self, dt: float) -> None:
        self.age += dt

    def draw(self, surface: Surface, camera_x: float, accent: Color) -> None:
        if self.collected:
            return
        x = int(self.position.x - camera_x)
        bob = math.sin(self.age * 4.0) * 5
        y = int(self.position.y + bob)
        pulse = int(2 + math.sin(self.age * 5.0) * 2)
        draw_glow(surface, (x, y - 3), (255, 82, 116), 42, 68)
        pygame.draw.ellipse(surface, (8, 10, 28), (x - 24, y + 19, 48, 12))
        pygame.draw.ellipse(surface, (*accent, 135), (x - 23, y + 14, 46, 14), 2)
        pygame.draw.polygon(surface, (50, 35, 72), [
            (x - 17, y + 16), (x + 17, y + 16), (x + 12, y + 23),
            (x - 12, y + 23),
        ])
        pygame.draw.line(surface, accent, (x - 12, y + 18), (x + 12, y + 18), 2)
        pygame.draw.rect(surface, (118, 42, 77), (x - 12, y - 12, 24, 29), border_radius=7)
        pygame.draw.rect(surface, (255, 84, 126), (x - 9, y - 8, 18, 21), border_radius=5)
        pygame.draw.rect(surface, (235, 219, 178), (x - 7, y - 21, 14, 9), border_radius=3)
        pygame.draw.rect(surface, (255, 243, 215), (x - 4, y - 23, 8, 3), border_radius=1)
        pygame.draw.line(surface, (255, 245, 226), (x - 6, y - 4), (x - 6, y + 8), 2)
        pygame.draw.line(surface, (255, 168, 190), (x + 5, y - 4), (x + 5, y + 11), 2)
        pygame.draw.line(surface, accent, (x - 4, y + 4), (x + 4, y + 4), 2)
        pygame.draw.line(surface, accent, (x, y), (x, y + 9), 2)
        pygame.draw.circle(surface, (255, 235, 246), (x - 7, y - 4), 2)
        pygame.draw.circle(surface, (255, 224, 238), (x + 8, y + 3), 2)
        pygame.draw.arc(surface, (255, 180, 202), (x - 16 - pulse, y - 28 - pulse,
                                                     32 + pulse * 2, 52 + pulse * 2),
                        math.pi * 1.05, math.pi * 1.95, 2)


class Player:
    def __init__(self) -> None:
        self.width = 42
        self.height = 72
        self.position = Vector2(150, GROUND_Y - self.height)
        self.velocity = Vector2()
        self.facing = 1
        self.health = 100
        self.on_ground = False
        self.jumps_left = 2
        self.attack_timer = 0
        self.attack_cooldown = 0
        self.invulnerable = 0
        self.hurt_flash = 0
        self.shield_max = 55
        self.shield = self.shield_max
        self.shield_broken = False
        self.shield_break_timer = 0.0
        self.damage_level = 0
        self.bruised_eye = 0.0
        self.blood_drips: list[tuple[float, float, float]] = []
        self.walk_time = 0
        self.trail: list[tuple[Vector2, float]] = []
        self.land_bounce = 0.0
        self.attack_swing = 0.0
        self.aspect_style = "abyss"
        self.dodge_timer = 0.0
        self.dodge_cooldown = 0.0
        self.dodge_direction = 1

    def set_aspect(self, style: str) -> None:
        self.aspect_style = style

    @property
    def rect(self) -> Rect:
        return Rect(int(self.position.x), int(self.position.y), self.width, self.height)

    @property
    def attack_rect(self) -> Rect:
        offset = self.width if self.facing > 0 else -74
        return Rect(int(self.position.x + offset), int(self.position.y + 18), 74, 34)

    def reset(self) -> None:
        self.__init__()

    def jump(self, particles: list[Particle]) -> None:
        if self.jumps_left <= 0:
            return
        self.velocity.y = -620 if self.jumps_left == 2 else -545
        self.jumps_left -= 1
        self.on_ground = False
        for _ in range(8):
            particles.append(Particle(
                Vector2(self.rect.centerx, self.rect.bottom),
                Vector2(random.uniform(-70, 70), random.uniform(-100, -25)),
                (166, 206, 232), random.uniform(2, 4), 0.45, 160,
            ))

    def attack(self, particles: list[Particle]) -> bool:
        if self.attack_timer > 0 or self.attack_cooldown > 0:
            return False
        self.attack_timer = 0.22
        self.attack_cooldown = 0.24
        self.attack_swing = 1.0
        for _ in range(5):
            particles.append(Particle(
                Vector2(self.attack_rect.right if self.facing > 0 else self.attack_rect.left, self.attack_rect.centery),
                Vector2(random.uniform(50, 140) * self.facing, random.uniform(-50, 50)),
                (222, 247, 255), random.uniform(2, 4), 0.28,
            ))
        return True

    def dodge(self, particles: list[Particle]) -> bool:
        """Short, readable evasive move with a real decision cost."""
        if self.dodge_cooldown > 0 or self.dodge_timer > 0:
            return False
        self.dodge_direction = self.facing or 1
        self.dodge_timer = 0.18
        self.dodge_cooldown = 0.72
        self.invulnerable = max(self.invulnerable, 0.28)
        self.velocity.x = self.dodge_direction * 760
        self.velocity.y = 0
        for _ in range(10):
            particles.append(Particle(
                Vector2(self.rect.center),
                Vector2(-self.dodge_direction * random.uniform(100, 280),
                        random.uniform(-85, 85)),
                (178, 224, 255), random.uniform(2, 5), 0.34, 180,
            ))
        return True

    def take_damage(self, amount: int, particles: list[Particle]) -> bool:
        if self.invulnerable > 0:
            return False
        remaining = amount
        if self.shield > 0:
            absorbed = min(self.shield, remaining)
            self.shield -= absorbed
            remaining -= absorbed
            self.shield_break_timer = 0.14
            if self.shield <= 0 and not self.shield_broken:
                self.shield_broken = True
                self.invulnerable = 0.3
                for _ in range(22):
                    angle = random.uniform(0, math.tau)
                    speed = random.uniform(90, 260)
                    particles.append(Particle(
                        Vector2(self.rect.center),
                        Vector2(math.cos(angle) * speed, math.sin(angle) * speed),
                        (151, 229, 255), random.uniform(2, 6), 0.85, 25,
                    ))
        self.health = max(0, self.health - remaining)
        self.invulnerable = 0.82
        self.hurt_flash = 0.18
        if remaining > 0:
            self.damage_level = min(5, self.damage_level + 1)
            self.bruised_eye = min(1.0, self.bruised_eye + 0.38)
            self.blood_drips.append((random.uniform(0.28, 0.72), random.uniform(0.15, 0.45), 1.0))
            self.blood_drips = self.blood_drips[-6:]
        self.land_bounce = 0.0
        self.velocity.x = -230 if self.facing > 0 else 230
        for _ in range(13):
            particles.append(Particle(
                Vector2(self.rect.center),
                Vector2(random.uniform(-180, 180), random.uniform(-180, 35)),
                (255, 118, 139), random.uniform(2, 5), 0.55, 320,
            ))
        return True

    def update(self, dt: float, keys: pygame.key.ScancodeWrapper, platforms: list[Rect], particles: list[Particle]) -> None:
        self.attack_timer = max(0, self.attack_timer - dt)
        self.attack_cooldown = max(0, self.attack_cooldown - dt)
        self.dodge_timer = max(0, self.dodge_timer - dt)
        self.dodge_cooldown = max(0, self.dodge_cooldown - dt)
        self.invulnerable = max(0, self.invulnerable - dt)
        self.hurt_flash = max(0, self.hurt_flash - dt)
        self.shield_break_timer = max(0, self.shield_break_timer - dt)
        self.attack_swing = max(0, self.attack_swing - dt * 5.4)
        self.bruised_eye = max(0, self.bruised_eye - dt * 0.012)
        self.blood_drips = [(x, length, life - dt * 0.035)
                            for x, length, life in self.blood_drips if life - dt * 0.035 > 0]
        self.land_bounce = max(0, self.land_bounce - dt * 5.5)
        self.trail = [(position, life - dt * 1.8) for position, life in self.trail if life - dt * 1.8 > 0]

        if self.dodge_timer > 0:
            self.invulnerable = max(self.invulnerable, 0.08)
            self.velocity.x = self.dodge_direction * 760
            self.velocity.y = 0
            self.position.x = clamp(self.position.x + self.velocity.x * dt,
                                    24, WORLD_WIDTH - self.width - 24)
            self.trail.append((Vector2(self.position), 0.7))
            self.trail = self.trail[-9:]
            return

        direction = (1 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0) - (
            1 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0
        )
        if direction:
            self.facing = direction
            target_speed = direction * 370
            self.velocity.x += (target_speed - self.velocity.x) * min(1, dt * 14)
            self.walk_time += dt * 11
        else:
            self.velocity.x *= max(0, 1 - 15 * dt)
            self.walk_time += dt * 3
        if abs(self.velocity.x) > 90 and random.random() < min(1, dt * 18):
            self.trail.append((Vector2(self.position), 0.75))
            self.trail = self.trail[-7:]

        previous_bottom = self.position.y + self.height
        self.velocity.y += 1450 * dt
        self.position.x = clamp(self.position.x + self.velocity.x * dt, 24, WORLD_WIDTH - self.width - 24)
        self.position.y += self.velocity.y * dt
        was_grounded = self.on_ground
        self.on_ground = False
        landing = land_on_platform(self.position, previous_bottom, self.velocity.y, self.width, self.height, platforms)
        if landing is not None:
            self.position.y = landing.top - self.height
            self.velocity.y = 0
            self.on_ground = True
            self.jumps_left = 2
        if self.on_ground and not was_grounded:
            self.land_bounce = 1.0
            for _ in range(5):
                particles.append(Particle(
                    Vector2(self.rect.centerx, self.rect.bottom),
                    Vector2(random.uniform(-60, 60), random.uniform(-55, -10)),
                    (145, 175, 200), random.uniform(2, 3), 0.3, 90,
                ))

    def draw(self, surface: Surface, camera_x: float) -> None:
        if self.invulnerable > 0 and int(self.invulnerable * 16) % 2 == 0:
            return
        x, y = int(self.position.x - camera_x), int(self.position.y)
        bob = math.sin(self.walk_time) * 2.8 if abs(self.velocity.x) > 25 else 0
        squash = self.land_bounce * 4.0
        x += int(math.sin(self.walk_time * 0.5) * 0.8)
        y += int(bob + squash)
        aspect = self.aspect_style
        cloak_palette = {
            "abyss": (238, 240, 255), "storm": (169, 226, 255),
            "crystal": (184, 255, 235), "fungus": (234, 190, 255),
            "forge": (255, 205, 150), "tide": (150, 245, 239),
            "clock": (255, 232, 160), "eclipse": (210, 182, 255),
            "thorn": (255, 172, 218), "inferno": (255, 194, 132),
            "mecha": (174, 231, 255),
        }
        cloak = (255, 142, 160) if self.hurt_flash > 0 else cloak_palette.get(aspect, (238, 240, 255))
        accent = {
            "abyss": (137, 215, 255), "storm": (231, 250, 255),
            "crystal": (112, 255, 224), "fungus": (238, 127, 255),
            "forge": (255, 104, 44), "tide": (64, 221, 230),
            "clock": (255, 208, 84), "eclipse": (187, 119, 255),
            "thorn": (255, 79, 153), "inferno": (255, 92, 35),
            "mecha": (76, 210, 255),
        }.get(aspect, (137, 215, 255))
        for trail_position, life in self.trail:
            tx = int(trail_position.x - camera_x)
            ty = int(trail_position.y + bob * 0.3)
            ghost = Surface((64, 94), pygame.SRCALPHA)
            ghost_color = (*cloak, int(44 * clamp(life, 0, 1)))
            pygame.draw.polygon(ghost, ghost_color, [(32, 28), (10, 78), (54, 78)])
            surface.blit(ghost, (tx - 11, ty - 8))
        draw_glow(surface, (x + 23, y + 22), accent, 34, 32)
        if self.shield > 0:
            shield_radius = 39 + int(math.sin(self.walk_time * 2) * 2)
            shield_ratio = self.shield / max(1, self.shield_max)
            shield_color = (146, 228, 255) if self.shield_break_timer <= 0 else (242, 253, 255)
            pygame.draw.circle(surface, (*shield_color, 135), (x + 23, y + 31), shield_radius, 2)
            pygame.draw.arc(surface, accent,
                            Rect(x + 23 - shield_radius - 4, y + 31 - shield_radius - 4,
                                 (shield_radius + 4) * 2, (shield_radius + 4) * 2),
                            -1.0, -1.0 + math.tau * shield_ratio, 3)
        elif self.shield_broken:
            for shard in range(6):
                angle = self.walk_time * 0.4 + shard * math.tau / 6
                pygame.draw.line(surface, (132, 215, 255), (x + 23, y + 31),
                                 (x + 23 + int(math.cos(angle) * 42),
                                  y + 31 + int(math.sin(angle) * 42)), 1)
        pygame.draw.ellipse(surface, (7, 9, 24), (x - 5, y + 61, 52, 14))
        pygame.draw.polygon(surface, (36, 42, 74), [(x + 21, y + 27 + bob), (x + 3, y + 69), (x + 39, y + 69)])
        pygame.draw.polygon(surface, (57, 63, 102), [(x + 21, y + 31 + bob), (x + 12, y + 68), (x + 31, y + 68)])
        # Larger articulated arms react to movement and the attack input.
        stride = math.sin(self.walk_time * 1.15) * 8 if abs(self.velocity.x) > 25 else 0
        punch = 18 if self.attack_timer > 0 else 0
        left_hand = (x + 5 - int(stride), y + 48 - int(punch * 0.35))
        right_hand = (x + 38 + int(stride) + int(punch * self.facing), y + 47 + int(stride * 0.25))
        pygame.draw.line(surface, (47, 57, 91), (x + 12, y + 37), left_hand, 8)
        pygame.draw.line(surface, (68, 82, 126), (x + 31, y + 37), right_hand, 8)
        pygame.draw.circle(surface, accent, left_hand, 5)
        pygame.draw.circle(surface, (225, 245, 255), right_hand, 5)
        pygame.draw.polygon(surface, cloak, [
            (x + 12, y + 19 + bob), (x + 7, y - 3 + bob), (x + 18, y + 8 + bob),
            (x + 24, y - 8 + bob), (x + 31, y + 8 + bob), (x + 39, y - 3 + bob),
            (x + 34, y + 23 + bob),
        ])
        pygame.draw.ellipse(surface, (17, 21, 44), (x + 15, y + 12 + bob, 19, 17))
        pygame.draw.circle(surface, accent, (x + 21, y + 20 + int(bob)), 2)
        pygame.draw.circle(surface, accent, (x + 29, y + 20 + int(bob)), 2)
        expression = self.damage_level + (1 if self.hurt_flash > 0 else 0)
        pygame.draw.line(surface, cloak, (x + 18, y + 16 + int(bob)),
                         (x + 22, y + 15 + int(bob) - expression), 2)
        pygame.draw.line(surface, cloak, (x + 28, y + 15 + int(bob) - expression),
                         (x + 32, y + 16 + int(bob)), 2)
        if expression >= 2:
            pygame.draw.arc(surface, (255, 179, 195),
                            Rect(x + 20, y + 23 + int(bob), 11, 8), 0, math.pi, 2)
        elif expression == 0:
            pygame.draw.arc(surface, (220, 242, 255),
                            Rect(x + 20, y + 23 + int(bob), 11, 7), math.pi, math.tau, 2)
        if self.bruised_eye > 0.12:
            pygame.draw.ellipse(surface, (75, 28, 74),
                                (x + 15, y + 16 + int(bob), 10, 7))
            pygame.draw.ellipse(surface, (35, 14, 48),
                                (x + 16, y + 17 + int(bob), 7, 5))
        for drip_x, length, life in self.blood_drips:
            start_x = x + int(42 * drip_x)
            start_y = y + 30 + int(bob)
            drip_color = (145, 28, 56, int(210 * clamp(life, 0, 1)))
            pygame.draw.line(surface, drip_color[:3], (start_x, start_y),
                             (start_x + 2, start_y + int(18 * length)), 2)
            pygame.draw.circle(surface, drip_color[:3],
                               (start_x + 2, start_y + int(18 * length) + 2), 2)
        for mark in range(self.damage_level):
            sx = x + 8 + ((mark * 17) % 30)
            sy = y + 38 + ((mark * 11) % 25)
            pygame.draw.line(surface, (103, 36, 73), (sx, sy), (sx + 9, sy + 5), 2)
        if aspect == "storm":
            pygame.draw.line(surface, (235, 250, 255), (x + 8, y + 12), (x - 5, y - 4), 2)
            pygame.draw.line(surface, (235, 250, 255), (x + 34, y + 12), (x + 48, y - 4), 2)
        elif aspect == "crystal":
            pygame.draw.polygon(surface, accent, [(x + 21, y - 10), (x + 14, y + 8), (x + 21, y + 4)])
            pygame.draw.polygon(surface, accent, [(x + 21, y - 10), (x + 28, y + 8), (x + 21, y + 4)])
        elif aspect == "fungus":
            pygame.draw.ellipse(surface, accent, (x + 5, y - 9, 34, 10))
            pygame.draw.line(surface, cloak, (x + 21, y - 1), (x + 21, y + 8), 3)
        elif aspect == "forge":
            pygame.draw.polygon(surface, (255, 211, 92), [(x + 21, y - 15), (x + 12, y + 5), (x + 21, y - 1), (x + 30, y + 5)])
        elif aspect == "tide":
            pygame.draw.arc(surface, accent, Rect(x - 5, y - 12, 56, 40), math.pi, math.tau, 3)
        elif aspect == "clock":
            pygame.draw.circle(surface, accent, (x + 24, y + 20), 15, 2)
            pygame.draw.line(surface, accent, (x + 24, y + 20), (x + 31, y + 12), 2)
        elif aspect == "eclipse":
            pygame.draw.circle(surface, (7, 5, 20), (x + 24, y + 5), 13)
            pygame.draw.arc(surface, accent, Rect(x + 9, y - 10, 30, 30), 0.2, 5.8, 2)
        elif aspect == "thorn":
            pygame.draw.polygon(surface, accent, [(x + 9, y + 4), (x - 2, y - 8), (x + 14, y - 2)])
            pygame.draw.polygon(surface, accent, [(x + 36, y + 4), (x + 47, y - 8), (x + 31, y - 2)])
        # New Lira details: an asymmetrical shoulder guard, rune belt and a
        # visible vow pendant make the silhouette read at a glance.
        pygame.draw.polygon(surface, (92, 108, 151), [
            (x + 8, y + 34), (x - 2, y + 39), (x + 5, y + 51), (x + 15, y + 47),
        ])
        pygame.draw.polygon(surface, (67, 80, 122), [
            (x + 28, y + 36), (x + 42, y + 42), (x + 36, y + 51), (x + 27, y + 47),
        ])
        pygame.draw.line(surface, accent, (x + 7, y + 47), (x + 36, y + 47), 3)
        for rune_x in (12, 20, 28, 35):
            pygame.draw.circle(surface, (190, 231, 255), (x + rune_x, y + 47), 1)
        pygame.draw.line(surface, (210, 232, 255), (x + 22, y + 35), (x + 22, y + 56), 2)
        pygame.draw.polygon(surface, (255, 225, 164), [
            (x + 22, y + 52), (x + 27, y + 58), (x + 22, y + 64), (x + 17, y + 58),
        ])
        pygame.draw.line(surface, (207, 227, 251), (x + 5, y + 62), (x + 13, y + 69), 3)
        pygame.draw.line(surface, (207, 227, 251), (x + 38, y + 62), (x + 31, y + 69), 3)
        if self.attack_timer > 0:
            swing = smoothstep(1 - self.attack_timer / 0.22)
            radius = 42 + int(swing * 8)
            center = (x + (45 if self.facing > 0 else -2), y + 35)
            draw_glow(surface, center, (198, 239, 255), radius + 14, 40)
            pygame.draw.arc(surface, (220, 246, 255), Rect(center[0] - radius, center[1] - radius, radius * 2, radius * 2),
                            -1.18 if self.facing > 0 else 2.0, 1.18 if self.facing > 0 else 4.42, 5)
            blade_tip = (center[0] + self.facing * (radius + 12), center[1] - 10)
            pygame.draw.line(surface, (255, 255, 255), center, blade_tip, 3)

    def draw_menu(self, surface: Surface, center: tuple[int, int]) -> None:
        x, y = center
        pygame.draw.ellipse(surface, (5, 7, 20), (x - 28, y + 34, 56, 14))
        pygame.draw.polygon(surface, (62, 73, 121), [(x, y - 24), (x - 27, y + 38), (x + 27, y + 38)])
        pygame.draw.polygon(surface, (238, 240, 255), [
            (x - 15, y - 11), (x - 22, y - 42), (x - 5, y - 22), (x, y - 50),
            (x + 6, y - 22), (x + 23, y - 42), (x + 15, y - 8),
        ])
        pygame.draw.ellipse(surface, (17, 21, 44), (x - 14, y - 20, 28, 22))
        pygame.draw.circle(surface, (180, 227, 255), (x - 6, y - 10), 2)
        pygame.draw.circle(surface, (180, 227, 255), (x + 6, y - 10), 2)


@dataclass(frozen=True)
class BossSpec:
    name: str
    title: str
    style: str
    primary: Color
    secondary: Color
    max_health: int
    phases: tuple[str, str, str]


BOSS_SPECS = [
    BossSpec("Rei do Abismo", "A coroa que acorda", "abyss", (232, 53, 91), (76, 21, 82), 180,
             ("Guardião Adormecido", "Asas da Fenda", "Coroa do Abismo")),
    BossSpec("Vespera Tempestade", "A voz dos céus", "storm", (67, 177, 255), (27, 42, 110), 205,
             ("Nuvem Carregada", "Olho da Tempestade", "Juízo Celeste")),
    BossSpec("Colosso Prismático", "A montanha que sangra luz", "crystal", (103, 244, 214), (44, 75, 121), 230,
             ("Pedra Viva", "Prisma Partido", "Explosão Espectral")),
    BossSpec("Matriarca dos Esporos", "A mãe sob as raízes", "fungus", (192, 116, 255), (65, 28, 86), 250,
             ("Jardim Faminto", "Nuvem de Esporos", "Floração Final")),
    BossSpec("Forjador Rubro", "O coração da fornalha", "forge", (255, 101, 43), (108, 29, 24), 275,
             ("Metal Vivo", "Forno Aberto", "Caldeira Solar")),
    BossSpec("Leviatã das Marés", "O abismo tem dentes", "tide", (54, 213, 216), (18, 54, 103), 300,
             ("Maré Baixa", "Onda Negra", "Maré do Fim")),
    BossSpec("Relógio Partido", "Cada segundo é uma lâmina", "clock", (242, 202, 91), (61, 45, 72), 325,
             ("Pêndulo", "Horas Roubadas", "Meia-Noite")),
    BossSpec("Eclipse Nulo", "A luz que esqueceu seu nome", "eclipse", (194, 144, 255), (18, 13, 45), 350,
             ("Sombra Nascente", "Apagão", "Nulo Absoluto")),
    BossSpec("Imperatriz dos Espinhos", "O jardim não perdoa", "thorn", (255, 79, 153), (53, 18, 61), 380,
             ("Semente", "Coroa de Espinhos", "Jardim Imortal")),
    BossSpec("Serafim da Brasa", "O sol caiu dentro da armadura", "inferno", (255, 104, 35), (92, 20, 22), 415,
             ("Cinzas Vivas", "Círculo de Fogo", "Coração em Chamas")),
    BossSpec("Arconte do Último Voto", "A máquina que guarda a despedida", "mecha", (76, 210, 255), (25, 32, 70), 460,
             ("Núcleo Desperto", "Armadura de Guerra", "Ascensão Final")),
]

STORY_LINES = [
    "Lira atravessa o Panteão para cumprir o último voto feito a Noa.",
    "A tempestade guarda uma carta que nunca chegou ao seu destino.",
    "O cristal conserva a primeira promessa dos dois amantes.",
    "Sob os esporos, Lira encontra a canção que Noa cantava para ela.",
    "O Forjador derrete as alianças que tentaram separar o casal.",
    "O Leviatã protege a ponte para o lugar onde Noa espera.",
    "O Relógio Partido oferece voltar no tempo, mas cobra a memória de Lira.",
    "O Eclipse quer apagar o nome de Noa do coração do mundo.",
    "No centro do jardim, o amor de Lira precisa ser escolhido, não herdado.",
    "O Serafim transforma cada passo de Lira em uma faísca de revolta.",
    "No último núcleo, Lira veste a máquina e decide como a despedida termina.",
]


@dataclass
class Hazard:
    position: Vector2
    velocity: Vector2
    radius: int
    color: Color
    damage: int
    lifetime: float
    kind: str
    age: float = 0
    hit: bool = False
    friendly: bool = False
    previous_position: Vector2 | None = None
    armed_after: float = 0.0

    def __post_init__(self) -> None:
        self.previous_position = self.position.copy()
        if self.armed_after <= 0:
            self.armed_after = {
                "lightning": 0.24,
                "mecha_beam": 0.28,
                "enemy_bolt_v": 0.12,
                "enemy_ring_v": 0.18,
                "fire_ring": 0.26,
            }.get(self.kind, 0.0)

    @property
    def rect(self) -> Rect:
        if self.kind == "lightning":
            return Rect(int(self.position.x - 14), 95, 28, GROUND_Y - 95)
        if self.kind == "mecha_beam":
            width = max(12, int(self.radius * (1.0 + self.age * 0.8)))
            return Rect(int(self.position.x - width), 70, width * 2, HEIGHT - 90)
        if self.kind == "fire_ring":
            radius = int(self.radius * (0.72 + min(1.4, self.age * 1.9)))
            return Rect(int(self.position.x - radius), int(self.position.y - radius),
                        radius * 2, radius * 2)
        return Rect(int(self.position.x - self.radius), int(self.position.y - self.radius),
                    self.radius * 2, self.radius * 2)

    def update(self, dt: float) -> bool:
        self.previous_position = self.position.copy()
        self.age += dt
        self.lifetime -= dt
        self.position += self.velocity * dt
        if self.kind in {"fire", "crystal", "spore", "thorn"}:
            self.velocity.y += 240 * dt
        if self.kind == "wave":
            self.position.y += math.sin(self.age * 10) * 1.8
        if self.kind == "plant_bite":
            self.position.y += math.sin(self.age * 5.0) * 0.45
        if self.kind == "lava_wave":
            self.position.y += math.sin(self.age * 8.0) * 0.9
        if self.kind == "shark":
            self.position.y += math.sin(self.age * 6.0) * 1.2
        return self.lifetime > 0 and not self.hit

    @property
    def armed(self) -> bool:
        """Telegraphed hazards only hurt after the warning window."""
        return self.age >= self.armed_after

    @property
    def swept_rect(self) -> Rect:
        previous = self.previous_position or self.position
        current = self.rect
        if self.kind == "lightning":
            return current
        previous_rect = Rect(
            int(previous.x - self.radius), int(previous.y - self.radius),
            self.radius * 2, self.radius * 2,
        )
        return current.union(previous_rect).inflate(8, 8)

    def draw(self, surface: Surface, camera_x: float) -> None:
        x, y = int(self.position.x - camera_x), int(self.position.y)
        if not self.armed and self.kind in {"lightning", "mecha_beam", "enemy_bolt_v", "enemy_ring_v", "fire_ring"}:
            pulse = int(2 + math.sin(self.age * 28) * 2)
            if self.kind == "mecha_beam":
                pygame.draw.line(surface, (255, 135, 58), (x, 78), (x, HEIGHT - 25), 3)
                pygame.draw.line(surface, (255, 239, 171), (x - 18, 78),
                                 (x + 18, 78), 2)
                pygame.draw.circle(surface, (255, 239, 171), (x, HEIGHT - 42),
                                   max(10, self.radius + pulse), 2)
            else:
                pygame.draw.circle(surface, (255, 239, 171), (x, max(78, y)), max(8, self.radius + pulse), 2)
                pygame.draw.line(surface, (255, 198, 99), (x - 18, max(78, y)),
                                 (x + 18, max(78, y)), 2)
            return
        if self.kind == "lightning":
            if int(self.age * 16) % 2 == 0:
                pygame.draw.line(surface, self.color, (x, 95), (x + int(math.sin(self.age * 14) * 13), GROUND_Y), 5)
                pygame.draw.line(surface, (240, 250, 255), (x, 95), (x + int(math.sin(self.age * 14) * 13), GROUND_Y), 2)
        elif self.kind == "wave":
            pygame.draw.arc(surface, self.color, Rect(x - 38, y - 28, 76, 56), 0.2, 2.9, 7)
        elif self.kind == "crystal":
            pygame.draw.polygon(surface, self.color, [(x, y - self.radius), (x + self.radius, y),
                                                       (x, y + self.radius), (x - self.radius, y)])
            pygame.draw.line(surface, (235, 255, 255), (x, y - self.radius + 2), (x, y + 4), 2)
        elif self.kind in {"fire", "spore", "thorn"}:
            pygame.draw.circle(surface, self.color, (x, y), self.radius)
            pygame.draw.circle(surface, (255, 224, 152), (x - self.radius // 3, y - self.radius // 3),
                               max(2, self.radius // 3))
        elif self.kind == "clock":
            pygame.draw.rect(surface, self.color, (x - self.radius, y - self.radius, self.radius * 2, self.radius * 2), 3)
            pygame.draw.line(surface, self.color, (x, y), (x + self.radius, y - self.radius // 2), 3)
        elif self.kind == "player_laser":
            pygame.draw.line(surface, (235, 251, 255), (x - 24, y), (x + 24, y), 5)
            pygame.draw.line(surface, self.color, (x - 28, y), (x + 28, y), 2)
        elif self.kind == "player_laser_v":
            draw_glow(surface, (x, y), self.color, 22, 42)
            pygame.draw.line(surface, (235, 251, 255), (x, y - 26), (x, y + 26), 6)
            pygame.draw.line(surface, self.color, (x, y - 32), (x, y + 32), 3)
            pygame.draw.circle(surface, (255, 255, 255), (x, y - 26), 3)
        elif self.kind == "enemy_bolt_v":
            draw_glow(surface, (x, y), self.color, self.radius * 3, 48)
            pygame.draw.ellipse(surface, self.color,
                                (x - self.radius, y - self.radius * 2,
                                 self.radius * 2, self.radius * 4))
            pygame.draw.line(surface, (255, 244, 202), (x, y - self.radius * 2),
                             (x, y + self.radius * 2), 2)
        elif self.kind == "enemy_ring_v":
            pulse = int(math.sin(self.age * 9) * 4)
            draw_glow(surface, (x, y), self.color, self.radius * 3, 35)
            pygame.draw.circle(surface, self.color, (x, y), self.radius + pulse, 3)
            pygame.draw.circle(surface, (255, 239, 190), (x, y), max(3, self.radius // 3), 2)
        elif self.kind == "storm":
            draw_glow(surface, (x, y), self.color, self.radius * 3, 42)
            pygame.draw.circle(surface, self.color, (x, y), self.radius)
            pygame.draw.circle(surface, (238, 250, 255), (x, y), max(3, self.radius // 3))
            pygame.draw.arc(surface, (238, 250, 255),
                            Rect(x - self.radius - 8, y - self.radius - 8,
                                 (self.radius + 8) * 2, (self.radius + 8) * 2),
                            self.age * 4, self.age * 4 + 2.0, 2)
        elif self.kind == "abyss":
            draw_glow(surface, (x, y), self.color, self.radius * 3, 44)
            pygame.draw.circle(surface, (8, 4, 26), (x, y), self.radius + 4)
            pygame.draw.circle(surface, self.color, (x, y), self.radius, 3)
            pygame.draw.line(surface, (255, 227, 173), (x - self.radius, y),
                             (x + self.radius, y), 2)
        elif self.kind == "eclipse":
            draw_glow(surface, (x, y), self.color, self.radius * 3, 48)
            pygame.draw.circle(surface, (2, 1, 10), (x, y), self.radius)
            pygame.draw.arc(surface, self.color,
                            Rect(x - self.radius - 8, y - self.radius - 8,
                                 (self.radius + 8) * 2, (self.radius + 8) * 2),
                            self.age * 2, self.age * 2 + math.pi * 1.5, 4)
        elif self.kind == "plant_bite":
            draw_glow(surface, (x, y - self.radius), self.color, self.radius * 2, 34)
            stem = max(20, int(self.radius * 1.8))
            pygame.draw.line(surface, (47, 130, 65), (x, y + 18), (x, y - stem), 6)
            mouth = Rect(x - self.radius, y - stem - self.radius // 2,
                         self.radius * 2, self.radius)
            pygame.draw.ellipse(surface, self.color, mouth)
            pygame.draw.arc(surface, (255, 225, 171), mouth.inflate(-4, -2), 0, math.pi, 3)
            for tooth in range(-2, 3):
                pygame.draw.polygon(surface, (246, 238, 190), [
                    (x + tooth * 8, mouth.centery), (x + tooth * 8 + 4, mouth.bottom),
                    (x + tooth * 8 + 8, mouth.centery),
                ])
        elif self.kind == "lava_wave":
            draw_glow(surface, (x, y), self.color, self.radius * 2, 40)
            pygame.draw.arc(surface, self.color,
                            Rect(x - self.radius * 2, y - self.radius * 2,
                                 self.radius * 4, self.radius * 3), 0, math.pi, 9)
            pygame.draw.arc(surface, (255, 237, 137),
                            Rect(x - self.radius * 2 + 8, y - self.radius * 2 + 7,
                                 self.radius * 4 - 16, self.radius * 3 - 14), 0, math.pi, 3)
            for drop in range(4):
                dx = x - self.radius + drop * self.radius // 2
                pygame.draw.circle(surface, (255, 135, 35), (dx, y - 20 - drop * 4), 4 + drop % 2)
        elif self.kind == "shark":
            draw_glow(surface, (x, y), self.color, self.radius * 2, 34)
            pygame.draw.ellipse(surface, self.color,
                                (x - self.radius * 2, y - self.radius, self.radius * 4, self.radius * 2))
            pygame.draw.polygon(surface, self.color, [
                (x - self.radius, y - self.radius), (x - self.radius // 2, y - self.radius * 2),
                (x, y - self.radius),
            ])
            pygame.draw.polygon(surface, self.color, [
                (x - self.radius, y + self.radius), (x - self.radius // 2, y + self.radius * 2),
                (x, y + self.radius),
            ])
            pygame.draw.circle(surface, (255, 244, 201), (x + self.radius, y - 3), 3)
            pygame.draw.arc(surface, (255, 245, 220),
                            Rect(x - self.radius, y - 5, self.radius * 2, 12), 0, math.pi, 2)
        elif self.kind == "fire_ring":
            radius = int(self.radius * (0.72 + min(1.4, self.age * 1.9)))
            draw_glow(surface, (x, y), self.color, radius + 12, 38)
            pygame.draw.circle(surface, self.color, (x, y), radius, 7)
            pygame.draw.circle(surface, (255, 232, 137), (x, y), max(4, radius - 8), 2)
            for flame in range(8):
                angle = self.age * 2.2 + flame * math.tau / 8
                tip = (x + int(math.cos(angle) * (radius + 10)),
                       y + int(math.sin(angle) * (radius + 10)))
                pygame.draw.line(surface, (255, 170, 45), (x + int(math.cos(angle) * radius),
                             y + int(math.sin(angle) * radius)), tip, 3)
        elif self.kind == "mecha_missile":
            draw_glow(surface, (x, y), self.color, self.radius * 3, 42)
            pygame.draw.polygon(surface, self.color, [
                (x, y - self.radius * 2), (x + self.radius, y + self.radius),
                (x, y + self.radius * 2), (x - self.radius, y + self.radius),
            ])
            pygame.draw.line(surface, (255, 240, 185), (x, y - self.radius),
                             (x, y + self.radius), 2)
            pygame.draw.line(surface, (255, 104, 35), (x, y + self.radius * 2),
                             (x, y + self.radius * 3), 4)
        elif self.kind == "mecha_beam":
            width = max(6, int(self.radius * (1.0 + self.age * 0.8)))
            draw_glow(surface, (x, y), self.color, width * 2, 50)
            pygame.draw.line(surface, self.color, (x - width, 80), (x + width, HEIGHT - 35), width)
            pygame.draw.line(surface, (239, 252, 255), (x, 80), (x, HEIGHT - 35), 3)
        else:
            pygame.draw.circle(surface, self.color, (x, y), self.radius)
            pygame.draw.circle(surface, (255, 225, 237), (x - 2, y - 2), max(2, self.radius // 3))


class PantheonBoss:
    def __init__(self, spec: BossSpec) -> None:
        self.spec = spec
        self.position = Vector2(770, GROUND_Y - 112)
        self.width = 68
        self.height = 112
        self.velocity = Vector2()
        self.health = spec.max_health
        self.phase = 1
        self.attack_timer = 0
        self.attack_cooldown = 0.65
        self.invulnerable = 0
        self.transition_timer = 0
        self.anim_time = 0
        self.facing = -1
        self.flight_time = 0
        self.hit_flash = 0.0
        self.shield_max = 70 + spec.max_health // 5
        self.shield = self.shield_max
        self.shield_broken = False
        self.shield_break_timer = 0.0
        self.damage_marks: list[tuple[float, float, float]] = []
        self.blood_drips: list[tuple[float, float, float]] = []
        self.crown_damage = 0
        self.attack_style = spec.style
        self.attack_duration = 0.42

    @property
    def rect(self) -> Rect:
        return Rect(int(self.position.x), int(self.position.y), self.width, self.height)

    @property
    def attack_rect(self) -> Rect:
        reach = 75 + self.phase * 18
        offset = self.width if self.facing > 0 else -reach
        return Rect(int(self.position.x + offset), int(self.position.y + self.height * 0.28),
                    int(reach), int(42 + self.phase * 8))

    @property
    def phase_name(self) -> str:
        return self.spec.phases[self.phase - 1]

    def take_damage(self, amount: int, particles: list[Particle]) -> bool:
        if self.invulnerable > 0 or self.transition_timer > 0:
            return False
        remaining = amount
        if self.shield > 0:
            absorbed = min(self.shield, remaining)
            self.shield -= absorbed
            remaining -= absorbed
            self.shield_break_timer = 0.14
            if self.shield <= 0 and not self.shield_broken:
                self.shield_broken = True
                self.crown_damage += 1
                self.invulnerable = 0.26
                for _ in range(26):
                    angle = random.uniform(0, math.tau)
                    speed = random.uniform(110, 320)
                    particles.append(Particle(Vector2(self.rect.center),
                                              Vector2(math.cos(angle) * speed, math.sin(angle) * speed),
                                              (145, 220, 255), random.uniform(2, 6), 0.9, 30))
        self.health = max(0, self.health - remaining)
        self.invulnerable = 0.18
        self.hit_flash = 0.16
        if remaining > 0:
            mark = (random.uniform(0.15, 0.85), random.uniform(0.18, 0.82), 1.0)
            self.damage_marks.append(mark)
            self.damage_marks = self.damage_marks[-8:]
            self.blood_drips.append((random.uniform(0.2, 0.8), random.uniform(0.2, 0.7), 1.0))
            self.blood_drips = self.blood_drips[-8:]
        for _ in range(9):
            particles.append(Particle(
                Vector2(self.rect.center),
                Vector2(random.uniform(-160, 160), random.uniform(-170, 70)),
                self.spec.primary, random.uniform(2, 5), 0.5, 300,
            ))
        return True

    def transform(self, particles: list[Particle]) -> None:
        self.phase += 1
        self.transition_timer = 2.2
        feet = self.position.y + self.height
        self.width = 68 + self.phase * 16
        self.height = 112 + self.phase * 24
        self.position.y = feet - self.height
        self.velocity = Vector2(0, -80 if self.phase >= 2 else 0)
        for _ in range(60 if self.phase == 2 else 90):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(90, 360)
            particles.append(Particle(
                Vector2(self.rect.center),
                Vector2(math.cos(angle) * speed, math.sin(angle) * speed),
                self.spec.primary if random.random() < 0.7 else self.spec.secondary,
                random.uniform(2, 8), random.uniform(0.7, 1.9), 100,
            ))

    def spawn_attack(self, player: Player, hazards: list[Hazard]) -> None:
        direction = 1 if player.position.x > self.position.x else -1
        center = Vector2(self.rect.center)
        style = self.spec.style
        damage = 8 + self.phase * 3
        self.attack_style = style
        self.attack_duration = 0.34 if self.phase == 1 else 0.48 if self.phase == 2 else 0.62
        if style == "storm":
            hazards.append(Hazard(Vector2(player.rect.centerx, 0), Vector2(), 14, self.spec.primary, damage + 3, 0.75, "lightning"))
            for offset in (-90, 0, 90):
                hazards.append(Hazard(center + Vector2(offset, 0), Vector2(direction * 125, 0), 15,
                                      self.spec.secondary, damage, 2.5, "storm"))
        elif style == "crystal":
            for spread in (-220, -110, 0, 110, 220):
                hazards.append(Hazard(center, Vector2(direction * 200 + spread, random.uniform(-280, -120)),
                                      13, self.spec.primary, damage, 2.1, "crystal"))
        elif style == "fungus":
            for _ in range(5):
                hazards.append(Hazard(center, Vector2(random.uniform(-120, 120), random.uniform(-310, -180)),
                                      14, self.spec.primary, damage, 3.1, "spore"))
            for offset in (-150, 0, 150):
                hazards.append(Hazard(Vector2(player.position.x + offset, GROUND_Y - 18),
                                      Vector2(), 24, (104, 207, 92), damage + 2, 2.8, "plant_bite"))
        elif style == "forge":
            for spread in (-75, 0, 75):
                hazards.append(Hazard(center, Vector2(direction * 230, spread - 80), 17,
                                      self.spec.primary, damage + 2, 2.5, "fire"))
            hazards.append(Hazard(Vector2(self.position.x + direction * 120, GROUND_Y - 24),
                                  Vector2(direction * 190, 0), 44, (233, 74, 27),
                                  damage + 5, 3.0, "lava_wave"))
        elif style == "tide":
            for index in range(3):
                hazards.append(Hazard(Vector2(self.position.x + direction * 35, GROUND_Y - 30 - index * 24),
                                      Vector2(direction * (180 + index * 45), 0), 27,
                                      self.spec.primary, damage, 3, "wave"))
            hazards.append(Hazard(Vector2(self.position.x + direction * 80, GROUND_Y - 62),
                                  Vector2(direction * 260, 0), 24, (66, 160, 207),
                                  damage + 4, 3.4, "shark"))
        elif style == "clock":
            for angle in (0, math.pi * 0.5, math.pi, math.pi * 1.5):
                hazards.append(Hazard(center + Vector2(math.cos(angle) * 54, math.sin(angle) * 54),
                                      Vector2(direction * 80, 0), 16, self.spec.primary, damage, 2.4, "clock"))
        elif style == "eclipse":
            hazards.append(Hazard(center + Vector2(direction * 28, 0), Vector2(direction * 120, 0), 31,
                                  self.spec.secondary, damage + 4, 3.4, "eclipse"))
            hazards.append(Hazard(Vector2(player.rect.center), Vector2(), 16, self.spec.primary, damage, 0.9, "lightning"))
        elif style == "thorn":
            for spread in (-160, -80, 0, 80, 160):
                hazards.append(Hazard(center, Vector2(direction * 180 + spread, random.uniform(-240, -90)),
                                      13, self.spec.primary, damage, 2.7, "thorn"))
        elif style == "inferno":
            hazards.append(Hazard(Vector2(player.rect.center), Vector2(), 28,
                                  self.spec.primary, damage + 5, 1.35, "fire_ring"))
            for offset in (-145, 0, 145):
                hazards.append(Hazard(Vector2(self.position.x + direction * 75, GROUND_Y - 28),
                                      Vector2(direction * (170 + self.phase * 30), 0), 34,
                                      self.spec.secondary, damage + 4, 2.8, "lava_wave"))
            for spread in (-125, -42, 42, 125):
                hazards.append(Hazard(center, Vector2(direction * 150 + spread, -280),
                                      15, self.spec.primary, damage, 2.4, "fire"))
        elif style == "mecha":
            for offset in (-150, -75, 0, 75, 150):
                hazards.append(Hazard(Vector2(center.x + offset, 35), Vector2(0, 245),
                                      13, self.spec.primary, damage + 2, 2.6, "mecha_missile"))
            hazards.append(Hazard(Vector2(player.rect.centerx, 0), Vector2(), 18,
                                  self.spec.primary, damage + 5, 0.8, "mecha_beam"))
        else:
            for spread in (-45, 0, 45):
                hazards.append(Hazard(center, Vector2(direction * 240, spread - 50), 16,
                                      self.spec.primary, damage, 2.3, "abyss"))

    def spawn_vertical_attack(self, player: Player, hazards: list[Hazard]) -> None:
        """Dense vertical-shooter patterns, aimed from the top of the screen."""
        center = Vector2(self.position.x + self.width * 0.5, self.position.y + self.height * 0.5)
        damage = 8 + self.phase * 3
        if self.spec.style == "storm":
            for offset in (-180, -90, 0, 90, 180):
                hazards.append(Hazard(Vector2(center.x + offset, 0), Vector2(0, 330),
                                      12, self.spec.primary, damage, 2.6, "lightning"))
            for offset in (-120, 0, 120):
                hazards.append(Hazard(Vector2(center.x + offset, 105), Vector2(0, 270),
                                      13, self.spec.secondary, damage + 2, 2.4, "enemy_bolt_v"))
        elif self.spec.style == "tide":
            for lane in range(5):
                x = 130 + lane * 175
                hazards.append(Hazard(Vector2(x, -30), Vector2(0, 190 + lane * 25),
                                      25, self.spec.primary, damage, 3.8, "wave"))
            hazards.append(Hazard(Vector2(player.rect.centerx, -50), Vector2(0, 250),
                                  17, self.spec.secondary, damage + 3, 2.6, "enemy_ring_v"))
        elif self.spec.style == "inferno":
            for lane in range(4):
                x = 170 + lane * 210
                hazards.append(Hazard(Vector2(x, HEIGHT - 10), Vector2(0, -165 - lane * 20),
                                      24, self.spec.primary, damage + 2, 2.7, "fire"))
            hazards.append(Hazard(Vector2(player.rect.centerx, HEIGHT // 2), Vector2(),
                                  22, self.spec.primary, damage + 5, 1.5, "fire_ring"))
        elif self.spec.style == "mecha":
            for offset in (-210, -105, 0, 105, 210):
                hazards.append(Hazard(Vector2(center.x + offset, -30), Vector2(0, 300),
                                      14, self.spec.primary, damage + 2, 2.4, "mecha_missile"))
            hazards.append(Hazard(Vector2(player.rect.centerx, 0), Vector2(), 20,
                                  self.spec.primary, damage + 7, 1.0, "mecha_beam"))
        else:
            aimed_x = player.rect.centerx
            for offset in (-150, -75, 0, 75, 150):
                hazards.append(Hazard(Vector2(center.x + offset, 70), Vector2(offset * 0.14, 255),
                                      11, self.spec.primary, damage, 2.8, "enemy_bolt_v"))
            hazards.append(Hazard(Vector2(aimed_x, -20), Vector2(0, 290),
                                  20, self.spec.secondary, damage + 4, 2.6, "enemy_ring_v"))

    def update(
        self,
        dt: float,
        player: Player,
        platforms: list[Rect],
        hazards: list[Hazard],
        particles: list[Particle],
    ) -> tuple[bool, bool]:
        phase_started = False
        attack_started = False
        self.anim_time += dt
        self.attack_timer = max(0, self.attack_timer - dt)
        self.attack_cooldown = max(0, self.attack_cooldown - dt)
        self.invulnerable = max(0, self.invulnerable - dt)
        self.hit_flash = max(0, self.hit_flash - dt)
        self.shield_break_timer = max(0, self.shield_break_timer - dt)
        self.blood_drips = [(x, length, life - dt * 0.03)
                            for x, length, life in self.blood_drips if life - dt * 0.03 > 0]

        threshold = self.spec.max_health * (0.66 if self.phase == 1 else 0.33)
        if self.health <= threshold and self.phase < 3:
            self.transform(particles)
            phase_started = True
        self.transition_timer = max(0, self.transition_timer - dt)
        if self.transition_timer > 0:
            return phase_started, False

        distance_x = player.position.x - self.position.x
        flight = self.phase >= 2 or self.spec.style in {"storm", "tide", "eclipse"}
        speed = 170 + self.phase * 78 + (42 if self.spec.style in {"clock", "storm"} else 0)
        distance_y = player.position.y - self.position.y
        if flight:
            self.flight_time += dt
            target_y = clamp(player.position.y - 125 + math.sin(self.flight_time * (2.2 + self.phase * 0.3)) * 54,
                             70, GROUND_Y - self.height - 15)
            self.velocity.y = (target_y - self.position.y) * 3.8
        else:
            self.velocity.y += 1450 * dt

        attack_range = 180 + self.phase * 24
        if math.hypot(distance_x, distance_y) > attack_range:
            self.facing = 1 if distance_x > 0 else -1
            self.velocity.x = self.facing * speed
        else:
            self.velocity.x *= max(0, 1 - 10 * dt)
        # Ranged guardians must never go passive just because Lira is centered.
        # They keep attacking while repositioning, so the arena always has a pulse.
        if self.attack_cooldown <= 0:
            self.facing = 1 if distance_x >= 0 else -1
            self.attack_duration = 0.30 if self.phase == 1 else 0.42 if self.phase == 2 else 0.54
            self.attack_timer = self.attack_duration
            self.attack_cooldown = max(0.26, 0.72 - self.phase * 0.12)
            self.spawn_attack(player, hazards)
            attack_started = True

        previous_bottom = self.position.y + self.height
        self.position.x = clamp(self.position.x + self.velocity.x * dt, 350, WORLD_WIDTH - self.width - 25)
        self.position.y += self.velocity.y * dt
        if not flight:
            landing = land_on_platform(self.position, previous_bottom, self.velocity.y, self.width, self.height, platforms)
            if landing is not None:
                self.position.y = landing.top - self.height
                self.velocity.y = 0
        return phase_started, attack_started

    def draw(self, surface: Surface, camera_x: float) -> None:
        x, y = int(self.position.x - camera_x), int(self.position.y)
        center_x, feet_y = x + self.width // 2, y + self.height
        pulse = math.sin(self.anim_time * (7 + self.phase * 2))
        hover = int(math.sin(self.anim_time * 2.3) * (2 + self.phase))
        y += hover
        if self.hit_flash > 0:
            flash = Surface((self.width + 130, self.height + 140), pygame.SRCALPHA)
            flash.fill((255, 255, 255, int(180 * self.hit_flash / 0.16)))
            surface.blit(flash, (center_x - flash.get_width() // 2, y - 70))
        draw_glow(surface, (center_x, y + 55), self.spec.primary, int(72 + self.phase * 16 + pulse * 4), 46)
        if self.shield > 0:
            shield_ratio = self.shield / max(1, self.shield_max)
            shield_radius = int(70 + self.phase * 12 + pulse * 3)
            shield_alpha = 120 if self.shield_break_timer <= 0 else 220
            pygame.draw.circle(surface, (*self.spec.primary, shield_alpha),
                               (center_x, y + 56), shield_radius, 3)
            pygame.draw.arc(surface, (210, 245, 255),
                            Rect(center_x - shield_radius - 6, y + 50 - shield_radius,
                                 (shield_radius + 6) * 2, (shield_radius + 6) * 2),
                            -1.1, -1.1 + math.tau * shield_ratio, 4)
        elif self.shield_broken:
            for shard in range(7):
                angle = self.anim_time * 0.7 + shard * math.tau / 7
                sx = center_x + int(math.cos(angle) * (68 + shard * 4))
                sy = y + 56 + int(math.sin(angle) * (68 + shard * 4))
                pygame.draw.line(surface, (148, 222, 255), (center_x, y + 56), (sx, sy), 1)
        pygame.draw.ellipse(surface, (6, 6, 18), (center_x - self.width // 2, feet_y - 8, self.width, 20))
        if self.phase >= 2:
            for side in (-1, 1):
                pygame.draw.polygon(surface, self.spec.secondary, [
                    (center_x + side * 22, y + 55),
                    (center_x + side * (92 + self.phase * 12), y + 18 + int(pulse * 10)),
                    (center_x + side * (65 + self.phase * 8), y + 80),
                    (center_x + side * 26, y + 90),
                ])
            pygame.draw.circle(surface, (*self.spec.primary, 45), (center_x, y + 54), int(self.width * 0.9 + pulse * 3))
            wing_sweep = int(math.sin(self.anim_time * 3.7) * 12)
            for side in (-1, 1):
                pygame.draw.line(surface, self.spec.primary, (center_x + side * 28, y + 50),
                                 (center_x + side * (92 + self.phase * 12), y + 25 + wing_sweep * side), 3)
        cloak = self.spec.secondary if self.phase == 1 else self.spec.primary
        pygame.draw.polygon(surface, cloak, [
            (center_x, y + 28), (center_x - self.width // 2, feet_y - 5), (center_x + self.width // 2, feet_y - 5),
        ])
        pygame.draw.polygon(surface, self.spec.primary, [
            (center_x, y + 32), (center_x - self.width // 4, feet_y - 12), (center_x + self.width // 4, feet_y - 12),
        ])
        head_w = int(self.width * 0.62)
        head = Rect(center_x - head_w // 2, y + 14, head_w, int(self.height * 0.25))
        pygame.draw.ellipse(surface, (220, 228, 246), head)
        horn = 12 + self.phase * 5
        pygame.draw.polygon(surface, (235, 241, 255), [
            (head.left + 8, head.top + 10), (head.left - horn, head.top - horn),
            (center_x - 5, head.top + 7), (center_x, head.top - horn - 9),
            (center_x + 5, head.top + 7), (head.right + horn, head.top - horn),
            (head.right - 8, head.top + 10),
        ])
        pygame.draw.ellipse(surface, (13, 11, 31), head.inflate(-10, -7))
        eye = self.spec.primary if self.phase > 1 else (255, 224, 139)
        draw_glow(surface, (center_x, head.centery), eye, 24 + self.phase * 3, 52)
        pygame.draw.circle(surface, eye, (center_x - 8, head.centery), 3 + self.phase)
        pygame.draw.circle(surface, eye, (center_x + 8, head.centery), 3 + self.phase)
        brow_drop = 2 + self.phase
        pygame.draw.line(surface, (24, 12, 38),
                         (center_x - 16, head.centery - 7),
                         (center_x - 3, head.centery - 7 + brow_drop), 3)
        pygame.draw.line(surface, (24, 12, 38),
                         (center_x + 3, head.centery - 7 + brow_drop),
                         (center_x + 16, head.centery - 7), 3)
        mouth_y = head.centery + 10
        pygame.draw.arc(surface, (38, 12, 42),
                        Rect(center_x - 12, mouth_y - 3, 24, 13),
                        math.pi, math.tau, 2)
        # Every guardian has a readable silhouette: arms, hands and a pose, not a floating mask.
        arm_sway = int(math.sin(self.anim_time * 3.0) * 12)
        attack_pose = int((1.0 - self.attack_timer / max(0.01, self.attack_duration)) * 28) if self.attack_timer > 0 else 0
        left_hand = (center_x - 46 - arm_sway, y + 64 + self.phase * 6 - attack_pose // 3)
        right_hand = (center_x + 46 + arm_sway + self.facing * attack_pose, y + 62 - self.phase * 4)
        pygame.draw.line(surface, self.spec.secondary, (center_x - 22, y + 45), left_hand, 11)
        pygame.draw.line(surface, self.spec.secondary, (center_x + 22, y + 45), right_hand, 11)
        pygame.draw.circle(surface, self.spec.primary, left_hand, 11)
        pygame.draw.circle(surface, self.spec.primary, right_hand, 11)
        if self.spec.style in {"fungus", "thorn"}:
            for side in (-1, 1):
                for finger in range(3):
                    hx, hy = (left_hand if side < 0 else right_hand)
                    pygame.draw.line(surface, self.spec.primary, (hx, hy),
                                     (hx + side * (14 + finger * 4), hy + 10 + finger * 3), 3)
        if self.damage_marks:
            for mark_x, mark_y, life in self.damage_marks:
                sx = center_x + int((mark_x - 0.5) * self.width)
                sy = y + int(mark_y * self.height)
                pygame.draw.line(surface, (92, 18, 48), (sx, sy),
                                 (sx + 8, sy + 12), 2)
                pygame.draw.line(surface, (192, 38, 74), (sx + 8, sy + 12),
                                 (sx + 4, sy + 24), 2)
        for drip_x, length, life in self.blood_drips:
            sx = center_x + int((drip_x - 0.5) * self.width)
            sy = y + int(46 * self.height / 112)
            pygame.draw.line(surface, (137, 24, 50), (sx, sy),
                             (sx + 2, sy + int(25 * length)), 2)
            pygame.draw.circle(surface, (190, 36, 65),
                               (sx + 2, sy + int(25 * length) + 2), 2)

        style = self.spec.style
        if style == "crystal":
            for angle in (-0.7, 0, 0.7):
                pygame.draw.polygon(surface, self.spec.primary, [
                    (center_x, y + 4), (center_x + int(math.cos(angle) * 34), y - 38),
                    (center_x + int(math.cos(angle) * 12), y + 18),
                ])
        elif style == "storm":
            pygame.draw.line(surface, (235, 250, 255), (center_x - 35, y + 35), (center_x - 60, y - 20), 3)
            pygame.draw.line(surface, (235, 250, 255), (center_x + 35, y + 35), (center_x + 60, y - 20), 3)
        elif style == "fungus":
            pygame.draw.ellipse(surface, self.spec.primary, (center_x - 46, y - 13, 92, 25))
            for mushroom_x in (-24, 0, 24):
                pygame.draw.line(surface, self.spec.primary, (center_x + mushroom_x, y - 4),
                                 (center_x + mushroom_x, y - 30), 6)
        elif style == "forge":
            pygame.draw.polygon(surface, (255, 211, 92), [
                (center_x - 36, y + 10), (center_x - 18, y - 32), (center_x, y + 2),
                (center_x + 22, y - 42), (center_x + 38, y + 12),
            ])
        elif style == "tide":
            pygame.draw.arc(surface, self.spec.primary, Rect(center_x - 70, y - 18, 140, 105), math.pi, math.tau, 5)
        elif style == "clock":
            radius = 42 + self.phase * 4
            pygame.draw.circle(surface, self.spec.primary, (center_x, y + 40), radius, 3)
            pygame.draw.line(surface, self.spec.primary, (center_x, y + 40),
                             (center_x + int(math.sin(self.anim_time) * radius), y + 40 - int(math.cos(self.anim_time) * radius)), 3)
        elif style == "eclipse":
            pygame.draw.circle(surface, (4, 3, 15), (center_x, y - 13), 30 + self.phase * 4)
            pygame.draw.arc(surface, self.spec.primary, Rect(center_x - 45, y - 58, 90, 90), 0, math.pi * 2, 4)
        elif style == "thorn":
            for side in (-1, 1):
                for offset in (0, 24, 48):
                    pygame.draw.polygon(surface, self.spec.primary, [
                        (center_x + side * (self.width // 3), y + 42 + offset),
                        (center_x + side * (self.width // 2 + 14), y + 34 + offset),
                        (center_x + side * (self.width // 3), y + 57 + offset),
                    ])
        if self.spec.style == "abyss" or self.crown_damage > 0:
            crown_y = y - 36
            crown_color = (255, 211, 116) if not self.shield_broken else (169, 103, 87)
            pygame.draw.line(surface, crown_color, (center_x - 25, crown_y + 15),
                             (center_x + 25, crown_y + 15), 4)
            crown_points = [(center_x - 24, crown_y + 13), (center_x - 18, crown_y - 12),
                            (center_x - 4, crown_y + 4), (center_x + 5, crown_y - 20),
                            (center_x + 15, crown_y + 5), (center_x + 27, crown_y - 8),
                            (center_x + 24, crown_y + 16)]
            pygame.draw.lines(surface, crown_color, False, crown_points, 3)
            if self.crown_damage > 0:
                pygame.draw.line(surface, (55, 18, 38), (center_x + 2, crown_y - 17),
                                 (center_x + 12, crown_y + 10), 3)
        if self.phase == 3:
            # Cada apoteose troca a silhueta, não só a cor.
            if style == "abyss":
                for side in (-1, 1):
                    pygame.draw.polygon(surface, (255, 218, 150), [
                        (center_x, y - 30), (center_x + side * 58, y - 70),
                        (center_x + side * 35, y - 5),
                    ])
            elif style == "storm":
                for offset in (-25, 0, 25):
                    pygame.draw.line(surface, (240, 250, 255), (center_x + offset, y - 48),
                                     (center_x + offset - 14, y + 16), 3)
            elif style == "crystal":
                for side in (-1, 1):
                    pygame.draw.polygon(surface, (225, 255, 250), [
                        (center_x, y + 50), (center_x + side * 74, y + 15),
                        (center_x + side * 46, y + 72),
                    ])
            elif style == "fungus":
                for side in (-1, 1):
                    pygame.draw.ellipse(surface, self.spec.secondary,
                                        (center_x + side * 62 - 24, y + 10, 48, 90))
            elif style == "forge":
                draw_glow(surface, (center_x, y + 38), (255, 226, 100), 70, 55)
                pygame.draw.circle(surface, (255, 236, 132), (center_x, y + 40), 18)
            elif style == "tide":
                for side in (-1, 1):
                    pygame.draw.arc(surface, self.spec.primary,
                                    Rect(center_x + side * 32 - 62, y - 55, 124, 130),
                                    math.pi * (0.1 if side > 0 else 0.9),
                                    math.pi * (1.3 if side > 0 else 1.9), 7)
            elif style == "clock":
                for angle in range(0, 360, 45):
                    radians = math.radians(angle) + self.anim_time * 0.2
                    pygame.draw.line(surface, self.spec.primary, (center_x, y + 40),
                                     (center_x + int(math.cos(radians) * 68),
                                      y + 40 + int(math.sin(radians) * 68)), 2)
            elif style == "eclipse":
                draw_glow(surface, (center_x, y + 28), self.spec.primary, 88, 60)
                pygame.draw.circle(surface, (2, 1, 9), (center_x, y + 28), 42)
            elif style == "thorn":
                pygame.draw.arc(surface, self.spec.primary, Rect(center_x - 90, y - 48, 180, 170),
                                math.pi, math.tau, 8)

        if self.attack_timer > 0:
            attack_progress = 1.0 - self.attack_timer / max(0.01, self.attack_duration)
            radius = 54 + self.phase * 12
            attack_center = (center_x + (self.width // 2 + 16 if self.facing > 0 else -(self.width // 2 + 16)),
                             y + int(self.height * 0.45))
            draw_glow(surface, attack_center, self.spec.primary, radius + 30, 35)
            pygame.draw.arc(surface, self.spec.primary,
                            Rect(attack_center[0] - radius, attack_center[1] - radius, radius * 2, radius * 2),
                            -1.1 if self.facing > 0 else 2.04, 1.1 if self.facing > 0 else 4.24,
                            8 if self.phase == 3 else 5)
            # Ataque com telegraph e follow-through: cada domínio ganha uma assinatura visual.
            if self.attack_style == "storm":
                for bolt in (-1, 0, 1):
                    pygame.draw.line(surface, (242, 252, 255),
                                     (center_x + bolt * 22, y + 6),
                                     (center_x + bolt * 34 + int(math.sin(self.anim_time * 22 + bolt) * 10),
                                      y + 62), 2)
            elif self.attack_style == "crystal":
                for shard in range(3):
                    offset = int((attack_progress * 90 + shard * 24) * self.facing)
                    pygame.draw.polygon(surface, (226, 255, 249), [
                        (attack_center[0] + offset, attack_center[1] - 22),
                        (attack_center[0] + offset + self.facing * 18, attack_center[1]),
                        (attack_center[0] + offset, attack_center[1] + 22),
                    ])
            elif self.attack_style == "fungus":
                for spore in range(5):
                    angle = self.anim_time * 2.0 + spore * math.tau / 5
                    sx = attack_center[0] + int(math.cos(angle) * (radius - 8))
                    sy = attack_center[1] + int(math.sin(angle) * (radius - 8))
                    pygame.draw.circle(surface, self.spec.primary, (sx, sy), 4 + spore % 3)
            elif self.attack_style == "forge":
                pygame.draw.circle(surface, (255, 223, 100), attack_center,
                                   max(4, int(radius * attack_progress)), 4)
                pygame.draw.line(surface, (255, 246, 195), attack_center,
                                 (attack_center[0] + self.facing * int(radius * 1.25),
                                  attack_center[1] - int(radius * 0.45)), 5)
            elif self.attack_style == "tide":
                for wave in range(3):
                    wave_radius = int(radius * (0.65 + wave * 0.28) + attack_progress * 30)
                    pygame.draw.arc(surface, self.spec.primary,
                                    Rect(attack_center[0] - wave_radius, attack_center[1] - wave_radius // 2,
                                         wave_radius * 2, wave_radius), 0.1, 2.9, 4)
            elif self.attack_style == "clock":
                for angle in range(0, 360, 45):
                    radians = math.radians(angle) + self.anim_time * 2
                    pygame.draw.line(surface, self.spec.primary, attack_center,
                                     (attack_center[0] + int(math.cos(radians) * radius),
                                      attack_center[1] + int(math.sin(radians) * radius)), 2)
            elif self.attack_style == "eclipse":
                pygame.draw.line(surface, self.spec.primary, (center_x, y + 30),
                                 (center_x + self.facing * int(140 + attack_progress * 90), y + 30), 8)
                pygame.draw.line(surface, (245, 240, 255), (center_x, y + 30),
                                 (center_x + self.facing * int(140 + attack_progress * 90), y + 30), 2)
            elif self.attack_style == "thorn":
                for thorn in range(4):
                    tx = attack_center[0] + self.facing * int(20 + thorn * 24 + attack_progress * 45)
                    pygame.draw.polygon(surface, self.spec.primary, [
                        (tx, attack_center[1]), (tx + self.facing * 22, attack_center[1] - 10),
                        (tx + self.facing * 14, attack_center[1] + 10),
                    ])
            elif self.attack_style == "inferno":
                for ring in range(3):
                    ring_radius = int(radius * (0.45 + ring * 0.28 + attack_progress * 0.3))
                    pygame.draw.circle(surface, (255, 90 + ring * 40, 35),
                                       attack_center, ring_radius, 4)
            elif self.attack_style == "mecha":
                pygame.draw.line(surface, (230, 250, 255), attack_center,
                                 (attack_center[0] + self.facing * int(radius * 1.7),
                                  attack_center[1] - int(radius * 0.12)), 8)
                pygame.draw.line(surface, self.spec.primary, attack_center,
                                 (attack_center[0] + self.facing * int(radius * 1.7),
                                  attack_center[1] - int(radius * 0.12)), 3)


class PantheonGame:
    def __init__(self) -> None:
        pygame.mixer.pre_init(44100, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("Ecos do Abismo — Panteão")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.audio = AudioSystem()
        self.running = True
        self.mode = "menu"
        self.player = Player()
        self.boss: PantheonBoss | None = None
        self.hazards: list[Hazard] = []
        self.particles: list[Particle] = []
        self.blood_pools: list[tuple[Vector2, float, Color]] = []
        self.potions: list[HealthPotion] = []
        self.platforms: list[Rect] = []
        self.selected_boss = 0
        self.unlocked_count = 1
        self.camera_x = 0
        self.elapsed = 0
        self.screen_shake = 0
        self.flash_timer = 0.0
        self.flash_color: Color = (255, 255, 255)
        self.banner_timer = 0
        self.banner_text = ""
        self.dimension_mode = "2d"
        self.qte_active = False
        self.qte_done = False
        self.qte_timer = 0
        self.qte_hits = 0
        self.qte_target = 18
        self.qte_success = False
        self.qte_pending = False
        self.qte_anim = 0.0
        self.qte_hit_flash = 0.0
        self.qte_last_side = 1
        self.qte_lunge = 0.0
        self.qte_clash = 0.0
        self.genre_title = ""
        self.victory_active = False
        self.victory_timer = 0.0
        self.victory_total = 0.0
        self.victory_style = "abyss"
        self.victory_seed = 0.0
        self.intro_timer = 0.0
        self.intro_total = 0.0
        self.intro_phase = 1
        self.intro_style = "abyss"
        self.domain_active = False
        self.domain_timer = 0.0
        self.domain_total = 0.0
        self.domain_text = ""
        self.domain_voice = ""
        self.notice_timer = 0
        self.notice = ""
        self.finale_entry_timer = 0.0
        self.finale_entry_total = 0.0
        self.finale_active = False
        self.finale_timer = 0.0
        self.finale_hits = 0
        self.finale_target = 28
        self.finale_health_max = 720
        self.finale_strike_flash = 0.0
        self.finale_combo = 0
        self.finale_execution_ready = False
        self.finale_execution_active = False
        self.finale_execution_timer = 0.0
        self.finale_execution_total = 3.8
        self.finale_execution_flash = 0.0
        self.finale_attack_cooldown = 0.0
        self.finale_attack_target_x = 0.0
        self.hit_stop = 0.0
        self.combat_feedback_timer = 0.0
        self.combat_feedback = ""
        self.jump_was_down = False
        self.attack_was_down = False
        self.load_progress()
        self.audio.start("menu")

    def load_progress(self) -> None:
        try:
            data = json.loads(SAVE_FILE.read_text(encoding="utf-8"))
            # Test build: every guardian is available from the menu.
            self.unlocked_count = len(BOSS_SPECS)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.unlocked_count = len(BOSS_SPECS)

    def save_progress(self) -> None:
        try:
            SAVE_FILE.write_text(json.dumps({"unlocked": self.unlocked_count}, indent=2), encoding="utf-8")
        except OSError:
            pass

    def set_notice(self, text: str, duration: float = 1.7) -> None:
        self.notice = text
        self.notice_timer = duration

    def trigger_hit_stop(self, duration: float, feedback: str = "") -> None:
        """Briefly freezes the action so hits read as deliberate events."""
        self.hit_stop = max(self.hit_stop, duration)
        if feedback:
            self.combat_feedback = feedback
            self.combat_feedback_timer = 0.32

    def add_blood_pool(self, position: Vector2, color: Color = (150, 25, 52)) -> None:
        self.blood_pools.append((Vector2(position), random.uniform(7, 18), color))
        self.blood_pools = self.blood_pools[-24:]

    def begin_phase_intro(self, phase: int) -> None:
        if self.boss is None:
            return
        self.intro_phase = phase
        self.intro_style = self.boss.spec.style
        self.intro_total = 2.65 if phase == 1 else 2.35
        self.intro_timer = self.intro_total
        self.banner_timer = self.intro_total
        self.banner_text = self.boss.spec.phases[phase - 1]
        self.audio.play("transform")
        self.screen_shake = max(self.screen_shake, 0.38 if phase == 1 else 0.72)
        self.flash_timer = max(self.flash_timer, 0.35)
        self.flash_color = self.boss.spec.primary
        for _ in range(32 if phase == 1 else 72):
            self.particles.append(Particle(
                Vector2(random.uniform(self.camera_x, self.camera_x + WIDTH), random.uniform(80, HEIGHT)),
                Vector2(random.uniform(-120, 120), random.uniform(-290, -55)),
                self.boss.spec.primary if random.random() < 0.72 else self.boss.spec.secondary,
                random.uniform(2, 8), random.uniform(0.8, 1.8), 80,
            ))

    def start_domain_expansion(self) -> None:
        if self.boss is None:
            return
        names = {
            "abyss": "CATEDRAL DO VAZIO",
            "storm": "TRONO DA TEMPESTADE",
            "crystal": "CATEDRAL DOS PRISMAS",
            "fungus": "JARDIM DA FOME",
            "forge": "MARÉ DA FORNALHA",
            "tide": "OCEANO QUE DEVORA",
            "clock": "MEIA-NOITE INFINITA",
            "eclipse": "SOL SEM NOME",
            "thorn": "JARDIM DO ÚLTIMO ESPINHO",
        }
        self.domain_active = True
        self.domain_total = 3.8
        self.domain_timer = self.domain_total
        self.domain_text = names.get(self.boss.spec.style, "DOMÍNIO ABSOLUTO")
        self.domain_voice = "EXPANSÃO DE DOMÍNIO"
        self.intro_timer = 0
        self.flash_timer = 0.85
        self.flash_color = self.boss.spec.primary
        self.screen_shake = max(self.screen_shake, 1.0)
        self.hazards.clear()
        self.audio.play("transform")

    def update_domain_expansion(self, dt: float) -> None:
        if self.boss is None:
            return
        self.domain_timer = max(0, self.domain_timer - dt)
        self.boss.anim_time += dt
        self.player.walk_time += dt * 5
        target_x = WIDTH * 0.42 if self.dimension_mode == "shooter" else self.camera_x + WIDTH * 0.42
        self.player.position.x += (target_x - self.player.position.x) * min(1, dt * 3.8)
        if self.dimension_mode == "shooter":
            self.player.position.y += (HEIGHT * 0.72 - self.player.position.y) * min(1, dt * 4)
            self.boss.position.x += (WIDTH * 0.5 - self.boss.position.x) * min(1, dt * 3.8)
            self.boss.position.y += (82 - self.boss.position.y) * min(1, dt * 3.8)
        else:
            self.boss.position.x += (self.camera_x + WIDTH * 0.62 - self.boss.position.x) * min(1, dt * 3.8)
        if random.random() < min(1, dt * 50):
            center = Vector2(self.boss.rect.center)
            angle = random.uniform(0, math.tau)
            speed = random.uniform(100, 380)
            self.particles.append(Particle(
                center, Vector2(math.cos(angle) * speed, math.sin(angle) * speed),
                self.boss.spec.primary, random.uniform(2, 8), random.uniform(0.5, 1.6), 20,
            ))
        if self.domain_timer <= 0:
            self.domain_active = False

    def build_arena(self, spec: BossSpec, phase: int = 1) -> list[Rect]:
        ground_top = 468 if phase == 1 else 505 if phase == 2 else 520
        layouts = {
            "abyss": [(250, 390, 190), (730, 340, 190), (1210, 395, 220), (1570, 315, 180)],
            "storm": [(170, 360, 190), (480, 430, 170), (790, 310, 180), (1200, 380, 240), (1570, 280, 170)],
            "crystal": [(100, 410, 240), (430, 345, 210), (780, 420, 250), (1160, 330, 210), (1510, 400, 250)],
            "fungus": [(220, 370, 220), (560, 300, 180), (900, 390, 240), (1320, 325, 190), (1630, 405, 210)],
            "forge": [(120, 395, 210), (440, 325, 170), (730, 410, 230), (1080, 350, 180), (1410, 280, 220)],
            "tide": [(80, 425, 250), (410, 350, 210), (760, 410, 200), (1110, 315, 240), (1510, 395, 230)],
            "clock": [(170, 380, 170), (480, 290, 160), (790, 390, 170), (1080, 270, 160), (1400, 360, 200)],
            "eclipse": [(90, 350, 190), (390, 425, 180), (720, 310, 230), (1100, 420, 180), (1450, 335, 230)],
            "thorn": [(140, 405, 210), (460, 345, 190), (800, 395, 220), (1170, 305, 200), (1500, 390, 250)],
            "inferno": [(110, 410, 220), (420, 340, 180), (730, 400, 230), (1060, 315, 210), (1430, 375, 240)],
            "mecha": [(150, 400, 210), (470, 325, 190), (790, 390, 220), (1110, 300, 210), (1480, 365, 230)],
        }
        if phase == 3:
            layouts[spec.style] = [(x, y - 35, width - 20) for x, y, width in layouts[spec.style]]
        platforms = [Rect(0, ground_top, WORLD_WIDTH, HEIGHT - ground_top)]
        platforms.extend(Rect(x, y, width, 16) for x, y, width in layouts[spec.style])
        return platforms

    def configure_potions(self, phase: int) -> None:
        """Keep potions on-screen and anchored to the current arena genre."""
        if self.dimension_mode == "shooter" and phase == 3:
            positions = ((450, 300), (210, 360), (735, 390))
        elif phase == 1:
            positions = ((560, 430), (1380, 366))
        elif phase == 2:
            positions = ((350, 330), (840, 282), (1320, 345))
        else:
            positions = ((450, 365), (820, 320), (1280, 365))
        self.potions = [HealthPotion(Vector2(x, y)) for x, y in positions]

    def start_boss(self, index: int) -> None:
        self.selected_boss = index
        spec = BOSS_SPECS[index]
        self.mode = "fight"
        self.player.reset()
        self.player.set_aspect(spec.style)
        self.boss = PantheonBoss(spec)
        self.hazards = []
        self.particles = []
        self.blood_pools = []
        self.platforms = self.build_arena(spec)
        self.camera_x = 0
        self.screen_shake = 0
        self.hit_stop = 0.0
        self.combat_feedback_timer = 0.0
        self.combat_feedback = ""
        self.dimension_mode = "2d"
        self.configure_potions(1)
        self.qte_active = False
        self.qte_done = False
        self.qte_pending = False
        self.victory_active = False
        self.victory_timer = 0.0
        self.domain_active = False
        self.domain_timer = 0.0
        self.finale_entry_timer = 0.0
        self.finale_entry_total = 0.0
        self.finale_active = False
        self.finale_timer = 0.0
        self.finale_hits = 0
        self.finale_health_max = 720
        self.finale_strike_flash = 0.0
        self.finale_combo = 0
        self.finale_execution_ready = False
        self.finale_execution_active = False
        self.finale_execution_timer = 0.0
        self.finale_execution_flash = 0.0
        self.finale_attack_cooldown = 0.0
        self.finale_attack_target_x = 0.0
        self.qte_hits = 0
        self.qte_timer = 0
        self.audio.start("cavern")
        self.begin_phase_intro(1)

    def start_victory(self) -> None:
        if self.boss is None or self.victory_active:
            return
        self.victory_active = True
        self.victory_total = 4.2
        self.victory_timer = self.victory_total
        self.victory_style = self.boss.spec.style
        self.victory_seed = random.random() * math.tau
        self.boss.health = 0
        self.boss.attack_timer = 0
        self.boss.attack_cooldown = 999
        self.hazards.clear()
        self.qte_active = False
        self.qte_pending = False
        self.screen_shake = 0.9
        self.flash_timer = 0.75
        self.flash_color = self.boss.spec.primary
        self.audio.play("transform")
        for _ in range(180):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(120, 520)
            self.particles.append(Particle(
                Vector2(self.boss.rect.center),
                Vector2(math.cos(angle) * speed, math.sin(angle) * speed),
                self.boss.spec.primary if random.random() < 0.72 else (255, 232, 170),
                random.uniform(2, 8), random.uniform(0.7, 2.7), random.uniform(-40, 180),
            ))

    def update_victory(self, dt: float) -> None:
        if self.boss is None:
            return
        self.victory_timer = max(0, self.victory_timer - dt)
        self.boss.anim_time += dt
        self.boss.hit_flash = max(0, self.boss.hit_flash - dt)
        if random.random() < min(1.0, dt * 26):
            origin = Vector2(self.boss.rect.center)
            angle = self.victory_seed + self.victory_timer * 2.2 + random.uniform(-0.4, 0.4)
            speed = random.uniform(80, 330)
            self.particles.append(Particle(
                origin, Vector2(math.cos(angle) * speed, math.sin(angle) * speed),
                self.boss.spec.primary if random.random() < 0.7 else (255, 237, 170),
                random.uniform(2, 7), random.uniform(0.4, 1.5), random.uniform(-80, 140),
            ))
        if self.victory_timer <= 0:
            self.victory_active = False
            self.finish_boss(True)

    def finish_boss(self, victory: bool) -> None:
        if victory and self.boss is not None:
            if self.selected_boss + 1 < len(BOSS_SPECS):
                self.unlocked_count = max(self.unlocked_count, self.selected_boss + 2)
                self.save_progress()
                self.selected_boss = min(self.selected_boss + 1, self.unlocked_count - 1)
                self.set_notice(f"Desbloqueado: {BOSS_SPECS[self.selected_boss].name}", 3)
            else:
                self.set_notice("Você dominou todo o Panteão.", 3)
        else:
            self.set_notice("O Panteão espera uma nova tentativa.", 2.4)
        self.mode = "menu"
        self.audio.start("menu")
        self.boss = None

    def apply_phase_change(self) -> None:
        if self.boss is None:
            return
        self.platforms = self.build_arena(self.boss.spec, self.boss.phase)
        self.screen_shake = 0.85
        self.flash_timer = 0.7
        self.flash_color = self.boss.spec.primary
        self.banner_timer = 3.0
        self.banner_text = self.boss.phase_name
        if self.boss.phase >= 2:
            self.audio.start("rock")
        if self.boss.phase == 2 and not self.qte_done:
            # QTE enters only after the phase entrance has fully finished.
            self.qte_pending = True
        if self.boss.phase == 3:
            self.dimension_mode = {
                "abyss": "3d",
                "storm": "shooter",
                "tide": "shooter",
                "eclipse": "shooter",
                "forge": "shooter",
                "mecha": "finale",
            }.get(self.boss.spec.style, "3d")
            self.genre_title = {
                "3d": "DOMÍNIO 3D: O CHÃO VIROU VAZIO",
                "shooter": "BATALHA DE NAVE: CAÇADA ORBITAL",
                "finale": "ASCENSÃO FINAL: LIRA E O MECHA DO VOTO",
            }[self.dimension_mode]
            if self.dimension_mode == "shooter":
                self.player.position = Vector2(450, 420)
                self.boss.position = Vector2(438, 72)
            self.configure_potions(3)
            self.set_notice(self.genre_title, 3.0)
            self.audio.start(f"phase_{self.boss.spec.style}")
        elif self.boss.phase == 2:
            self.configure_potions(2)
        if self.boss.phase == 3 and self.dimension_mode == "finale":
            self.start_finale_entry()
        elif self.boss.phase == 3:
            self.start_domain_expansion()
        else:
            self.begin_phase_intro(self.boss.phase)
        for _ in range(70):
            self.particles.append(Particle(
                Vector2(random.uniform(self.camera_x, self.camera_x + WIDTH), random.uniform(65, HEIGHT)),
                Vector2(random.uniform(-90, 90), random.uniform(-260, -40)),
                self.boss.spec.primary, random.uniform(2, 7), random.uniform(0.8, 1.8), 120,
            ))

    def start_finale_entry(self) -> None:
        """Begin the last fight inside the arena, not on a separate screen."""
        self.finale_entry_total = 5.4
        self.finale_entry_timer = self.finale_entry_total
        self.finale_active = False
        self.finale_timer = 0.0
        self.finale_hits = 0
        self.finale_target = 36
        self.finale_health_max = 720
        self.finale_strike_flash = 0.0
        self.finale_combo = 0
        self.finale_execution_ready = False
        self.finale_execution_active = False
        self.finale_execution_timer = 0.0
        self.finale_execution_flash = 0.0
        self.finale_attack_cooldown = 0.7
        self.finale_attack_target_x = 0.0
        self.hazards.clear()
        self.player.position = Vector2(245, 354)
        self.player.velocity = Vector2()
        self.boss.position = Vector2(650, 190)
        self.boss.health = self.finale_health_max
        self.boss.attack_timer = 0
        self.boss.attack_cooldown = 999
        self.boss.shield = 0
        self.boss.shield_broken = True
        self.set_notice("LIRA VESTE O MECHA DO VOTO", self.finale_entry_total)
        self.audio.start("phase_mecha")
        for _ in range(80):
            self.particles.append(Particle(
                Vector2(random.uniform(160, 800), random.uniform(140, 470)),
                Vector2(random.uniform(-80, 80), random.uniform(-210, -45)),
                random.choice([(255, 91, 35), (255, 206, 91), (76, 210, 255)]),
                random.uniform(2, 7), random.uniform(0.8, 1.8), 90,
            ))

    def update_finale_entry(self, dt: float) -> None:
        self.finale_entry_timer = max(0, self.finale_entry_timer - dt)
        self.boss.anim_time += dt * 1.4
        progress = 1.0 - self.finale_entry_timer / max(0.01, self.finale_entry_total)
        flight = smoothstep(clamp(progress / 0.34, 0.0, 1.0))
        self.boss.position.y = 190 - flight * 260
        self.boss.position.x = 650 + math.sin(progress * math.pi * 4) * 35
        self.player.position.x += (300 + progress * 70 - self.player.position.x) * min(1, dt * 2.5)
        self.player.position.y += (360 - progress * 28 - self.player.position.y) * min(1, dt * 2.5)
        if random.random() < min(1, dt * 38):
            center = Vector2(360, 365)
            angle = random.uniform(0, math.tau)
            radius = random.uniform(50, 230) * (1.0 - progress * 0.55)
            self.particles.append(Particle(
                center + Vector2(math.cos(angle), math.sin(angle)) * radius,
                Vector2(-math.cos(angle) * 80, -math.sin(angle) * 80),
                random.choice([(255, 100, 36), (255, 227, 133), (109, 225, 255)]),
                random.uniform(2, 6), 0.55, 0,
            ))
        if self.finale_entry_timer <= 0:
            self.finale_active = True
            self.finale_timer = 20.0
            self.finale_attack_cooldown = 0.7
            self.set_notice("ATAQUE E MOVA: A/D, J OU X", 2.2)

    def update_finale_player(self, dt: float) -> None:
        """Movement is the defense in the climax, not a frozen QTE lane."""
        keys = pygame.key.get_pressed()
        direction = (1 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0) - (
            1 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0
        )
        self.player.velocity.x += (direction * 420 - self.player.velocity.x) * min(1, dt * 12)
        self.player.position.x = clamp(
            self.player.position.x + self.player.velocity.x * dt, 155, 420
        )
        self.player.position.y = 355 + math.sin(self.elapsed * 5.5) * 5
        self.player.walk_time += dt * (8 if direction else 3)

    def update_finale_hazards(self, dt: float) -> None:
        """The boss counterattacks with readable beams that punish standing still."""
        self.finale_attack_cooldown = max(0, self.finale_attack_cooldown - dt)
        if self.finale_attack_cooldown <= 0 and self.boss is not None:
            self.finale_attack_target_x = self.player.position.x + 85
            self.hazards.append(Hazard(
                Vector2(self.finale_attack_target_x, 0), Vector2(), 21,
                (255, 105, 42), 22, 1.15, "mecha_beam", armed_after=0.38,
            ))
            self.finale_attack_cooldown = 1.55
            self.set_notice("MOVA: O FEIXE VAI CAIR AÍ", 0.55)
            self.audio.play("boss_attack")

        alive: list[Hazard] = []
        for hazard in self.hazards:
            if not hazard.update(dt):
                continue
            if hazard.kind == "mecha_beam" and self.hazard_hits_player(hazard):
                if self.player.take_damage(hazard.damage, self.particles):
                    self.trigger_hit_stop(0.08, "CONTRA-ATAQUE")
                    self.screen_shake = max(self.screen_shake, 0.26)
                    self.set_notice("O FEIXE ACERTOU LIRA", 0.7)
                hazard.hit = True
            if not hazard.hit:
                alive.append(hazard)
        self.hazards = alive

    def register_finale_hit(self) -> None:
        if not self.finale_active or self.boss is None:
            return
        self.finale_hits += 1
        self.finale_combo = min(9, self.finale_combo + 1)
        self.finale_strike_flash = 1.0
        self.trigger_hit_stop(0.045, "IMPACTO DO VOTO")
        self.screen_shake = max(self.screen_shake, 0.24 + self.finale_combo * 0.015)
        self.boss.hit_flash = 0.18
        self.boss.health = max(0, self.boss.health - 18)
        center = Vector2(650, 258)
        for _ in range(18):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(100, 430)
            self.particles.append(Particle(
                center.copy(),
                Vector2(math.cos(angle) * speed, math.sin(angle) * speed),
                random.choice([(255, 92, 35), (255, 220, 123), (120, 229, 255)]),
                random.uniform(2, 7), random.uniform(0.35, 0.9), 40,
            ))
        self.audio.play("impact")
        if self.finale_hits % 5 == 0:
            self.finale_combo = 0
            self.set_notice("O NÚCLEO CEDE", 0.6)
        if self.boss.health <= self.finale_health_max * 0.12:
            self.finale_active = False
            self.finale_execution_ready = True
            self.finale_timer = 0.0
            self.set_notice("NÚCLEO EXPOSTO: PRESSIONE ESPAÇO PARA FINALIZAR", 3.0)

    def start_finale_execution(self) -> None:
        if self.boss is None or not self.finale_execution_ready:
            return
        self.finale_execution_ready = False
        self.finale_execution_active = True
        self.finale_execution_timer = self.finale_execution_total
        self.finale_execution_flash = 1.0
        self.hazards.clear()
        self.screen_shake = max(self.screen_shake, 0.9)
        self.set_notice("GOLPE DO VOTO: MANDE O GUARDIÃO AO SOL", 2.0)
        self.audio.play("transform")

    def update_finale_execution(self, dt: float) -> None:
        if self.boss is None:
            return
        self.finale_execution_timer = max(0, self.finale_execution_timer - dt)
        self.finale_execution_flash = max(0, self.finale_execution_flash - dt * 2.8)
        progress = 1.0 - self.finale_execution_timer / max(0.01, self.finale_execution_total)
        self.boss.anim_time += dt * 3.0
        self.player.walk_time += dt * 9.0
        self.boss.position.y = 180 - smoothstep(progress) * 430
        self.boss.position.x = 650 + math.sin(progress * math.pi * 2.2) * 120
        self.screen_shake = max(self.screen_shake, 0.18 + progress * 0.5)
        if random.random() < min(1, dt * 60):
            origin = Vector2(650, 250 - progress * 120)
            angle = random.uniform(0, math.tau)
            self.particles.append(Particle(
                origin,
                Vector2(math.cos(angle) * random.uniform(100, 420),
                        math.sin(angle) * random.uniform(100, 420)),
                random.choice([(255, 95, 38), (255, 225, 133), (103, 220, 255)]),
                random.uniform(2, 8), random.uniform(0.35, 1.0), 20,
            ))
        if self.finale_execution_timer <= 0:
            self.boss.health = 0
            self.finale_execution_active = False
            self.start_victory()

    def update_finale(self, dt: float) -> None:
        if self.boss is None:
            return
        self.update_finale_player(dt)
        self.update_finale_hazards(dt)
        self.finale_timer = max(0, self.finale_timer - dt)
        self.finale_strike_flash = max(0, self.finale_strike_flash - dt * 4.2)
        self.boss.anim_time += dt * 2.4
        self.player.walk_time += dt * 7
        if random.random() < min(1, dt * 30):
            angle = self.elapsed * 2.3 + random.uniform(-0.2, 0.2)
            self.particles.append(Particle(
                Vector2(650, 280) + Vector2(math.cos(angle), math.sin(angle)) * random.uniform(120, 265),
                Vector2(random.uniform(-30, 30), random.uniform(-170, -40)),
                (255, 118, 45), random.uniform(2, 6), random.uniform(0.5, 1.3), 75,
            ))
        if self.boss.health <= 0 or self.finale_hits >= self.finale_target:
            self.finale_active = False
            self.start_victory()
        elif self.player.health <= 0:
            self.finale_active = False
            self.finish_boss(False)
        elif self.finale_timer <= 0:
            self.finale_active = False
            self.player.take_damage(35, self.particles)
            if self.player.health <= 0:
                self.finish_boss(False)
            else:
                self.set_notice("O NÚCLEO REJEITA O VOTO. TENTE DE NOVO.", 2.0)
                self.start_finale_entry()

    def start_qte(self) -> None:
        self.qte_active = True
        self.qte_done = True
        self.qte_timer = 4.2
        self.qte_hits = 0
        self.qte_target = 28 + (self.selected_boss * 2)
        self.qte_success = False
        self.qte_anim = 0.0
        self.qte_hit_flash = 0.0
        self.qte_last_side = 1
        self.qte_lunge = 0.0
        self.qte_clash = 0.0
        self.set_notice("CONFRONTO DE VOTOS — ESPAÇO!", 4.2)

    def update_qte(self, dt: float) -> None:
        self.qte_anim += dt
        self.qte_hit_flash = max(0, self.qte_hit_flash - dt * 4.5)
        self.qte_lunge = max(0, self.qte_lunge - dt * 3.5)
        self.qte_clash = max(0, self.qte_clash - dt * 4.0)
        self.qte_timer = max(0, self.qte_timer - dt)
        if self.qte_hits >= self.qte_target:
            self.qte_active = False
            self.qte_success = True
            if self.boss is not None:
                self.boss.health = max(0, self.boss.health - 36)
            self.set_notice("LIRA VENCE O CHOQUE. O GUARDIÃO SANGRA.", 2.2)
            return
        if self.qte_timer <= 0:
            self.qte_active = False
            self.qte_success = False
            self.player.take_damage(30, self.particles)
            self.set_notice("O GUARDIÃO VENCE O CHOQUE. LIRA É LANÇADA.", 2.2)

    def fire_player_laser(self) -> None:
        if self.mode != "fight" or self.dimension_mode != "shooter":
            return
        for spread in (-105, 0, 105):
            self.hazards.append(Hazard(
                Vector2(self.player.position.x + 22 + spread * 0.08, self.player.position.y - 12),
                Vector2(spread * 0.42, -820), 7 if spread else 9,
                (102, 239, 255), 14 if spread else 18, 1.35, "player_laser_v", friendly=True,
            ))
        for _ in range(5):
            self.particles.append(Particle(
                Vector2(self.player.position.x + 22, self.player.position.y - 18),
                Vector2(random.uniform(-100, 100), random.uniform(-130, -35)),
                (139, 246, 255), random.uniform(2, 5), 0.32, 0,
            ))
        self.audio.play("attack")

    def update_hazards_and_collisions(self, dt: float) -> None:
        if self.boss is None:
            return
        alive_hazards: list[Hazard] = []
        for hazard in self.hazards:
            if hazard.update(dt):
                if hazard.friendly:
                    if hazard.swept_rect.colliderect(self.boss.rect):
                        if self.boss.take_damage(hazard.damage, self.particles):
                            self.audio.play("impact")
                            self.screen_shake = max(self.screen_shake, 0.12)
                            self.add_blood_pool(Vector2(self.boss.rect.centerx, self.boss.rect.bottom - 4))
                        hazard.hit = True
                elif self.hazard_hits_player(hazard) and self.player.take_damage(hazard.damage, self.particles):
                    self.audio.play("hurt")
                    self.screen_shake = max(self.screen_shake, 0.18)
                    self.add_blood_pool(Vector2(self.player.rect.centerx, self.player.rect.bottom - 3))
                    self.set_notice("ESCUDO DE LIRA ABSORVEU O IMPACTO" if self.player.shield > 0
                                    else "LIRA FOI ATINGIDA", 0.55)
                    hazard.hit = True
                if not hazard.hit:
                    alive_hazards.append(hazard)
        self.hazards = alive_hazards
        if self.player.health <= 0:
            self.finish_boss(False)
        elif self.boss.health <= 0:
            self.start_victory()

    def hazard_hits_player(self, hazard: Hazard) -> bool:
        """Use a swept test for vertical shots so fast projectiles cannot tunnel through Lira."""
        if not hazard.armed:
            return False
        if hazard.kind == "mecha_beam":
            mecha_rect = self.player.rect.move(64, 0).inflate(18, 12)
            return hazard.swept_rect.colliderect(mecha_rect)
        if hazard.kind in {"lightning", "mecha_beam", "enemy_bolt_v", "enemy_ring_v", "wave", "shark"}:
            player_rect = self.player.rect.inflate(10, 8)
            if hazard.kind == "lightning":
                return abs(hazard.position.x - player_rect.centerx) <= hazard.radius + player_rect.width // 2
            return hazard.swept_rect.colliderect(player_rect)
        return hazard.swept_rect.colliderect(self.player.rect)

    def handle_audio_key(self, key: int) -> bool:
        if key == pygame.K_m:
            muted = self.audio.toggle_mute()
            self.set_notice("ÁUDIO SILENCIADO" if muted else "ÁUDIO REATIVADO")
            return True
        if key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.audio.adjust(-0.1)
            self.set_notice(f"VOLUME {int(self.audio.master_volume * 100)}%")
            return True
        if key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
            self.audio.adjust(0.1)
            self.set_notice(f"VOLUME {int(self.audio.master_volume * 100)}%")
            return True
        return False

    def handle_input(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_ESCAPE:
                if self.mode == "fight":
                    self.finish_boss(False)
                else:
                    self.running = False
                continue
            if self.victory_active:
                continue
            if self.mode == "fight" and self.qte_active:
                if self.handle_audio_key(event.key):
                    continue
                if event.key in (pygame.K_SPACE, pygame.K_j, pygame.K_x):
                    self.qte_hits += 1
                    self.qte_hit_flash = 1.0
                    self.qte_lunge = 1.0
                    self.qte_clash = 1.0
                    self.qte_last_side *= -1
                    self.audio.play("attack")
                    if self.boss is not None:
                        self.particles.append(Particle(
                            Vector2(WIDTH // 2, 276),
                            Vector2(random.uniform(-170, 170), random.uniform(-190, 20)),
                            self.boss.spec.primary, random.uniform(2, 5), 0.38, 250,
                        ))
                continue
            if self.mode == "fight" and (self.finale_entry_timer > 0 or self.finale_active):
                if self.handle_audio_key(event.key):
                    continue
                if self.finale_active and event.key in (pygame.K_SPACE, pygame.K_j, pygame.K_x):
                    self.register_finale_hit()
                continue
            if self.mode == "fight" and self.finale_execution_ready:
                if self.handle_audio_key(event.key):
                    continue
                if event.key in (pygame.K_SPACE, pygame.K_j, pygame.K_x):
                    self.start_finale_execution()
                continue
            if self.mode == "fight" and self.finale_execution_active:
                if self.handle_audio_key(event.key):
                    continue
                continue
            if self.mode == "menu":
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    self.selected_boss = max(0, self.selected_boss - 1)
                    self.audio.play("select")
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    self.selected_boss = min(self.unlocked_count - 1, self.selected_boss + 1)
                    self.audio.play("select")
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_j, pygame.K_x):
                    self.start_boss(self.selected_boss)
                elif event.key == pygame.K_r:
                    self.unlocked_count = len(BOSS_SPECS)
                    self.selected_boss = 0
                    self.save_progress()
                    self.set_notice("MODO DE TESTE: TODOS OS GUARDIÕES DISPONÍVEIS")
                self.handle_audio_key(event.key)
            else:
                if self.handle_audio_key(event.key):
                    continue
                if event.key == pygame.K_r and self.boss is not None:
                    self.start_boss(self.selected_boss)
                elif (self.dimension_mode != "shooter"
                      and event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT)
                      and not self.qte_active):
                    if self.player.dodge(self.particles):
                        self.set_notice("ESQUIVA", 0.45)
                elif self.dimension_mode == "shooter" and event.key in (pygame.K_j, pygame.K_x, pygame.K_SPACE):
                    self.fire_player_laser()

        if self.mode != "fight" or self.boss is None:
            return
        if self.qte_active:
            return
        keys = pygame.key.get_pressed()
        if self.dimension_mode == "shooter":
            self.jump_was_down = False
            self.attack_was_down = False
            return
        jump_down = bool(keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP])
        attack_down = bool(keys[pygame.K_j] or keys[pygame.K_x])
        if jump_down and not self.jump_was_down:
            self.player.jump(self.particles)
        if attack_down and not self.attack_was_down and self.player.attack(self.particles):
            self.audio.play("attack")
        self.jump_was_down = jump_down
        self.attack_was_down = attack_down

    def update(self, dt: float) -> None:
        self.elapsed += dt
        self.notice_timer = max(0, self.notice_timer - dt)
        self.combat_feedback_timer = max(0, self.combat_feedback_timer - dt)
        self.banner_timer = max(0, self.banner_timer - dt)
        self.screen_shake = max(0, self.screen_shake - dt * 2.4)
        self.flash_timer = max(0, self.flash_timer - dt * 2.0)
        self.particles = [particle for particle in self.particles if particle.update(dt)]
        if self.hit_stop > 0:
            self.hit_stop = max(0, self.hit_stop - dt)
            return
        for potion in self.potions:
            potion.update(dt)
        if self.mode != "fight" or self.boss is None:
            return
        if self.victory_active:
            self.update_victory(dt)
            return
        if self.finale_entry_timer > 0:
            self.update_finale_entry(dt)
            return
        if self.finale_execution_active:
            self.update_finale_execution(dt)
            return
        if self.finale_execution_ready:
            self.finale_strike_flash = max(0, self.finale_strike_flash - dt * 2.0)
            return
        if self.finale_active:
            self.update_finale(dt)
            return
        if self.domain_active:
            self.update_domain_expansion(dt)
            return
        if self.intro_timer > 0:
            self.intro_timer = max(0, self.intro_timer - dt)
            self.boss.anim_time += dt
            return
        if self.qte_pending and not self.qte_active:
            self.qte_pending = False
            self.start_qte()
            return
        if self.qte_active:
            self.update_qte(dt)
            return

        keys = pygame.key.get_pressed()
        if self.dimension_mode == "shooter":
            self.update_shooter_player(dt, keys)
        else:
            self.player.update(dt, keys, self.platforms, self.particles)
        for potion in self.potions:
            if not potion.collected and potion.rect.colliderect(self.player.rect) and self.player.health < 100:
                potion.collected = True
                recovered = max(1, int(100 * 0.40))
                self.player.health = min(100, self.player.health + recovered)
                self.audio.play("select")
                self.flash_timer = max(self.flash_timer, 0.16)
                self.flash_color = (255, 96, 142)
                self.set_notice(f"POÇÃO DE VIDA +{recovered}% ", 1.5)
                for _ in range(20):
                    self.particles.append(Particle(
                        Vector2(self.player.rect.center),
                        Vector2(random.uniform(-150, 150), random.uniform(-190, 20)),
                        (255, 102, 145), random.uniform(2, 5), 0.65, -70,
                    ))
        if self.dimension_mode == "shooter":
            self.update_shooter_boss(dt)
            phase_started = False
        else:
            phase_started, _ = self.boss.update(dt, self.player, self.platforms, self.hazards, self.particles)
        if phase_started:
            self.apply_phase_change()
        if self.qte_active:
            return
        if self.player.attack_timer > 0 and self.player.attack_rect.colliderect(self.boss.rect):
            if self.boss.take_damage(12, self.particles):
                self.audio.play("impact")
                self.screen_shake = max(self.screen_shake, 0.12)
                self.flash_timer = max(self.flash_timer, 0.08)
                self.trigger_hit_stop(0.065, "IMPACTO")
                self.add_blood_pool(Vector2(self.boss.rect.centerx, self.boss.rect.bottom - 4))

        alive_hazards: list[Hazard] = []
        for hazard in self.hazards:
            if hazard.update(dt):
                if hazard.friendly:
                    if hazard.swept_rect.colliderect(self.boss.rect):
                        if self.boss.take_damage(hazard.damage, self.particles):
                            self.audio.play("impact")
                            self.screen_shake = max(self.screen_shake, 0.1)
                            self.flash_timer = max(self.flash_timer, 0.06)
                            self.trigger_hit_stop(0.04, "ACERTO")
                            self.add_blood_pool(Vector2(self.boss.rect.centerx, self.boss.rect.bottom - 4))
                        hazard.hit = True
                elif self.hazard_hits_player(hazard) and self.player.take_damage(hazard.damage, self.particles):
                    self.audio.play("hurt")
                    self.screen_shake = max(self.screen_shake, 0.15)
                    self.trigger_hit_stop(0.09, "LIRA ATINGIDA")
                    self.add_blood_pool(Vector2(self.player.rect.centerx, self.player.rect.bottom - 3))
                    self.set_notice("ESCUDO DE LIRA ABSORVEU O IMPACTO" if self.player.shield > 0
                                    else "LIRA FOI ATINGIDA", 0.55)
                    hazard.hit = True
                if not hazard.hit:
                    alive_hazards.append(hazard)
        self.hazards = alive_hazards

        if self.dimension_mode != "shooter" and self.boss.attack_timer > 0 and self.boss.attack_rect.colliderect(self.player.rect):
            if self.player.take_damage(10 + self.boss.phase * 3, self.particles):
                self.audio.play("hurt")
                self.screen_shake = max(self.screen_shake, 0.2)
                self.trigger_hit_stop(0.10, "LIRA ATINGIDA")
                self.add_blood_pool(Vector2(self.player.rect.centerx, self.player.rect.bottom - 3))

        if self.player.health <= 0:
            self.finish_boss(False)
        elif self.boss.health <= 0:
            self.start_victory()

        target_camera = self.player.position.x - WIDTH * 0.36
        self.camera_x += (target_camera - self.camera_x) * min(1, dt * 5)
        self.camera_x = clamp(self.camera_x, 0, WORLD_WIDTH - WIDTH)

    def update_shooter_player(self, dt: float, keys: pygame.key.ScancodeWrapper) -> None:
        direction_x = (1 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0) - (
            1 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0
        )
        direction_y = (1 if keys[pygame.K_s] or keys[pygame.K_DOWN] else 0) - (
            1 if keys[pygame.K_w] or keys[pygame.K_UP] else 0
        )
        self.player.velocity.x = direction_x * 470
        self.player.velocity.y = direction_y * 390
        self.player.position.x = clamp(self.player.position.x + self.player.velocity.x * dt, 70, WIDTH - 115)
        self.player.position.y = clamp(self.player.position.y + self.player.velocity.y * dt, 125, HEIGHT - 78)
        self.player.attack_timer = max(0, self.player.attack_timer - dt)
        self.player.attack_cooldown = max(0, self.player.attack_cooldown - dt)
        # The platform controller normally owns these timers. The ship
        # controller must decay them too, otherwise one hit can make Lira
        # permanently invulnerable for the rest of the ship phase.
        self.player.invulnerable = max(0, self.player.invulnerable - dt)
        self.player.hurt_flash = max(0, self.player.hurt_flash - dt)
        self.player.shield_break_timer = max(0, self.player.shield_break_timer - dt)
        self.player.bruised_eye = max(0, self.player.bruised_eye - dt * 0.012)

    def update_shooter_boss(self, dt: float) -> None:
        if self.boss is None:
            return
        boss = self.boss
        boss.anim_time += dt
        boss.attack_timer = max(0, boss.attack_timer - dt)
        boss.attack_cooldown = max(0, boss.attack_cooldown - dt)
        boss.invulnerable = max(0, boss.invulnerable - dt)
        boss.hit_flash = max(0, boss.hit_flash - dt)
        boss.transition_timer = max(0, boss.transition_timer - dt)
        boss.position.x = clamp(438 + math.sin(self.elapsed * 1.7) * 210,
                                150, WIDTH - boss.width - 150)
        boss.position.y = 72 + math.sin(self.elapsed * 2.4) * 20
        if boss.attack_cooldown <= 0:
            boss.attack_duration = 0.44
            boss.attack_timer = boss.attack_duration
            boss.attack_cooldown = max(0.36, 0.86 - boss.phase * 0.11)
            boss.spawn_vertical_attack(self.player, self.hazards)

    def draw_menu_background(self, surface: Surface) -> None:
        for y in range(HEIGHT):
            ratio = y / HEIGHT
            color = (int(7 + ratio * 19), int(10 + ratio * 14), int(32 + ratio * 34))
            pygame.draw.line(surface, color, (0, y), (WIDTH, y))
        center = (WIDTH // 2, 250)
        for radius in (220, 178, 136):
            pulse = int(math.sin(self.elapsed * 1.7 + radius) * 4)
            pygame.draw.circle(surface, (35, 53, 94), center, radius + pulse, 1)
        pygame.draw.circle(surface, (12, 16, 42), center, 74)
        draw_glow(surface, center, (78, 155, 235), 90, 38)
        for ray in range(12):
            angle = self.elapsed * 0.12 + ray * math.tau / 12
            start = Vector2(center) + Vector2(math.cos(angle), math.sin(angle)) * 82
            end = Vector2(center) + Vector2(math.cos(angle), math.sin(angle)) * 215
            pygame.draw.line(surface, (36, 55, 99), start, end, 1)
        for index in range(12):
            x = (index * 113 + int(self.elapsed * (8 + index % 3))) % (WIDTH + 80) - 40
            y = 90 + (index * 47) % 270
            twinkle = 1 + int((math.sin(self.elapsed * 3 + index) + 1) * 1.2)
            draw_glow(surface, (x, y), (85, 160, 224), 10 + twinkle * 2, 18)
            pygame.draw.circle(surface, (145, 196, 240), (x, y), twinkle)

    def draw_portrait(self, surface: Surface, rect: Rect, spec: BossSpec, locked: bool, selected: bool) -> None:
        border = spec.primary if selected and not locked else (79, 92, 131)
        if selected and not locked:
            draw_glow(surface, rect.center, spec.primary, 120, 42)
            float_offset = int(math.sin(self.elapsed * 3.0) * 4)
            rect = rect.move(0, -float_offset)
        pygame.draw.rect(surface, (13, 17, 43), rect, border_radius=10)
        pygame.draw.rect(surface, border, rect, 3 if selected else 1, border_radius=10)
        art = rect.inflate(-18, -44)
        pygame.draw.rect(surface, spec.secondary if not locked else (22, 25, 49), art, border_radius=8)
        if locked:
            pygame.draw.circle(surface, (93, 99, 133), art.center, 27, 4)
            pygame.draw.line(surface, (93, 99, 133), (art.centerx, art.centery - 18), (art.centerx, art.centery + 18), 5)
            draw_text(surface, "BLOQUEADO", (rect.centerx, rect.bottom - 21), 11, (146, 154, 187), center=True, bold=True)
            return
        cx, cy = art.center
        pulse = int(math.sin(self.elapsed * 3 + rect.x) * 3)
        draw_glow(surface, (cx, cy + pulse), spec.primary, 52, 28)
        pygame.draw.circle(surface, spec.primary, (cx, cy + pulse), 31)
        pygame.draw.polygon(surface, spec.secondary, [(cx, cy + 10), (cx - 35, art.bottom - 8), (cx + 35, art.bottom - 8)])
        if spec.style in {"storm", "eclipse"}:
            pygame.draw.line(surface, spec.primary, (cx - 44, cy - 24), (cx + 45, cy + 18), 4)
        if spec.style in {"crystal", "thorn"}:
            for side in (-1, 1):
                pygame.draw.polygon(surface, spec.primary, [(cx, cy - 20), (cx + side * 42, cy - 45), (cx + side * 16, cy + 6)])
        if spec.style == "clock":
            pygame.draw.circle(surface, (245, 226, 136), (cx, cy), 38, 3)
        if spec.style == "tide":
            pygame.draw.arc(surface, spec.primary, Rect(cx - 48, cy - 20, 96, 70), math.pi, math.tau, 5)
        if spec.style == "inferno":
            for flame in range(7):
                angle = flame * math.tau / 7 + self.elapsed
                pygame.draw.line(surface, (255, 184, 61), (cx, cy),
                                 (cx + int(math.cos(angle) * 43), cy + int(math.sin(angle) * 43)), 3)
        if spec.style == "mecha":
            pygame.draw.rect(surface, (25, 61, 94), (cx - 30, cy - 24, 60, 48), 3, border_radius=5)
            pygame.draw.line(surface, (239, 104, 65), (cx - 20, cy), (cx + 20, cy), 4)
        draw_text(surface, spec.name, (rect.centerx, rect.bottom - 29), 12, (235, 239, 255), center=True, bold=True)
        draw_text(surface, spec.title, (rect.centerx, rect.bottom - 13), 9, (167, 181, 213), center=True)

    def draw_menu(self, surface: Surface) -> None:
        self.draw_menu_background(surface)
        draw_text(surface, "PANTEÃO DO ABISMO", (WIDTH // 2, 32), 30, (237, 242, 255), center=True, bold=True)
        draw_text(surface, "Caminhe entre os retratos. Cada vitória abre um novo desafio.", (WIDTH // 2, 62), 14, (164, 181, 216), center=True)
        progress = f"{self.unlocked_count}/{len(BOSS_SPECS)} guardiões despertos"
        draw_text(surface, progress, (WIDTH // 2, 86), 13, (243, 193, 113), center=True, bold=True)
        if self.notice_timer <= 0:
            draw_text(surface, STORY_LINES[self.selected_boss], (WIDTH // 2, 105), 11, (188, 202, 228), center=True)

        card_w, card_h, gap = 158, 205, 18
        target_scroll = self.selected_boss * (card_w + gap) - (WIDTH // 2 - card_w // 2)
        self.menu_scroll = getattr(self, "menu_scroll", 0)
        self.menu_scroll += (target_scroll - self.menu_scroll) * 0.12
        for index, spec in enumerate(BOSS_SPECS):
            x = int(index * (card_w + gap) - self.menu_scroll)
            rect = Rect(x, 118, card_w, card_h)
            if rect.right < -20 or rect.left > WIDTH + 20:
                continue
            self.draw_portrait(surface, rect, spec, index >= self.unlocked_count, index == self.selected_boss)
        selected_x = WIDTH // 2
        self.player.draw_menu(surface, (selected_x, 430))
        draw_text(surface, f"SELECIONADO: {BOSS_SPECS[self.selected_boss].name}",
                  (WIDTH // 2, 474), 16, BOSS_SPECS[self.selected_boss].primary, center=True, bold=True)
        draw_text(surface, "A/D ou setas: caminhar entre retratos   ENTER/J: desafiar   M: silêncio   -/+: volume",
                  (WIDTH // 2, 512), 12, (165, 180, 211), center=True)
        if self.notice_timer > 0:
            draw_text(surface, self.notice, (WIDTH // 2, 106), 14, (255, 213, 133), center=True, bold=True)

    def draw_background(self, surface: Surface) -> None:
        if self.boss is None:
            return
        spec = self.boss.spec
        phase = self.boss.phase
        top = tuple(int(c * (0.34 + phase * 0.08)) for c in spec.secondary)
        bottom = tuple(int(c * (0.45 + phase * 0.1)) for c in spec.primary)
        for y in range(HEIGHT):
            ratio = y / HEIGHT
            color = tuple(int(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3))
            surface.fill(color, Rect(0, y, WIDTH, 1))
        orb_center = (770 - int(self.camera_x * 0.12), 104)
        draw_glow(surface, orb_center, spec.primary, 105 + phase * 12, 38)
        pygame.draw.circle(surface, (*spec.primary, 70), orb_center, 52 + phase * 10)
        for ring in range(3):
            radius = 80 + ring * 24 + int(math.sin(self.elapsed * 1.6 + ring) * 5)
            start = self.elapsed * 0.2 + ring
            pygame.draw.arc(surface, spec.primary,
                            Rect(orb_center[0] - radius, orb_center[1] - radius, radius * 2, radius * 2),
                            start, start + 1.7, 1)
        for index in range(18):
            x = (index * 137 - int(self.camera_x * (0.08 + index % 3 * 0.03))) % (WIDTH + 90) - 45
            y = 70 + (index * 61) % 310
            alpha = 40 + int((math.sin(self.elapsed * 2.4 + index) + 1) * 22)
            mote = Surface((10, 10), pygame.SRCALPHA)
            pygame.draw.circle(mote, (*spec.primary, alpha), (5, 5), 1 + index % 2)
            surface.blit(mote, (x, y))
        if spec.style == "storm":
            for index in range(7):
                x = (index * 177 + int(self.elapsed * 20)) % WIDTH
                pygame.draw.line(surface, spec.primary, (x, 0), (x - 90, 290), 1)
        elif spec.style == "crystal":
            for index in range(8):
                x = (index * 145 - int(self.camera_x * 0.25)) % (WIDTH + 120) - 60
                pygame.draw.polygon(surface, spec.secondary, [(x, 310), (x + 35, 110), (x + 76, 310)])
        elif spec.style == "fungus":
            for index in range(10):
                x = (index * 117 - int(self.camera_x * 0.2)) % (WIDTH + 120)
                pygame.draw.circle(surface, spec.secondary, (x, 275 + index % 3 * 25), 24 + index % 3 * 7)
        elif spec.style == "forge":
            for index in range(9):
                x = (index * 130 - int(self.camera_x * 0.3)) % (WIDTH + 100)
                pygame.draw.line(surface, (255, 185, 62), (x, 350), (x + 50, 90), 2)
        elif spec.style == "tide":
            for wave in range(3):
                pygame.draw.arc(surface, spec.secondary, Rect(-100, 180 + wave * 58, WIDTH + 200, 170), 0, math.pi, 4)
        elif spec.style == "clock":
            pygame.draw.circle(surface, spec.secondary, (WIDTH // 2, 245), 185, 2)
            pygame.draw.line(surface, spec.secondary, (WIDTH // 2, 245), (WIDTH // 2 + 145, 245), 2)
        elif spec.style == "eclipse":
            pygame.draw.circle(surface, (4, 3, 15), (WIDTH // 2, 145), 86)
            pygame.draw.circle(surface, spec.primary, (WIDTH // 2, 145), 100, 4)
        elif spec.style == "thorn":
            for x in range(-100, WIDTH + 120, 100):
                pygame.draw.line(surface, spec.secondary, (x, 350), (x + 75, 140), 4)
        elif spec.style == "inferno":
            for ring in range(4):
                radius = 120 + ring * 48 + int(math.sin(self.elapsed * 3 + ring) * 5)
                pygame.draw.arc(surface, (255, 91 + ring * 28, 35),
                                Rect(WIDTH // 2 - radius, 300 - radius // 3,
                                     radius * 2, radius), math.pi, math.tau, 3)
        elif spec.style == "mecha":
            for ray in range(9):
                x = (ray * 143 + int(self.elapsed * 16)) % WIDTH
                pygame.draw.line(surface, (33, 106, 151), (x, 420), (x + 85, 90), 2)
            pygame.draw.circle(surface, spec.primary, (WIDTH // 2, 155), 72, 2)
        else:
            pygame.draw.polygon(surface, spec.secondary, [(0, 310), (180, 160), (390, 310), (620, 120), (960, 310)])
        if phase == 2:
            # A segunda fase não é só um multiplicador: o palco se rompe.
            veil = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            veil.fill((*spec.primary, 24))
            surface.blit(veil, (0, 0))
            for shard in range(8):
                x = (shard * 149 - int(self.camera_x * 0.15)) % (WIDTH + 180) - 90
                drift = int(math.sin(self.elapsed * 2.5 + shard) * 18)
                pygame.draw.polygon(surface, spec.primary, [
                    (x, 75 + drift), (x + 20, 215 + drift), (x - 36, 340 + drift),
                    (x - 18, 185 + drift),
                ])
            pygame.draw.line(surface, (255, 235, 180), (0, 125), (WIDTH, 390), 2)
            pygame.draw.line(surface, spec.primary, (0, 390), (WIDTH, 125), 1)
            if spec.style in {"storm", "eclipse"}:
                for bolt in range(5):
                    x = (bolt * 211 + int(self.elapsed * 90)) % WIDTH
                    pygame.draw.line(surface, (245, 250, 255), (x, 0), (x - 85, 410), 2)
            elif spec.style in {"tide", "fungus"}:
                for wave in range(4):
                    y = 330 + wave * 34 + int(math.sin(self.elapsed * 2 + wave) * 12)
                    pygame.draw.arc(surface, spec.primary, Rect(-100, y - 70, WIDTH + 200, 150), 0, math.pi, 3)

    def draw_ship(self, surface: Surface) -> None:
        if self.boss is None:
            return
        x, y = int(self.player.position.x), int(self.player.position.y)
        cx, cy = x + 22, y + 30
        draw_glow(surface, (cx, cy - 18), (112, 231, 255), 44, 42)
        if self.player.shield > 0:
            shield_ratio = self.player.shield / max(1, self.player.shield_max)
            shield_radius = 47 + int(math.sin(self.elapsed * 5) * 2)
            pygame.draw.circle(surface, (145, 232, 255), (cx, cy + 4), shield_radius, 2)
            pygame.draw.arc(surface, (232, 252, 255),
                            Rect(cx - shield_radius - 4, cy + 4 - shield_radius - 4,
                                 (shield_radius + 4) * 2, (shield_radius + 4) * 2),
                            -1.2, -1.2 + math.tau * shield_ratio, 3)
        elif self.player.shield_broken:
            for shard in range(6):
                angle = self.elapsed * 0.7 + shard * math.tau / 6
                pygame.draw.line(surface, (125, 213, 255), (cx, cy + 4),
                                 (cx + int(math.cos(angle) * 52), cy + 4 + int(math.sin(angle) * 52)), 1)
        pygame.draw.ellipse(surface, (6, 8, 21), (x - 17, y + 42, 78, 18))
        pygame.draw.polygon(surface, (183, 229, 255),
                            [(cx, y - 12), (x - 4, y + 44), (cx, y + 32), (x + 48, y + 44)])
        pygame.draw.polygon(surface, (70, 142, 205),
                            [(cx, y - 12), (x + 6, y + 38), (x + 19, y + 21), (x + 31, y + 38)])
        pygame.draw.polygon(surface, (22, 48, 91),
                            [(cx, y - 5), (x + 11, y + 25), (cx, y + 31), (x + 33, y + 25)])
        pygame.draw.line(surface, (188, 247, 255), (x + 11, y + 25), (cx, y + 31), 2)
        pygame.draw.line(surface, (188, 247, 255), (cx, y + 31), (x + 33, y + 25), 2)
        pygame.draw.circle(surface, (255, 245, 190), (cx, y + 16), 4)
        pygame.draw.circle(surface, (94, 237, 255), (cx, y + 16), 2)
        for rune in range(3):
            rx = x + 15 + rune * 14
            pygame.draw.line(surface, self.boss.spec.primary, (rx, y + 35), (rx + 6, y + 39), 2)
            pygame.draw.line(surface, self.boss.spec.primary, (rx + 6, y + 39), (rx + 2, y + 44), 2)
        pygame.draw.polygon(surface, self.boss.spec.primary,
                            [(x + 3, y + 35), (x - 13, y + 56), (x + 16, y + 45)])
        pygame.draw.polygon(surface, self.boss.spec.primary,
                            [(x + 41, y + 35), (x + 57, y + 56), (x + 28, y + 45)])
        pygame.draw.circle(surface, (255, 244, 177), (cx, y + 3), 6)
        pygame.draw.line(surface, (136, 235, 255), (cx, y + 50), (cx, y + 72), 5)
        pygame.draw.line(surface, (230, 250, 255), (cx - 4, y + 51), (cx - 4, y + 72), 2)
        pygame.draw.line(surface, (240, 255, 255), (cx - 9, y + 22), (cx + 9, y + 22), 2)
        for mark in range(self.player.damage_level):
            sx = x - 4 + (mark * 13) % 42
            sy = y + 12 + (mark * 9) % 28
            pygame.draw.line(surface, (115, 41, 80), (sx, sy), (sx + 10, sy + 5), 2)
        if self.boss.spec.style == "tide":
            pygame.draw.arc(surface, (130, 250, 245), Rect(x - 22, y + 3, 72, 62), 0.4, 2.8, 3)
            pygame.draw.line(surface, (88, 226, 255), (x - 30, y + 42), (x - 62, y + 24), 3)
        elif self.boss.spec.style == "eclipse":
            pygame.draw.circle(surface, (12, 3, 30), (x + 42, y + 31), 13)
            pygame.draw.arc(surface, self.boss.spec.primary, Rect(x + 28, y + 17, 28, 28), 0, math.tau, 2)
        else:
            pygame.draw.line(surface, (238, 255, 255), (x + 44, y + 25), (x + 58, y + 17), 2)

    def draw_qte_hand(self, surface: Surface, center: tuple[int, int], facing: int, color: Color) -> None:
        x, y = center
        beat = math.sin(self.qte_anim * 9.0 + x * 0.01) * 8
        y += int(beat)
        pygame.draw.polygon(surface, color, [
            (x, y + 30), (x + facing * 28, y + 8), (x + facing * 48, y - 4),
            (x + facing * 36, y + 18), (x + facing * 58, y + 7),
            (x + facing * 43, y + 35), (x + facing * 20, y + 55),
        ])
        for offset in (0, 10, 20):
            pygame.draw.line(surface, (255, 239, 223), (x + facing * (32 + offset), y + 8),
                             (x + facing * (48 + offset), y - 4), 4)
        draw_glow(surface, (x + facing * 32, y + 17), color, 30, 32)

    def draw_qte_weapon(self, surface: Surface, center: tuple[int, int], facing: int, color: Color,
                        sword: bool = False) -> None:
        x, y = center
        strike = smoothstep((math.sin(self.qte_anim * 7.0) + 1) * 0.5)
        reach = int(42 + strike * 30)
        if sword:
            start = (x, y)
            tip = (x + facing * reach, y - 26)
            draw_glow(surface, tip, color, 32, 45)
            pygame.draw.line(surface, (246, 249, 255), start, tip, 7)
            pygame.draw.line(surface, color, start, tip, 3)
            pygame.draw.line(surface, (255, 255, 255), tip,
                             (tip[0] - facing * 10, tip[1] + 9), 2)
        else:
            fist_x = x + facing * reach
            draw_glow(surface, (fist_x, y), color, 35, 50)
            pygame.draw.circle(surface, color, (fist_x, y), 15)
            pygame.draw.line(surface, (255, 238, 220), (fist_x - facing * 8, y - 7),
                             (fist_x + facing * 8, y - 7), 3)
            pygame.draw.line(surface, (255, 238, 220), (fist_x - facing * 8, y),
                             (fist_x + facing * 8, y), 3)

    def draw_qte_fighter(self, surface: Surface, center: tuple[int, int], facing: int,
                         color: Color, boss: bool = False, striking: bool = False) -> None:
        """Full-body duel silhouettes for the QTE, not floating hands."""
        x, y = center
        scale = 1.18 if boss else 1.0
        body_w = int(34 * scale)
        body_h = int(66 * scale)
        head_r = int(16 * scale)
        shadow = Rect(x - int(35 * scale), y + int(44 * scale), int(70 * scale), 14)
        pygame.draw.ellipse(surface, (2, 3, 14), shadow)
        draw_glow(surface, (x, y), color, int(58 * scale), 44)
        cape = [
            (x, y - int(6 * scale)),
            (x - facing * int(22 * scale), y + int(62 * scale)),
            (x + facing * int(34 * scale), y + int(55 * scale)),
        ]
        pygame.draw.polygon(surface, (28, 25, 62) if not boss else (35, 12, 46), cape)
        pygame.draw.polygon(surface, color, [
            (x, y + int(2 * scale)),
            (x - body_w // 2, y + body_h),
            (x + body_w // 2, y + body_h),
        ])
        pygame.draw.circle(surface, (229, 234, 252), (x, y - int(25 * scale)), head_r)
        pygame.draw.circle(surface, (12, 10, 30), (x, y - int(25 * scale)), int(head_r * 0.72))
        pygame.draw.circle(surface, color, (x + facing * int(6 * scale), y - int(25 * scale)), max(2, int(4 * scale)))
        pygame.draw.line(surface, color, (x - int(9 * scale), y + int(13 * scale)),
                         (x - facing * int(26 * scale), y + int(34 * scale)), int(6 * scale))
        pygame.draw.line(surface, color, (x + int(9 * scale), y + int(13 * scale)),
                         (x + facing * int(26 * scale), y + int(30 * scale)), int(6 * scale))
        leg_y = y + body_h - 2
        pygame.draw.line(surface, (203, 217, 245), (x - int(7 * scale), leg_y),
                         (x - facing * int(20 * scale), leg_y + int(32 * scale)), int(7 * scale))
        pygame.draw.line(surface, (203, 217, 245), (x + int(7 * scale), leg_y),
                         (x + facing * int(19 * scale), leg_y + int(28 * scale)), int(7 * scale))
        if striking:
            hand_x = x + facing * int(50 * scale)
            hand_y = y + int(9 * scale)
            pygame.draw.line(surface, (255, 239, 218), (x + facing * int(16 * scale), y + int(10 * scale)),
                             (hand_x, hand_y), int(8 * scale))
            pygame.draw.circle(surface, (255, 239, 218), (hand_x, hand_y), int(10 * scale))
            pygame.draw.line(surface, (255, 255, 255), (hand_x, hand_y),
                             (hand_x + facing * int(28 * scale), hand_y - int(12 * scale)), 3)
        if boss:
            horn = int(18 * scale)
            pygame.draw.polygon(surface, (240, 244, 255), [
                (x - head_r, y - int(30 * scale)), (x - horn, y - int(55 * scale)),
                (x, y - int(36 * scale)), (x + horn, y - int(55 * scale)),
                (x + head_r, y - int(30 * scale)),
            ])

    def draw_qte_actual_fighters(self, surface: Surface, lira_center: tuple[int, int],
                                 boss_center: tuple[int, int], lira_strike: bool,
                                 boss_strike: bool) -> None:
        """Reuse the real Player and PantheonBoss sprites inside the QTE."""
        if self.boss is None:
            return
        saved_player = (Vector2(self.player.position), self.player.facing, self.player.invulnerable,
                        self.player.attack_timer, self.player.walk_time)
        saved_boss = (Vector2(self.boss.position), self.boss.facing, self.boss.anim_time,
                      self.boss.attack_timer)
        lira_x, lira_y = lira_center
        boss_x, boss_y = boss_center
        self.player.position = Vector2(lira_x - self.player.width // 2, lira_y - 58)
        self.player.facing = 1
        self.player.invulnerable = 0
        self.player.attack_timer = 0.12 if lira_strike else 0
        self.player.walk_time = self.qte_anim * 12
        self.boss.position = Vector2(boss_x - self.boss.width // 2, boss_y - self.boss.height + 24)
        self.boss.facing = -1
        self.boss.anim_time = self.qte_anim * 8
        self.boss.attack_timer = 0.18 if boss_strike else 0
        self.player.draw(surface, 0)
        self.boss.draw(surface, 0)
        self.player.position, self.player.facing, self.player.invulnerable, self.player.attack_timer, self.player.walk_time = saved_player
        self.boss.position, self.boss.facing, self.boss.anim_time, self.boss.attack_timer = saved_boss

    def draw_qte(self, surface: Surface) -> None:
        if self.boss is None:
            return
        overlay = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((5, 4, 18, 220))
        surface.blit(overlay, (0, 0))
        panel = Rect(126, 62, WIDTH - 252, 400)
        pygame.draw.rect(surface, (14, 12, 37), panel, border_radius=18)
        pygame.draw.rect(surface, self.boss.spec.primary, panel, 2, border_radius=18)
        draw_glow(surface, (WIDTH // 2, 300), self.boss.spec.primary, 115, 20)
        draw_text(surface, "CONFRONTO DE VOTOS", (WIDTH // 2, 86), 29, (255, 226, 166), center=True, bold=True)
        draw_text(surface, "Lira e o guardião trocam golpes pelo destino de Noa", (WIDTH // 2, 119), 15,
                  (205, 211, 237), center=True)
        pressure = clamp(self.qte_hits / max(1, self.qte_target), 0, 1)
        rhythm = abs(math.sin(self.qte_anim * 4.7))
        closing = int(pressure * 130 + self.qte_lunge * 28)
        lira_x = 192 + closing + int(rhythm * 12)
        boss_x = 768 - closing - int(rhythm * 12)
        lira_y = 327 - int(abs(math.sin(self.qte_anim * 4.7)) * 74) - int(self.qte_lunge * 24)
        boss_y = 312 - int(abs(math.sin(self.qte_anim * 4.7 + math.pi)) * 74) - int(self.qte_lunge * 24)
        sword_mode = int(self.qte_anim * 2.5) % 2 == 1
        self.draw_qte_actual_fighters(
            surface, (lira_x, lira_y), (boss_x, boss_y),
            self.qte_last_side > 0 or self.qte_lunge > 0.3,
            self.qte_last_side < 0 or self.qte_lunge > 0.3,
        )
        pygame.draw.line(surface, (144, 179, 221), (lira_x + 42, lira_y + 6),
                         (boss_x - 50, boss_y + 2), 2)
        impact_radius = 18 + int((math.sin(self.qte_anim * 10) + 1) * 7)
        if self.qte_hit_flash > 0:
            impact_radius += int(24 * self.qte_hit_flash)
        clash_center = (WIDTH // 2, 286 - int(self.qte_lunge * 12))
        draw_glow(surface, clash_center, (255, 238, 170), impact_radius + 25, 75)
        pygame.draw.circle(surface, (255, 243, 194), clash_center, impact_radius, 3)
        for angle in range(0, 360, 45):
            radians = math.radians(angle) + self.qte_anim
            pygame.draw.line(surface, (255, 238, 170),
                             (clash_center[0] + int(math.cos(radians) * 25),
                              clash_center[1] + int(math.sin(radians) * 25)),
                             (clash_center[0] + int(math.cos(radians) * 48),
                              clash_center[1] + int(math.sin(radians) * 48)), 2)
        draw_text(surface, "ESPACO! ATAQUE O CHOQUE", (WIDTH // 2, 390), 23,
                  (255, 241, 197), center=True, bold=True)
        draw_text(surface, f"{self.qte_hits}/{self.qte_target} IMPACTOS", (WIDTH // 2, 420), 18,
                  self.boss.spec.primary, center=True, bold=True)
        pygame.draw.rect(surface, (25, 21, 50), (WIDTH // 2 - 220, 447, 440, 14), border_radius=7)
        pygame.draw.rect(surface, (173, 214, 255), (WIDTH // 2 - 217, 450, int(434 * pressure), 8), border_radius=4)
        draw_text(surface, "LIRA AVANÇA", (WIDTH // 2 - 275, 454), 11, (173, 214, 255), center=True, bold=True)
        draw_text(surface, "GUARDIÃO RESISTE", (WIDTH // 2 + 275, 454), 11, self.boss.spec.primary, center=True, bold=True)
        pygame.draw.rect(surface, (25, 21, 50), (WIDTH // 2 - 150, 481, 300, 11), border_radius=6)
        pygame.draw.rect(surface, self.boss.spec.primary,
                         (WIDTH // 2 - 147, 483, int(294 * self.qte_timer / 4.2), 7), border_radius=4)
        draw_text(surface, "Aperte sem parar: quem perder o choque recebe dano",
                  (WIDTH // 2, 516), 14,
                  (176, 190, 219), center=True)

    def draw_3d_fight(self, surface: Surface) -> None:
        if self.boss is None:
            return
        spec = self.boss.spec
        map_colors = {
            "abyss": (8, 5, 28), "crystal": (8, 25, 40),
            "fungus": (20, 8, 31), "clock": (27, 18, 12),
            "thorn": (22, 5, 20),
        }
        surface.fill(map_colors.get(spec.style, (8, 5, 28)))
        horizon = 190
        portal = (WIDTH // 2, 148)
        draw_glow(surface, portal, spec.primary, 132, 50)
        pygame.draw.circle(surface, (112, 35, 168), portal, 92 + int(math.sin(self.elapsed * 2) * 5), 4)
        for row in range(9):
            y = horizon + int((row / 8) ** 1.8 * 350)
            pygame.draw.line(surface, (86, 47, 145), (0, y), (WIDTH, y), 1)
        for x in range(-800, 1801, 80):
            pygame.draw.line(surface, (57, 40, 116), (WIDTH // 2, horizon), (x, HEIGHT), 1)
        for ray in range(7):
            x = int((ray / 6) * WIDTH)
            pygame.draw.line(surface, (*spec.primary, 80), (WIDTH // 2, horizon), (x, HEIGHT), 2)
        for depth in range(9):
            scale = 0.25 + depth / 10
            width = int(56 + scale * 270)
            y = int(horizon + scale * 275)
            x = WIDTH // 2 + int(math.sin(self.elapsed * 0.7 + depth) * (22 + depth * 6))
            pygame.draw.polygon(surface, (25, 14 + depth * 2, 58), [
                (x - width, y), (x + width, y), (x + width - 24, y + 10), (x - width + 24, y + 10)
            ])
            pygame.draw.line(surface, spec.primary, (x - width, y), (x + width, y), 2)
        for shard in range(16):
            angle = self.elapsed * (0.25 + shard % 3 * 0.08) + shard * math.tau / 16
            distance = 105 + (shard % 5) * 40
            sx = WIDTH // 2 + int(math.cos(angle) * distance)
            sy = 190 + int(math.sin(angle) * distance * 0.62)
            size = 7 + shard % 5
            pygame.draw.polygon(surface, spec.primary, [
                (sx, sy - size), (sx + size, sy + size), (sx - size, sy + size // 2)
            ])
        if spec.style == "crystal":
            for column in range(7):
                x = column * 158 - int(self.elapsed * 18) % 158
                height = 100 + (column % 3) * 55
                pygame.draw.polygon(surface, (36, 117, 139), [
                    (x, 380), (x + 35, 380 - height), (x + 76, 380)
                ])
                pygame.draw.line(surface, (172, 255, 246), (x + 35, 380 - height),
                                 (x + 46, 380), 2)
        elif spec.style == "fungus":
            for index in range(12):
                x = (index * 103 + int(self.elapsed * (12 + index % 3))) % (WIDTH + 100) - 50
                y = 255 + (index % 4) * 28
                pygame.draw.line(surface, (83, 29, 96), (x, 430), (x + 40, y), 4)
                pygame.draw.circle(surface, (142, 62, 159), (x + 40, y), 22 + index % 3 * 5, 2)
                draw_glow(surface, (x + 40, y), spec.primary, 26, 24)
        elif spec.style == "clock":
            for ring in range(4):
                radius = 70 + ring * 58
                pygame.draw.circle(surface, (103, 71, 39), portal, radius, 2)
                for tick in range(0, 360, 30):
                    angle = math.radians(tick) + self.elapsed * (0.1 + ring * 0.03)
                    pygame.draw.line(surface, spec.primary, portal,
                                     (portal[0] + int(math.cos(angle) * radius),
                                      portal[1] + int(math.sin(angle) * radius)), 1)
        elif spec.style == "thorn":
            for index in range(10):
                x = index * 115 - int(self.elapsed * 22) % 115
                pygame.draw.line(surface, (88, 17, 63), (x, 440), (x + 120, 155), 5)
                pygame.draw.polygon(surface, spec.primary, [
                    (x + 120, 155), (x + 94, 181), (x + 135, 188)
                ])
        for index in range(12):
            x = (index * 103 + int(self.elapsed * 24)) % WIDTH
            y = 95 + (index * 37) % 250
            pygame.draw.circle(surface, spec.primary, (x, y), 2 + index % 3)
        for hazard in self.hazards:
            hazard.draw(surface, 0)
        for potion in self.potions:
            potion.draw(surface, 0, spec.primary)
        self.draw_blood_pools(surface, 0)
        for particle in self.particles:
            particle.draw(surface, 0)
        self.boss.draw(surface, 0)
        self.player.draw(surface, 0)
        map_title = {
            "abyss": "DOMÍNIO 3D — VAZIO INFINITO",
            "crystal": "DOMÍNIO 3D — CATEDRAL DE PRISMAS",
            "fungus": "DOMÍNIO 3D — FLORESTA DOS ESPOROS",
            "clock": "DOMÍNIO 3D — ENGRENAGENS DO TEMPO",
            "thorn": "DOMÍNIO 3D — JARDIM VERTICAL",
        }.get(spec.style, "DOMÍNIO 3D")
        draw_text(surface, f"TERCEIRA FASE — {map_title}", (WIDTH // 2, 28), 21, (255, 229, 170), center=True, bold=True)
        draw_text(surface, "O cenário respira, se move e reage ao ritmo do guardião",
                  (WIDTH // 2, 57), 14, (197, 191, 230), center=True)
        self.draw_battle_hud(surface)
        if self.qte_active:
            self.draw_qte(surface)

    def draw_shooter_fight(self, surface: Surface) -> None:
        if self.boss is None:
            return
        spec = self.boss.spec
        ship_backgrounds = {
            "storm": (4, 8, 25), "tide": (3, 24, 42),
            "eclipse": (10, 3, 28), "forge": (30, 8, 3),
        }
        surface.fill(ship_backgrounds.get(spec.style, (4, 8, 25)))
        for index in range(44):
            x = (index * 97 + int(self.elapsed * (15 + index % 4))) % WIDTH
            y = (index * 53 + int(self.elapsed * (38 + index % 3))) % HEIGHT
            star_color = spec.primary if index % 4 == 0 else (155, 185, 241)
            pygame.draw.circle(surface, star_color, (x, y), 1 + index % 2)
        for lane_x in (110, 300, 480, 660, 850):
            pygame.draw.line(surface, (32, 74, 117), (lane_x, 70), (lane_x, HEIGHT), 1)
            pygame.draw.line(surface, (75, 156, 194), (lane_x, 90), (lane_x, 118), 2)
        arena_center = (480, 150)
        if spec.style == "tide":
            for wave in range(6):
                y = 90 + wave * 72 + int(math.sin(self.elapsed * 2.0 + wave) * 14)
                pygame.draw.arc(surface, spec.primary, Rect(-140, y - 70, WIDTH + 280, 150), 0, math.pi, 3)
        elif spec.style == "eclipse":
            pygame.draw.circle(surface, (1, 1, 8), arena_center, 142)
            pygame.draw.circle(surface, spec.primary, arena_center, 156, 3)
            for ray in range(10):
                angle = self.elapsed * 0.2 + ray * math.tau / 10
                pygame.draw.line(surface, spec.primary, arena_center,
                                 (arena_center[0] + int(math.cos(angle) * 205),
                                  arena_center[1] + int(math.sin(angle) * 205)), 1)
        elif spec.style == "forge":
            for column in range(7):
                x = 72 + column * 142
                height = 90 + int(abs(math.sin(self.elapsed * 2.3 + column)) * 170)
                pygame.draw.line(surface, (120, 34, 18), (x, 80), (x, HEIGHT), 4)
                pygame.draw.line(surface, (255, 106, 30), (x + 8, 100), (x + 8, 100 + height), 2)
                draw_glow(surface, (x + 8, 100 + height), (255, 120, 35), 24, 34)
        draw_glow(surface, arena_center, spec.primary, 165, 48)
        pygame.draw.ellipse(surface, (25, 54, 120), (365, 35, 230, 230))
        pygame.draw.ellipse(surface, spec.primary, (400, 70, 160, 160), 4)
        for ring in range(3):
            rect = Rect(388 - ring * 12, 58 - ring * 12, 184 + ring * 24, 184 + ring * 24)
            start = self.elapsed * (0.5 + ring * 0.2)
            pygame.draw.arc(surface, spec.primary, rect, start, start + 2.0, 1)
        for hazard in self.hazards:
            hazard.draw(surface, 0)
        for potion in self.potions:
            potion.draw(surface, 0, spec.primary)
        self.draw_blood_pools(surface, 0)
        for particle in self.particles:
            particle.draw(surface, 0)
        self.draw_ship(surface)
        self.boss.draw(surface, 0)
        ship_title = {
            "storm": "TEMPESTADE ORBITAL", "tide": "MARÉ ESTELAR",
            "eclipse": "ECLIPSE DE NAVE", "forge": "FORNALHA VERTICAL",
        }.get(spec.style, "BATALHA ESTELAR")
        draw_text(surface, f"TERCEIRA FASE — {ship_title}", (WIDTH // 2, 27), 22, (255, 229, 170), center=True, bold=True)
        draw_text(surface, "A/D ou setas movem a nave   W/S ou ↑/↓ desviam   ESPAÇO atira", (WIDTH // 2, 55), 13,
                  (197, 205, 232), center=True)
        self.draw_battle_hud(surface)
        if self.qte_active:
            self.draw_qte(surface)

    def draw_battle_hud(self, surface: Surface) -> None:
        if self.boss is None:
            return
        draw_text(surface, "LIRA", (24, 17), 13, (185, 202, 231), bold=True)
        pygame.draw.rect(surface, (9, 12, 28), (24, 38, 220, 16), border_radius=5)
        pygame.draw.rect(surface, (98, 203, 232), (27, 41, int(214 * self.player.health / 100), 10), border_radius=4)
        if self.player.shield > 0:
            draw_text(surface, "ESCUDO LIRA", (24, 61), 10, (166, 230, 255), bold=True)
            pygame.draw.rect(surface, (12, 24, 40), (24, 75, 220, 9), border_radius=4)
            pygame.draw.rect(surface, (123, 221, 255),
                             (27, 77, int(214 * self.player.shield / max(1, self.player.shield_max)), 5),
                             border_radius=3)
        elif self.player.shield_broken:
            draw_text(surface, "ESCUDO LIRA QUEBRADO", (24, 61), 10, (255, 155, 181), bold=True)
        dodge_label = "ESQUIVA PRONTA" if self.player.dodge_cooldown <= 0 else (
            f"ESQUIVA {self.player.dodge_cooldown:.1f}s"
        )
        dodge_color = (178, 235, 255) if self.player.dodge_cooldown <= 0 else (137, 151, 181)
        draw_text(surface, f"SHIFT  {dodge_label}", (24, 94), 10, dodge_color, bold=True)
        label = f"{self.boss.spec.name} — FASE {self.boss.phase}/3"
        draw_text(surface, label, (WIDTH - 24, 17), 13, self.boss.spec.primary, bold=True)
        pygame.draw.rect(surface, (9, 12, 28), (WIDTH - 284, 38, 260, 16), border_radius=5)
        health_max = self.finale_health_max if self.dimension_mode == "finale" else self.boss.spec.max_health
        health_ratio = clamp(self.boss.health / max(1, health_max), 0.0, 1.0)
        pygame.draw.rect(surface, self.boss.spec.primary,
                         (WIDTH - 281, 41, int(254 * health_ratio), 10), border_radius=4)
        if self.boss.shield > 0:
            draw_text(surface, "ESCUDO", (WIDTH - 284, 61), 10, (174, 229, 255), bold=True)
            pygame.draw.rect(surface, (14, 25, 40), (WIDTH - 284, 75, 260, 9), border_radius=4)
            pygame.draw.rect(surface, (118, 216, 255),
                             (WIDTH - 281, 77,
                              int(254 * self.boss.shield / max(1, self.boss.shield_max)), 5),
                             border_radius=3)
        elif self.boss.shield_broken:
            draw_text(surface, "ESCUDO QUEBRADO", (WIDTH - 284, 61), 10, (255, 156, 176), bold=True)
        if self.boss.attack_timer > 0 and not self.qte_active:
            draw_text(surface, "ATAQUE TELEGRAFADO", (WIDTH // 2, 91), 13,
                      (255, 184, 126), center=True, bold=True)
        if self.combat_feedback_timer > 0:
            feedback_alpha = int(255 * min(1.0, self.combat_feedback_timer / 0.18))
            feedback = Surface((WIDTH, 42), pygame.SRCALPHA)
            draw_text(feedback, self.combat_feedback, (WIDTH // 2, 20), 20,
                      (255, 239, 181), center=True, bold=True)
            feedback.set_alpha(feedback_alpha)
            surface.blit(feedback, (0, 118))

    def draw_blood_pools(self, surface: Surface, camera_x: float) -> None:
        for position, radius, color in self.blood_pools:
            x = int(position.x - camera_x)
            y = int(position.y)
            pygame.draw.ellipse(surface, (48, 8, 22), (x - int(radius), y - 3,
                                                        int(radius * 2.2), 8))
            pygame.draw.circle(surface, color, (x + int(radius * 0.7), y - 1), max(2, int(radius * 0.28)))
            pygame.draw.line(surface, color, (x - int(radius * 0.4), y - 1),
                             (x - int(radius * 0.4), y + int(radius * 0.8)), 2)

    def draw_phase_intro(self, surface: Surface) -> None:
        if self.boss is None or self.intro_timer <= 0:
            return
        progress = 1.0 - self.intro_timer / max(0.01, self.intro_total)
        reveal = smoothstep(progress)
        overlay = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((2, 2, 12, int(170 * (1 - reveal * 0.55))))
        surface.blit(overlay, (0, 0))
        bar_height = int(45 * (1 - reveal))
        if bar_height:
            pygame.draw.rect(surface, (2, 2, 12), (0, 0, WIDTH, bar_height))
            pygame.draw.rect(surface, (2, 2, 12), (0, HEIGHT - bar_height, WIDTH, bar_height))
        center = (WIDTH // 2, 235)
        draw_glow(surface, center, self.boss.spec.primary, int(105 + reveal * 48), 68)
        ring = int(72 + reveal * 115)
        pygame.draw.circle(surface, self.boss.spec.primary, center, ring, 3)
        pygame.draw.circle(surface, (255, 235, 176), center, max(10, ring - 18), 1)
        for ray in range(12):
            angle = self.elapsed * 0.8 + ray * math.tau / 12
            start = Vector2(center) + Vector2(math.cos(angle), math.sin(angle)) * 30
            end = Vector2(center) + Vector2(math.cos(angle), math.sin(angle)) * ring
            pygame.draw.line(surface, self.boss.spec.primary, start, end, 2)
        title_y = int(150 - reveal * 18)
        alpha = int(clamp(1.0 - abs(progress - 0.55) * 1.45, 0.25, 1.0) * 255)
        title_layer = Surface((WIDTH, 110), pygame.SRCALPHA)
        draw_text(title_layer, f"FASE {self.intro_phase}", (WIDTH // 2, 18), 17,
                  (255, 222, 151), center=True, bold=True)
        draw_text(title_layer, self.boss.spec.name.upper(), (WIDTH // 2, 52), 34,
                  self.boss.spec.primary, center=True, bold=True)
        draw_text(title_layer, self.boss.spec.phases[self.intro_phase - 1].upper(), (WIDTH // 2, 86), 16,
                  (237, 232, 255), center=True, bold=True)
        title_layer.set_alpha(alpha)
        surface.blit(title_layer, (0, title_y))
        if self.intro_phase == 3:
            draw_text(surface, self.genre_title, (WIDTH // 2, 386), 18,
                      (255, 232, 170), center=True, bold=True)
        else:
            draw_text(surface, "O PANTEÃO PRENDE A RESPIRAÇÃO", (WIDTH // 2, 386), 15,
                      (211, 219, 244), center=True)

    def draw_domain_expansion(self, surface: Surface) -> None:
        if self.boss is None or not self.domain_active:
            return
        progress = 1.0 - self.domain_timer / max(0.01, self.domain_total)
        reveal = smoothstep(progress)
        spec = self.boss.spec
        center = (WIDTH // 2, HEIGHT // 2)
        veil = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((*spec.secondary, int(145 - reveal * 55)))
        surface.blit(veil, (0, 0))
        wipe = int((1 - reveal) * WIDTH * 0.55)
        pygame.draw.rect(surface, (4, 2, 16), (0, 0, wipe, HEIGHT))
        pygame.draw.rect(surface, (4, 2, 16), (WIDTH - wipe, 0, wipe, HEIGHT))
        draw_glow(surface, center, spec.primary, int(90 + reveal * 180), 65)
        ring = int(35 + reveal * 250)
        pygame.draw.circle(surface, spec.primary, center, ring, 4)
        pygame.draw.circle(surface, (255, 239, 179), center, max(12, ring - 28), 2)
        for ray in range(18):
            angle = self.elapsed * 0.8 + ray * math.tau / 18
            length = ring + 35 + (ray % 3) * 22
            pygame.draw.line(surface, spec.primary,
                             (center[0] + int(math.cos(angle) * 28),
                              center[1] + int(math.sin(angle) * 28)),
                             (center[0] + int(math.cos(angle) * length),
                              center[1] + int(math.sin(angle) * length)), 2)
        if spec.style in {"fungus", "thorn"}:
            for index in range(9):
                x = index * 120 + int(math.sin(self.elapsed + index) * 20)
                pygame.draw.line(surface, spec.primary, (x, HEIGHT), (x + 60, 130), 5)
        elif spec.style in {"forge", "tide"}:
            for index in range(6):
                y = 100 + index * 70 + int(math.sin(self.elapsed * 2 + index) * 20)
                pygame.draw.arc(surface, spec.primary, Rect(-120, y - 55, WIDTH + 240, 130), 0, math.pi, 4)
        elif spec.style in {"crystal", "eclipse"}:
            for index in range(14):
                angle = self.elapsed * 0.25 + index * math.tau / 14
                distance = 110 + index % 4 * 48
                sx = center[0] + int(math.cos(angle) * distance)
                sy = center[1] + int(math.sin(angle) * distance * 0.65)
                pygame.draw.polygon(surface, spec.primary, [
                    (sx, sy - 10), (sx + 10, sy + 13), (sx - 10, sy + 10)
                ])
        title = Surface((WIDTH, 150), pygame.SRCALPHA)
        draw_text(title, self.domain_voice, (WIDTH // 2, 25), 22, (255, 232, 170), center=True, bold=True)
        draw_text(title, self.domain_text, (WIDTH // 2, 76), 40, spec.primary, center=True, bold=True)
        draw_text(title, self.boss.spec.name.upper(), (WIDTH // 2, 122), 15,
                  (239, 237, 255), center=True, bold=True)
        title.set_alpha(int(clamp(1 - abs(progress - 0.5) * 1.6, 0.2, 1) * 255))
        surface.blit(title, (0, 82))
        if progress < 0.72:
            draw_text(surface, "A REALIDADE OBEDECE AO GUARDIÃO", (WIDTH // 2, 438), 15,
                      (218, 225, 245), center=True, bold=True)

    def draw_victory(self, surface: Surface) -> None:
        if self.boss is None or not self.victory_active:
            return
        spec = self.boss.spec
        progress = 1.0 - self.victory_timer / max(0.01, self.victory_total)
        ease = smoothstep(progress)
        center = (WIDTH // 2, 268)
        veil = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((3, 2, 16, int(80 + ease * 95)))
        surface.blit(veil, (0, 0))
        draw_glow(surface, center, spec.primary, int(120 + ease * 160), 55)
        pulse = int(math.sin(self.elapsed * 10) * 8)

        if self.victory_style == "abyss":
            for ring in range(5):
                radius = int(40 + ease * 260 + ring * 22 + pulse)
                pygame.draw.circle(surface, spec.primary, center, radius, max(1, 5 - ring))
            pygame.draw.line(surface, (255, 244, 195), (0, 470), (WIDTH, 90), 3)
            pygame.draw.line(surface, spec.primary, (0, 90), (WIDTH, 470), 2)
            title = "A COROA SE PARTE"
        elif self.victory_style == "storm":
            for bolt in range(11):
                x = int((bolt * 101 + self.elapsed * 180) % (WIDTH + 180)) - 90
                pygame.draw.line(surface, (238, 251, 255), (x, 0), (x - 70, HEIGHT), 3)
            pygame.draw.circle(surface, spec.primary, center, int(55 + ease * 165), 4)
            title = "O CÉU CAI EM SILÊNCIO"
        elif self.victory_style == "crystal":
            for shard in range(24):
                angle = self.victory_seed + shard * math.tau / 24
                distance = int(35 + ease * 310 + (shard % 4) * 16)
                sx = center[0] + int(math.cos(angle) * distance)
                sy = center[1] + int(math.sin(angle) * distance * 0.65)
                size = 8 + shard % 9
                pygame.draw.polygon(surface, (226, 255, 250), [
                    (sx, sy - size), (sx + size, sy + size), (sx - size, sy + size // 2)
                ])
            title = "A MONTANHA VIRA ESTRELAS"
        elif self.victory_style == "fungus":
            for index in range(15):
                x = (index * 79 + int(self.elapsed * 34)) % WIDTH
                y = 405 - int(abs(math.sin(self.elapsed * 2 + index)) * ease * 250)
                pygame.draw.line(surface, spec.secondary, (x, 520), (x, y), 4)
                pygame.draw.circle(surface, spec.primary, (x, y), 10 + index % 5, 3)
            title = "A FLORESTA RESPIRA"
        elif self.victory_style == "forge":
            for ray in range(14):
                angle = self.victory_seed + ray * math.tau / 14
                end = (center[0] + int(math.cos(angle) * (90 + ease * 350)),
                       center[1] + int(math.sin(angle) * (90 + ease * 260)))
                pygame.draw.line(surface, (255, 224, 112), center, end, 4)
            pygame.draw.circle(surface, (255, 245, 168), center, int(26 + ease * 90), 5)
            title = "A FORNALHA APAGA"
        elif self.victory_style == "tide":
            for wave in range(6):
                height = int(80 + ease * 240 + wave * 18)
                pygame.draw.arc(surface, spec.primary,
                                Rect(-160, 220 - height // 2 + wave * 8, WIDTH + 320, height),
                                0, math.pi, 5)
            title = "A MARÉ DEVOLVE O SILÊNCIO"
        elif self.victory_style == "clock":
            pygame.draw.circle(surface, spec.primary, center, int(80 + ease * 190), 4)
            for angle in range(0, 360, 30):
                radians = math.radians(angle) + self.elapsed * 0.4
                pygame.draw.line(surface, (255, 244, 180), center,
                                 (center[0] + int(math.cos(radians) * (80 + ease * 220)),
                                  center[1] + int(math.sin(radians) * (80 + ease * 220))), 2)
            title = "O ÚLTIMO SEGUNDO PARA"
        elif self.victory_style == "eclipse":
            pygame.draw.circle(surface, (0, 0, 5), center, int(42 + ease * 180))
            pygame.draw.circle(surface, spec.primary, center, int(60 + ease * 205), 4)
            for ray in range(18):
                angle = self.victory_seed + ray * math.tau / 18
                pygame.draw.line(surface, spec.primary, center,
                                 (center[0] + int(math.cos(angle) * (80 + ease * 330)),
                                  center[1] + int(math.sin(angle) * (80 + ease * 260))), 2)
            title = "A LUZ RECORDA O NOME"
        elif self.victory_style == "inferno":
            for ring in range(7):
                radius = int(35 + ease * 260 + ring * 18 + pulse)
                pygame.draw.arc(surface, (255, 91 + ring * 18, 35),
                                Rect(center[0] - radius, center[1] - radius // 2,
                                     radius * 2, radius), 0, math.tau, 4)
            title = "O SOL SE APAGA POR DENTRO"
        elif self.victory_style == "mecha":
            self.draw_final_mecha(surface, center, 1, 1.0, ease)
            for ray in range(18):
                angle = self.victory_seed + ray * math.tau / 18
                distance = 110 + ease * 300
                pygame.draw.line(surface, (255, 116, 55), center,
                                 (center[0] + int(math.cos(angle) * distance),
                                  center[1] + int(math.sin(angle) * distance * 0.65)), 3)
            title = "O ÚLTIMO VOTO SE TORNA LUZ"
        else:
            for thorn in range(12):
                angle = self.victory_seed + thorn * math.tau / 12
                inner = 30 + ease * 45
                outer = 100 + ease * 250
                a = (center[0] + int(math.cos(angle) * inner), center[1] + int(math.sin(angle) * inner))
                b = (center[0] + int(math.cos(angle) * outer), center[1] + int(math.sin(angle) * outer))
                pygame.draw.line(surface, spec.primary, a, b, 5)
                pygame.draw.polygon(surface, spec.primary, [b,
                    (b[0] - int(math.sin(angle) * 18), b[1] + int(math.cos(angle) * 18)),
                    (b[0] + int(math.sin(angle) * 18), b[1] - int(math.cos(angle) * 18))])
            title = "O JARDIM ABRE CAMINHO"

        for ring in range(3):
            radius = int(22 + ease * 120 + ring * 24 + pulse)
            pygame.draw.circle(surface, (255, 238, 181), center, radius, 2)
        title_alpha = int(clamp(1.0 - abs(progress - 0.66) * 1.2, 0.2, 1.0) * 255)
        label = Surface((WIDTH, 120), pygame.SRCALPHA)
        draw_text(label, "FINALIZAÇÃO", (WIDTH // 2, 18), 16, (255, 224, 148), center=True, bold=True)
        draw_text(label, title, (WIDTH // 2, 57), 31, spec.primary, center=True, bold=True)
        draw_text(label, spec.name.upper(), (WIDTH // 2, 94), 15, (239, 235, 255), center=True, bold=True)
        label.set_alpha(title_alpha)
        surface.blit(label, (0, 96))

    def draw_apotheosis_fight(self, surface: Surface) -> None:
        """Third phases become a different visual genre for each guardian."""
        if self.boss is None:
            return
        spec = self.boss.spec
        self.draw_background(surface)
        center = (WIDTH // 2, 260)
        if spec.style == "crystal":
            for index in range(18):
                angle = self.elapsed * 0.6 + index * math.tau / 18
                radius = 90 + (index % 4) * 55
                point = (center[0] + int(math.cos(angle) * radius),
                         center[1] + int(math.sin(angle) * radius))
                pygame.draw.polygon(surface, spec.primary, [
                    point, (point[0] + 14, point[1] - 28), (point[0] + 25, point[1] + 8)
                ])
        elif spec.style == "fungus":
            for index in range(11):
                x = (index * 101 + int(math.sin(self.elapsed + index) * 22)) % WIDTH
                pygame.draw.line(surface, spec.secondary, (x, HEIGHT), (x + 40, 275), 5)
                pygame.draw.circle(surface, spec.primary, (x + 40, 275), 16 + index % 3 * 5, 2)
        elif spec.style == "forge":
            for index in range(9):
                x = (index * 137 + int(self.elapsed * 35)) % WIDTH
                height = 90 + (index % 4) * 30
                pygame.draw.line(surface, (255, 222, 110), (x, HEIGHT), (x - 24, HEIGHT - height), 3)
                draw_glow(surface, (x, HEIGHT - height), (255, 90, 32), 22, 28)
        elif spec.style == "tide":
            for wave in range(4):
                offset = int(math.sin(self.elapsed * 1.7 + wave) * 22)
                rect = Rect(-130 - offset, 130 + wave * 63, WIDTH + 260, 190)
                pygame.draw.arc(surface, spec.primary, rect, 0, math.pi, 5)
        elif spec.style == "clock":
            pygame.draw.circle(surface, spec.secondary, center, 205, 3)
            for angle in range(0, 360, 30):
                radians = math.radians(angle) + self.elapsed * 0.25
                pygame.draw.line(surface, spec.primary, center,
                                 (center[0] + int(math.cos(radians) * 205),
                                  center[1] + int(math.sin(radians) * 205)), 2)
            pygame.draw.line(surface, (255, 244, 180), center,
                             (center[0] + int(math.cos(self.elapsed) * 160),
                              center[1] + int(math.sin(self.elapsed) * 160)), 5)
        elif spec.style == "eclipse":
            draw_glow(surface, center, spec.primary, 190, 42)
            pygame.draw.circle(surface, (1, 1, 8), center, 118)
            pygame.draw.circle(surface, spec.primary, center, 132, 3)
            pygame.draw.arc(surface, (255, 245, 205), Rect(300, 130, 320, 260),
                            self.elapsed * 0.4, self.elapsed * 0.4 + 2.2, 4)
        elif spec.style == "thorn":
            for index in range(9):
                x = index * 125 - int(self.camera_x * 0.3) % 125
                pygame.draw.line(surface, spec.secondary, (x, HEIGHT), (x + 110, 180), 5)
                pygame.draw.polygon(surface, spec.primary, [(x + 110, 180), (x + 95, 208), (x + 128, 202)])

        for platform in self.platforms:
            rect = platform.move(-int(self.camera_x), 0)
            color = spec.secondary if platform.top >= GROUND_Y else spec.primary
            pygame.draw.rect(surface, color, rect)
            pygame.draw.line(surface, spec.primary, (rect.left, rect.top), (rect.right, rect.top), 3)
        for potion in self.potions:
            potion.draw(surface, self.camera_x, spec.primary)
        self.draw_blood_pools(surface, self.camera_x)
        for hazard in self.hazards:
            hazard.draw(surface, self.camera_x)
        for particle in self.particles:
            particle.draw(surface, self.camera_x)
        self.boss.draw(surface, self.camera_x)
        self.player.draw(surface, self.camera_x)
        self.draw_battle_hud(surface)
        draw_text(surface, f"APOTEOSE: {self.boss.phase_name.upper()}",
                  (WIDTH // 2, 78), 18, spec.primary, center=True, bold=True)
        draw_text(surface, "O gênero mudou. Aprenda o novo ritmo do domínio.",
                  (WIDTH // 2, HEIGHT - 22), 12, (216, 224, 242), center=True)
        if self.qte_active:
            self.draw_qte(surface)

    def draw_final_mecha(self, surface: Surface, center: tuple[int, int], scale: float,
                         assembly: float = 1.0, strike: float = 0.0) -> None:
        """Angular, readable mecha silhouette assembled from layered shapes."""
        cx, cy = center
        s = max(1, int(scale))
        glow = (76, 210, 255)
        draw_glow(surface, (cx, cy - 28 * s), glow, 92 * s, 52)
        body = Rect(cx - 48 * s, cy - 12 * s, 96 * s, 100 * s)
        pygame.draw.polygon(surface, (24, 39, 70), [
            (cx - 42 * s, cy - 12 * s), (cx + 42 * s, cy - 12 * s),
            (cx + 60 * s, cy + 70 * s), (cx + 28 * s, cy + 95 * s),
            (cx - 30 * s, cy + 95 * s), (cx - 60 * s, cy + 70 * s),
        ])
        pygame.draw.polygon(surface, (51, 93, 137), [
            (cx, cy - 4 * s), (cx + 32 * s, cy + 16 * s),
            (cx + 24 * s, cy + 72 * s), (cx, cy + 82 * s),
            (cx - 24 * s, cy + 72 * s), (cx - 32 * s, cy + 16 * s),
        ])
        pygame.draw.rect(surface, (16, 26, 51), body, 3, border_radius=10 * s)
        pygame.draw.circle(surface, (255, 224, 132), (cx, cy + 34 * s), 17 * s)
        pygame.draw.circle(surface, (82, 225, 255), (cx, cy + 34 * s), 9 * s)
        pygame.draw.circle(surface, (240, 255, 255), (cx - 3 * s, cy + 30 * s), 3 * s)

        head_y = cy - 62 * s - int((1.0 - assembly) * 90 * s)
        head = Rect(cx - 30 * s, head_y - 25 * s, 60 * s, 46 * s)
        pygame.draw.polygon(surface, (39, 63, 96), [
            (head.left, head.bottom - 7 * s), (head.left + 12 * s, head.top),
            (head.right - 10 * s, head.top), (head.right, head.bottom - 7 * s),
            (cx, head.bottom + 10 * s),
        ])
        pygame.draw.rect(surface, (11, 19, 39), head, 3, border_radius=6 * s)
        pygame.draw.line(surface, (255, 119, 75), (cx - 18 * s, head.centery),
                         (cx + 18 * s, head.centery), 5 * s)
        pygame.draw.line(surface, (198, 248, 255), (cx, head.top - 14 * s),
                         (cx, head.top + 4 * s), 3 * s)

        shoulder_y = cy + 2 * s + int((1.0 - assembly) * 55 * s)
        for side in (-1, 1):
            shoulder_x = cx + side * (67 * s + int((1.0 - assembly) * 55 * s))
            pygame.draw.polygon(surface, (62, 104, 148), [
                (shoulder_x, shoulder_y - 22 * s),
                (shoulder_x + side * 34 * s, shoulder_y - 4 * s),
                (shoulder_x + side * 25 * s, shoulder_y + 28 * s),
                (shoulder_x - side * 8 * s, shoulder_y + 22 * s),
            ])
            pygame.draw.line(surface, (148, 229, 255),
                             (shoulder_x + side * 8 * s, shoulder_y - 10 * s),
                             (shoulder_x + side * 27 * s, shoulder_y + 13 * s), 3 * s)

            arm_y = cy + 38 * s
            fist_x = cx + side * (105 * s + int((1.0 - assembly) * 110 * s))
            fist_y = cy + 84 * s - int(strike * 18 * s)
            elbow_x = cx + side * (70 * s + int((1.0 - assembly) * 55 * s))
            elbow_y = cy + 62 * s + int(math.sin(self.elapsed * 6 + side) * 5 * s)
            pygame.draw.line(surface, (35, 62, 96), (cx + side * 43 * s, arm_y),
                             (elbow_x, elbow_y), 17 * s)
            pygame.draw.line(surface, (48, 82, 120), (elbow_x, elbow_y),
                             (fist_x, fist_y), 15 * s)
            pygame.draw.circle(surface, (102, 180, 218), (elbow_x, elbow_y), 10 * s)
            pygame.draw.circle(surface, (80, 144, 188), (fist_x, fist_y), 18 * s)
            pygame.draw.circle(surface, (229, 250, 255), (fist_x, fist_y), 8 * s, 2 * s)

        for side in (-1, 1):
            hip_x = cx + side * 25 * s
            foot_y = cy + 148 * s
            pygame.draw.line(surface, (36, 61, 93), (hip_x, cy + 80 * s),
                             (hip_x + side * 15 * s, foot_y), 22 * s)
            pygame.draw.polygon(surface, (79, 133, 175), [
                (hip_x + side * 4 * s, foot_y - 10 * s),
                (hip_x + side * 34 * s, foot_y - 5 * s),
                (hip_x + side * 29 * s, foot_y + 12 * s),
                (hip_x - side * 3 * s, foot_y + 9 * s),
            ])

        if strike > 0:
            arc_radius = int((135 + strike * 44) * s)
            pygame.draw.arc(surface, (255, 239, 166),
                            Rect(cx - arc_radius, cy - arc_radius, arc_radius * 2, arc_radius * 2),
                            -1.2, 1.2, max(2, 7 * s))
            pygame.draw.arc(surface, (255, 93, 42),
                            Rect(cx - arc_radius - 12 * s, cy - arc_radius - 12 * s,
                                 arc_radius * 2 + 24 * s, arc_radius * 2 + 24 * s),
                            -1.0, 1.0, max(2, 4 * s))

    def draw_final_guardian(self, surface: Surface, center: tuple[int, int], scale: int = 1) -> None:
        cx, cy = center
        s = max(1, scale)
        draw_glow(surface, (cx, cy), (76, 210, 255), 115 * s, 38)
        pygame.draw.polygon(surface, (17, 24, 52), [
            (cx, cy - 104 * s), (cx + 77 * s, cy - 55 * s),
            (cx + 65 * s, cy + 88 * s), (cx, cy + 120 * s),
            (cx - 65 * s, cy + 88 * s), (cx - 77 * s, cy - 55 * s),
        ])
        pygame.draw.polygon(surface, (33, 64, 103), [
            (cx, cy - 87 * s), (cx + 42 * s, cy - 52 * s),
            (cx + 36 * s, cy + 70 * s), (cx, cy + 90 * s),
            (cx - 36 * s, cy + 70 * s), (cx - 42 * s, cy - 52 * s),
        ])
        pygame.draw.circle(surface, (6, 12, 30), (cx, cy - 60 * s), 42 * s)
        pygame.draw.line(surface, (255, 92, 65), (cx - 25 * s, cy - 61 * s),
                         (cx + 25 * s, cy - 61 * s), 7 * s)
        for side in (-1, 1):
            pygame.draw.line(surface, (62, 121, 166), (cx + side * 42 * s, cy - 20 * s),
                             (cx + side * 118 * s, cy + 52 * s), 22 * s)
            pygame.draw.circle(surface, (85, 171, 209), (cx + side * 126 * s, cy + 60 * s), 25 * s)
            pygame.draw.line(surface, (255, 115, 53), (cx + side * 108 * s, cy + 45 * s),
                             (cx + side * 142 * s, cy + 75 * s), 4 * s)
        for ray in range(8):
            angle = self.elapsed * 0.7 + ray * math.tau / 8
            pygame.draw.line(surface, (76, 210, 255), (cx, cy - 5 * s),
                             (cx + int(math.cos(angle) * 145 * s),
                              cy - 5 * s + int(math.sin(angle) * 145 * s)), 2 * s)

    def draw_finale_fight(self, surface: Surface) -> None:
        if self.boss is None:
            return
        spec = self.boss.spec
        for y in range(HEIGHT):
            ratio = y / HEIGHT
            color = (int(5 + ratio * 22), int(7 + ratio * 7), int(24 + ratio * 25))
            pygame.draw.line(surface, color, (0, y), (WIDTH, y))
        center = (500, 324)
        for ring in range(5):
            radius = 100 + ring * 46 + int(math.sin(self.elapsed * 3 + ring) * 5)
            pygame.draw.arc(surface, (255, 82 + ring * 18, 32), 
                            Rect(center[0] - radius, center[1] - radius * 0.52,
                                 radius * 2, int(radius * 1.04)), math.pi, math.tau, 5)
        for flame in range(24):
            angle = flame * math.tau / 24 + self.elapsed * 0.4
            inner = 135 + (flame % 3) * 12
            outer = inner + 28 + int(abs(math.sin(self.elapsed * 5 + flame)) * 22)
            a = (center[0] + int(math.cos(angle) * inner), center[1] + int(math.sin(angle) * inner * 0.52))
            b = (center[0] + int(math.cos(angle) * outer), center[1] + int(math.sin(angle) * outer * 0.52))
            pygame.draw.line(surface, (255, 179, 62), a, b, 4)
        for particle in self.particles:
            particle.draw(surface, 0)

        if self.finale_execution_active or self.finale_execution_ready:
            progress = 1.0 - self.finale_execution_timer / max(0.01, self.finale_execution_total)
            horizon = 185
            for row in range(8):
                y = horizon + int((row / 7) ** 1.8 * 330)
                pygame.draw.line(surface, (48, 70, 119), (0, y), (WIDTH, y), 1)
            for x in range(-700, 1701, 90):
                pygame.draw.line(surface, (32, 61, 102), (WIDTH // 2, horizon), (x, HEIGHT), 1)
            sun = (790, 92)
            draw_glow(surface, sun, (255, 194, 91), 115, 70)
            pygame.draw.circle(surface, (255, 229, 142), sun, 48 + int(progress * 15))
            pygame.draw.circle(surface, (255, 120, 48), sun, 64 + int(progress * 30), 4)
            boss_y = 260 - int(progress * 128)
            if self.finale_execution_active:
                boss_y = 260 - int(smoothstep(progress) * 270)
                for trail in range(8):
                    trail_x = 735 + int(math.sin(self.elapsed * 4 + trail) * (20 + trail * 4))
                    pygame.draw.line(surface, (255, 115 + trail * 10, 55),
                                     (trail_x, boss_y + 105), (trail_x - 35, boss_y + 220), 4)
            self.draw_final_guardian(surface, (735, boss_y), 1)
            punch = self.finale_execution_flash if self.finale_execution_active else 0.0
            self.draw_final_mecha(surface, (335, 302), 1, 1.0, punch)
            if self.finale_execution_active:
                arc = int(120 + punch * 90)
                pygame.draw.arc(surface, (255, 241, 180),
                                Rect(390 - arc, 265 - arc, arc * 2, arc * 2), -1.2, 1.2, 8)
                draw_text(surface, "GOLPE DO VOTO", (WIDTH // 2, 70), 28,
                          (255, 237, 180), center=True, bold=True)
                draw_text(surface, "O GUARDIÃO VAI AO SOL", (WIDTH // 2, 108), 16,
                          (255, 121, 62), center=True, bold=True)
            else:
                draw_text(surface, "3D: NÚCLEO EXPOSTO", (WIDTH // 2, 70), 25,
                          (255, 237, 180), center=True, bold=True)
                draw_text(surface, "PRESSIONE ESPAÇO, J OU X PARA FINALIZAR",
                          (WIDTH // 2, 108), 15, (153, 232, 255), center=True, bold=True)
            self.draw_battle_hud(surface)
            return

        if self.finale_entry_timer > 0:
            progress = 1.0 - self.finale_entry_timer / max(0.01, self.finale_entry_total)
            flight = smoothstep(clamp(progress / 0.34, 0.0, 1.0))
            assembly = smoothstep(clamp((progress - 0.18) / 0.78, 0.0, 1.0))
            self.player.draw(surface, 0)
            self.draw_final_guardian(surface, (735, 265 - int(flight * 190)), 1)
            for thruster in range(5):
                tx = 690 + thruster * 22
                pygame.draw.line(surface, (255, 120, 48),
                                 (tx, 310 - int(flight * 160)),
                                 (tx, 365 - int(flight * 180)), 4)
            self.draw_final_mecha(surface, (405, 310), 1, assembly, 0)
            if assembly < 0.98:
                for beam in range(5):
                    angle = self.elapsed * 2.0 + beam * math.tau / 5
                    pygame.draw.line(surface, (102, 218, 255),
                                     (405 + int(math.cos(angle) * 165),
                                      310 + int(math.sin(angle) * 115)),
                                     (405 + int(math.cos(angle) * 78),
                                      310 + int(math.sin(angle) * 52)), 3)
            draw_text(surface, "A ARMADURA RESPONDE AO VOTO", (WIDTH // 2, 88), 24,
                      (255, 232, 170), center=True, bold=True)
            draw_text(surface, "LIRA ENTRA NO NÚCLEO", (WIDTH // 2, 120), 15,
                      spec.primary, center=True, bold=True)
        else:
            strike = self.finale_strike_flash
            self.draw_final_guardian(surface, (735, 265), 1)
            mecha_center = (int(self.player.position.x + 85), 300)
            self.draw_final_mecha(surface, mecha_center, 1, 1.0, strike)
            if self.player.hurt_flash > 0:
                hurt_radius = 112 + int(math.sin(self.elapsed * 30) * 8)
                pygame.draw.circle(surface, (255, 112, 132), mecha_center, hurt_radius, 5)
                draw_text(surface, "IMPACTO", (mecha_center[0], 178), 16,
                          (255, 155, 177), center=True, bold=True)
            for hazard in self.hazards:
                hazard.draw(surface, 0)
            draw_text(surface, "ASCENSÃO FINAL", (WIDTH // 2, 72), 27,
                      (255, 235, 182), center=True, bold=True)
            draw_text(surface, "ATAQUE J/X/ESPAÇO  •  MOVA A/D PARA ESCAPAR", (WIDTH // 2, 105), 17,
                      (153, 232, 255), center=True, bold=True)
            draw_text(surface, f"{self.finale_hits}/{self.finale_target} IMPACTOS",
                      (WIDTH // 2, 132), 14, (231, 238, 255), center=True, bold=True)
            pygame.draw.rect(surface, (16, 20, 46), (260, 450, 440, 16), border_radius=8)
            pygame.draw.rect(surface, (255, 105, 42), (264, 454,
                             int(432 * self.finale_hits / max(1, self.finale_target)), 8),
                             border_radius=4)
            pygame.draw.rect(surface, (22, 28, 58), (335, 475, 330, 10), border_radius=5)
            pygame.draw.rect(surface, (103, 220, 255), (338, 478,
                             int(324 * self.finale_timer / 20.0), 4), border_radius=3)
        self.draw_battle_hud(surface)

    def draw_fight(self, surface: Surface) -> None:
        if self.dimension_mode == "finale":
            self.draw_finale_fight(surface)
            return
        if self.dimension_mode == "3d":
            self.draw_3d_fight(surface)
            return
        if self.dimension_mode == "shooter":
            self.draw_shooter_fight(surface)
            return
        if self.boss is not None and self.boss.phase == 3:
            self.draw_apotheosis_fight(surface)
            return
        self.draw_background(surface)
        if self.boss is None:
            return
        for platform in self.platforms:
            rect = platform.move(-int(self.camera_x), 0)
            color = self.boss.spec.secondary if platform.top >= GROUND_Y else self.boss.spec.primary
            pygame.draw.rect(surface, color, rect)
            pygame.draw.line(surface, self.boss.spec.primary, (rect.left, rect.top), (rect.right, rect.top), 3)
            if self.boss.phase >= 2 and platform.top < GROUND_Y:
                for crystal_x in range(rect.left + 16, rect.right - 8, 40):
                    pygame.draw.polygon(surface, self.boss.spec.primary, [
                        (crystal_x, rect.bottom), (crystal_x + 8, rect.bottom + 17), (crystal_x + 16, rect.bottom),
                    ])
        for potion in self.potions:
            potion.draw(surface, self.camera_x, self.boss.spec.primary)
        for hazard in self.hazards:
            hazard.draw(surface, self.camera_x)
        for particle in self.particles:
            particle.draw(surface, self.camera_x)
        self.boss.draw(surface, self.camera_x)
        self.player.draw(surface, self.camera_x)

        self.draw_battle_hud(surface)
        controls = "A/D mover   ESPAÇO pulo duplo   J atacar   ESC voltar ao Panteão"
        draw_text(surface, controls, (WIDTH // 2, HEIGHT - 22), 12, (173, 186, 215), center=True)
        audio = "SILÊNCIO" if self.audio.muted else f"ÁUDIO {int(self.audio.master_volume * 100)}%"
        draw_text(surface, audio, (WIDTH - 24, HEIGHT - 44), 11, (184, 200, 226), bold=True)
        if self.notice_timer > 0:
            draw_text(surface, self.notice, (WIDTH // 2, 78), 15, (255, 220, 145), center=True, bold=True)

        if self.banner_timer > 0:
            overlay = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((*self.boss.spec.primary, int(clamp(self.banner_timer / 3, 0, 1) * 80)))
            surface.blit(overlay, (0, 0))
            draw_text(surface, self.banner_text, (WIDTH // 2, 150), 32, (255, 235, 186), center=True, bold=True)
            draw_text(surface, "A arena muda. A música acelera.", (WIDTH // 2, 190), 17, self.boss.spec.primary, center=True)
        if self.qte_active:
            self.draw_qte(surface)

    def draw(self) -> None:
        scene = Surface((WIDTH, HEIGHT))
        if self.mode == "menu":
            self.draw_menu(scene)
        else:
            self.draw_fight(scene)
            if self.domain_active:
                self.draw_domain_expansion(scene)
            if self.victory_active:
                self.draw_victory(scene)
        shake = int(self.screen_shake * 20)
        offset = (random.randint(-shake, shake), random.randint(-shake, shake)) if shake else (0, 0)
        self.screen.fill((3, 4, 14))
        self.screen.blit(scene, offset)
        if self.mode == "fight" and self.intro_timer > 0:
            self.draw_phase_intro(self.screen)
        if self.flash_timer > 0:
            overlay = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            alpha = int(clamp(self.flash_timer / 0.7, 0, 1) * 92)
            overlay.fill((*self.flash_color, alpha))
            self.screen.blit(overlay, (0, 0))
        pygame.display.flip()

    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000, 0.033)
            self.handle_input()
            self.update(dt)
            self.draw()
        self.audio.shutdown()
        pygame.quit()