"""Ecos do Abismo - um pequeno metroidvania 2D feito em Python + Pygame.

Controles:
    A/D ou setas esquerda/direita: mover
    Espaço/W/seta para cima: pular (permite pulo duplo)
    J ou X: atacar
    M: silenciar ou reativar o áudio
    - / +: diminuir ou aumentar o volume
    R: reiniciar depois de vencer ou perder
    ESC: sair
"""

from __future__ import annotations

import math
import random
import sys
from array import array
from dataclasses import dataclass

import pygame
from pygame import Rect, Surface
from pygame.math import Vector2


WIDTH, HEIGHT = 960, 540
FPS = 60
GROUND_Y = 468
WORLD_WIDTH = 1900
PLAYER_SPAWN = Vector2(150, GROUND_Y - 72)
ENEMY_SPAWN = Vector2(730, GROUND_Y - 108)

Color = tuple[int, int, int]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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
    if center:
        rect.center = position
    else:
        rect.topleft = position
    surface.blit(image, rect)


class AudioSystem:
    """Sons procedurais para manter o protótipo livre de assets externos."""

    SAMPLE_RATE = 44100

    def __init__(self) -> None:
        self.enabled = False
        self.master_volume = 0.65
        self.muted = False
        self.current_phase_two = False
        self.ambient_channel: pygame.mixer.Channel | None = None
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.ambience: dict[bool, pygame.mixer.Sound] = {}

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(
                    frequency=self.SAMPLE_RATE,
                    size=-16,
                    channels=1,
                    buffer=512,
                )
            self.sounds = {
                "player_attack": self._make_tone(
                    0.16,
                    260,
                    1150,
                    0.34,
                    harmonics=((2.0, 0.24), (0.5, 0.12)),
                    noise=0.05,
                ),
                "impact": self._make_tone(
                    0.22,
                    190,
                    58,
                    0.48,
                    harmonics=((1.5, 0.34), (3.0, 0.16)),
                    noise=0.28,
                ),
                "boss_attack": self._make_tone(
                    0.24,
                    105,
                    42,
                    0.44,
                    harmonics=((2.0, 0.3), (0.5, 0.18)),
                    noise=0.18,
                ),
                "player_hurt": self._make_tone(
                    0.3,
                    210,
                    92,
                    0.38,
                    harmonics=((1.5, 0.26), (2.5, 0.1)),
                    noise=0.16,
                ),
                "boss_scream": self._make_scream(),
            }
            self.ambience = {
                False: self._make_ambience(False),
                True: self._make_ambience(True),
            }
            self.enabled = True
        except pygame.error:
            # O jogo continua jogável em ambientes sem dispositivo de áudio.
            self.enabled = False

    @property
    def audible_volume(self) -> float:
        return 0.0 if self.muted else self.master_volume

    def _apply_volume(self) -> None:
        if not self.enabled:
            return
        for sound in self.sounds.values():
            sound.set_volume(self.audible_volume)
        for phase_two, phase_sound in self.ambience.items():
            base_volume = 0.5 if phase_two else 0.38
            phase_sound.set_volume(self.audible_volume * base_volume)
        if self.ambient_channel is not None:
            base_volume = 0.5 if self.current_phase_two else 0.38
            self.ambient_channel.set_volume(self.audible_volume * base_volume)

    def set_volume(self, volume: float) -> None:
        self.master_volume = clamp(volume, 0.0, 1.0)
        self._apply_volume()

    def adjust_volume(self, delta: float) -> None:
        self.set_volume(self.master_volume + delta)

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        self._apply_volume()
        return self.muted

    @staticmethod
    def _sample_bytes(samples: array) -> bytes:
        if sys.byteorder != "little":
            samples.byteswap()
        return samples.tobytes()

    def _make_tone(
        self,
        duration: float,
        start_frequency: float,
        end_frequency: float,
        volume: float,
        *,
        harmonics: tuple[tuple[float, float], ...] = (),
        noise: float = 0.0,
    ) -> pygame.mixer.Sound:
        count = int(self.SAMPLE_RATE * duration)
        samples = array("h")
        phase = 0.0
        noise_source = random.Random(int(start_frequency + end_frequency))
        release = min(0.08, duration * 0.35)

        for index in range(count):
            position = index / max(1, count - 1)
            frequency = start_frequency + (end_frequency - start_frequency) * position
            phase += math.tau * frequency / self.SAMPLE_RATE
            value = math.sin(phase)
            for multiple, amplitude in harmonics:
                value += math.sin(phase * multiple) * amplitude
            if noise:
                value += noise_source.uniform(-1.0, 1.0) * noise

            envelope = min(1.0, position / 0.04)
            envelope *= min(1.0, (1.0 - position) / release)
            sample = int(clamp(value * volume * envelope, -1.0, 1.0) * 32767)
            samples.append(sample)

        return pygame.mixer.Sound(buffer=self._sample_bytes(samples))

    def _make_scream(self) -> pygame.mixer.Sound:
        duration = 0.9
        count = int(self.SAMPLE_RATE * duration)
        samples = array("h")
        phase = 0.0

        for index in range(count):
            position = index / max(1, count - 1)
            frequency = 138 - 58 * position + math.sin(position * math.tau * 3) * 11
            phase += math.tau * frequency / self.SAMPLE_RATE
            growl = math.sin(phase) * 0.62
            growl += math.sin(phase * 1.97) * 0.25
            growl += math.sin(phase * 3.03) * 0.14
            growl += math.sin(phase * 0.48) * 0.18
            envelope = min(1.0, position / 0.08, (1.0 - position) / 0.22)
            sample = int(clamp(growl * 0.7 * envelope, -1.0, 1.0) * 32767)
            samples.append(sample)

        return pygame.mixer.Sound(buffer=self._sample_bytes(samples))

    def _make_ambience(self, phase_two: bool) -> pygame.mixer.Sound:
        duration = 10.0
        count = int(self.SAMPLE_RATE * duration)
        samples = array("h")
        if phase_two:
            frequencies = (43.0, 64.5, 86.0, 129.0)
            volume = 0.3
        else:
            frequencies = (55.0, 82.5, 110.0, 165.0)
            volume = 0.22

        for index in range(count):
            time = index / self.SAMPLE_RATE
            pulse = 0.82 + math.sin(time * (1.25 if phase_two else 0.7)) * 0.18
            value = math.sin(math.tau * frequencies[0] * time) * 0.52
            value += math.sin(math.tau * frequencies[1] * time) * 0.28
            value += math.sin(math.tau * frequencies[2] * time) * 0.13
            value += math.sin(math.tau * frequencies[3] * time) * 0.07
            if phase_two:
                value += math.sin(math.tau * 31 * time) * 0.14
                value *= 1.0 + math.sin(time * math.tau * 0.25) * 0.15
            else:
                value += math.sin(math.tau * 27 * time) * 0.06

            # Suaviza a passagem no ponto de loop sem silenciar a ambiência.
            loop_fade = min(1.0, index / (self.SAMPLE_RATE * 0.12))
            loop_fade *= min(1.0, (count - index) / (self.SAMPLE_RATE * 0.12))
            samples.append(int(clamp(value * volume * pulse * loop_fade, -1.0, 1.0) * 32767))

        return pygame.mixer.Sound(buffer=self._sample_bytes(samples))

    def play(self, name: str) -> None:
        if not self.enabled or self.muted:
            return
        sound = self.sounds.get(name)
        if sound is not None:
            sound.set_volume(self.audible_volume)
            sound.play()

    def start_ambience(self, phase_two: bool) -> None:
        if not self.enabled:
            return
        if self.ambient_channel is not None:
            self.ambient_channel.fadeout(500)
        self.current_phase_two = phase_two
        sound = self.ambience[phase_two]
        sound.set_volume(self.audible_volume * (0.5 if phase_two else 0.38))
        self.ambient_channel = sound.play(loops=-1, fade_ms=650)
        self.ambient_channel.set_volume(self.audible_volume * (0.5 if phase_two else 0.38))

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
    gravity: float = 0.0

    def update(self, dt: float) -> bool:
        self.position += self.velocity * dt
        self.velocity.y += self.gravity * dt
        self.lifetime -= dt
        self.radius *= 0.985
        return self.lifetime > 0 and self.radius > 0.5

    def draw(self, surface: Surface, camera_x: float) -> None:
        alpha = int(clamp(self.lifetime / 0.8, 0.0, 1.0) * 255)
        layer = Surface((16, 16), pygame.SRCALPHA)
        pygame.draw.circle(
            layer,
            (*self.color, alpha),
            (8, 8),
            max(1, int(self.radius)),
        )
        surface.blit(layer, (int(self.position.x - camera_x - 8), int(self.position.y - 8)))


class Player:
    def __init__(self) -> None:
        self.position = PLAYER_SPAWN.copy()
        self.velocity = Vector2()
        self.width = 42
        self.height = 72
        self.facing = 1
        self.on_ground = False
        self.jumps_left = 2
        self.attack_timer = 0.0
        self.attack_cooldown = 0.0
        self.invulnerability = 0.0
        self.health = 100
        self.walk_time = 0.0
        self.hurt_flash = 0.0

    @property
    def rect(self) -> Rect:
        return Rect(
            int(self.position.x),
            int(self.position.y),
            self.width,
            self.height,
        )

    @property
    def attack_rect(self) -> Rect:
        offset = self.width if self.facing > 0 else -68
        return Rect(
            int(self.position.x + offset),
            int(self.position.y + 17),
            68,
            28,
        )

    def reset(self) -> None:
        self.__init__()

    def jump(self, particles: list[Particle]) -> None:
        if self.jumps_left <= 0:
            return
        self.velocity.y = -610 if self.jumps_left == 2 else -535
        self.jumps_left -= 1
        self.on_ground = False
        for _ in range(8):
            particles.append(
                Particle(
                    Vector2(self.position.x + self.width / 2, self.position.y + self.height),
                    Vector2(random.uniform(-70, 70), random.uniform(-90, -25)),
                    (160, 190, 214),
                    random.uniform(2, 4),
                    0.45,
                    160,
                )
            )

    def attack(self, particles: list[Particle]) -> bool:
        if self.attack_cooldown > 0 or self.attack_timer > 0:
            return False
        self.attack_timer = 0.24
        self.attack_cooldown = 0.34
        for _ in range(5):
            edge = self.attack_rect.right if self.facing > 0 else self.attack_rect.left
            particles.append(
                Particle(
                    Vector2(edge, self.attack_rect.centery + random.uniform(-11, 11)),
                    Vector2(random.uniform(40, 135) * self.facing, random.uniform(-40, 40)),
                    (208, 238, 255),
                    random.uniform(2, 4),
                    0.28,
                )
            )
        return True

    def take_damage(self, amount: int, particles: list[Particle]) -> bool:
        if self.invulnerability > 0:
            return False
        self.health = max(0, self.health - amount)
        self.invulnerability = 0.9
        self.hurt_flash = 0.18
        self.velocity.x = -260 if self.facing > 0 else 260
        for _ in range(15):
            particles.append(
                Particle(
                    Vector2(self.rect.center),
                    Vector2(random.uniform(-180, 180), random.uniform(-170, 40)),
                    (255, 120, 133),
                    random.uniform(2, 5),
                    0.55,
                    320,
                )
            )
        return True

    def update(
        self,
        dt: float,
        keys: pygame.key.ScancodeWrapper,
        platforms: list[Rect],
        particles: list[Particle],
    ) -> None:
        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
        self.invulnerability = max(0.0, self.invulnerability - dt)
        self.hurt_flash = max(0.0, self.hurt_flash - dt)

        direction = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            direction -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            direction += 1
        if direction:
            self.facing = direction
            self.velocity.x = direction * 275
            self.walk_time += dt * 11
        else:
            self.velocity.x *= max(0, 1 - 11 * dt)
            self.walk_time += dt * 3

        previous_bottom = self.position.y + self.height
        self.velocity.y += 1450 * dt
        self.position.x += self.velocity.x * dt
        self.position.x = clamp(self.position.x, 30, WORLD_WIDTH - self.width - 30)
        self.position.y += self.velocity.y * dt

        was_grounded = self.on_ground
        self.on_ground = False
        landing = land_on_platform(
            self.position,
            previous_bottom,
            self.velocity.y,
            self.width,
            self.height,
            platforms,
        )
        if landing is not None:
            self.position.y = landing.top - self.height
            self.velocity.y = 0
            self.on_ground = True
            self.jumps_left = 2

        if self.on_ground and not was_grounded:
            for _ in range(5):
                particles.append(
                    Particle(
                        Vector2(self.position.x + self.width / 2, self.rect.bottom),
                        Vector2(random.uniform(-65, 65), random.uniform(-50, -10)),
                        (141, 167, 192),
                        random.uniform(2, 3),
                        0.3,
                        90,
                    )
                )

    def draw(self, surface: Surface, camera_x: float) -> None:
        if self.invulnerability > 0 and int(self.invulnerability * 16) % 2 == 0:
            return

        x = int(self.position.x - camera_x)
        y = int(self.position.y)
        bob = math.sin(self.walk_time) * 2 if abs(self.velocity.x) > 25 else 0
        cloak = (238, 240, 255) if self.hurt_flash <= 0 else (255, 139, 156)

        # Sombra e capa
        pygame.draw.ellipse(surface, (8, 11, 28), (x - 5, y + 61, 52, 14))
        pygame.draw.polygon(
            surface,
            (36, 42, 74),
            [(x + 21, y + 27 + bob), (x + 3, y + 69), (x + 39, y + 69)],
        )
        pygame.draw.polygon(
            surface,
            (57, 63, 102),
            [(x + 21, y + 31 + bob), (x + 12, y + 68), (x + 31, y + 68)],
        )
        # Cabeça com chifres
        pygame.draw.polygon(
            surface,
            cloak,
            [(x + 12, y + 19 + bob), (x + 7, y - 3 + bob), (x + 18, y + 8 + bob),
             (x + 24, y - 8 + bob), (x + 31, y + 8 + bob), (x + 39, y - 3 + bob),
             (x + 34, y + 23 + bob)],
        )
        pygame.draw.ellipse(surface, (17, 21, 44), (x + 15, y + 12 + bob, 19, 17))
        pygame.draw.circle(surface, (172, 218, 255), (x + 21, y + 20 + int(bob)), 2)
        pygame.draw.circle(surface, (172, 218, 255), (x + 29, y + 20 + int(bob)), 2)

        if self.attack_timer > 0:
            progress = 1 - self.attack_timer / 0.24
            radius = int(38 + progress * 17)
            center = (x + (44 if self.facing > 0 else -2), y + 35)
            arc_rect = Rect(center[0] - radius, center[1] - radius, radius * 2, radius * 2)
            start = -1.18 if self.facing > 0 else 2.0
            end = 1.18 if self.facing > 0 else 4.42
            pygame.draw.arc(surface, (218, 245, 255), arc_rect, start, end, 5)
            pygame.draw.arc(surface, (112, 177, 229), arc_rect.inflate(-10, -10), start, end, 2)


class AbyssKnight:
    def __init__(self) -> None:
        self.position = ENEMY_SPAWN.copy()
        self.width = 62
        self.height = 108
        self.velocity = Vector2()
        self.health = 160
        self.max_health = 160
        self.facing = -1
        self.attack_timer = 0.0
        self.attack_cooldown = 0.5
        self.invulnerability = 0.0
        self.phase_two = False
        self.scream_timer = 0.0
        self.hurt_flash = 0.0
        self.anim_time = 0.0
        self.has_been_hit = False
        self.flight_time = 0.0

    @property
    def rect(self) -> Rect:
        return Rect(int(self.position.x), int(self.position.y), self.width, self.height)

    @property
    def attack_rect(self) -> Rect:
        offset = self.width if self.facing > 0 else -(120 if self.phase_two else 70)
        reach = 120 if self.phase_two else 70
        attack_height = 64 if self.phase_two else 46
        return Rect(
            int(self.position.x + offset),
            int(self.position.y + self.height * 0.3),
            reach,
            attack_height,
        )

    def reset(self) -> None:
        self.__init__()

    def take_damage(self, amount: int, particles: list[Particle]) -> bool:
        if self.invulnerability > 0 or self.scream_timer > 0:
            return False
        self.health = max(0, self.health - amount)
        self.has_been_hit = True
        self.invulnerability = 0.18
        self.hurt_flash = 0.16
        self.velocity.x = -110 * self.facing
        for _ in range(9):
            particles.append(
                Particle(
                    Vector2(self.rect.center),
                    Vector2(random.uniform(-140, 140), random.uniform(-160, 80)),
                    (255, 215, 135),
                    random.uniform(2, 5),
                    0.5,
                    320,
                )
            )
        return True

    def start_phase_two(self, particles: list[Particle]) -> None:
        self.phase_two = True
        self.scream_timer = 2.6
        feet_y = self.position.y + self.height
        self.width = 96
        self.height = 156
        self.position.y = feet_y - self.height
        self.velocity = Vector2(0, -90)
        for _ in range(42):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(100, 310)
            particles.append(
                Particle(
                    Vector2(self.rect.center),
                    Vector2(math.cos(angle) * speed, math.sin(angle) * speed),
                    (246, 76, 101),
                    random.uniform(3, 7),
                    1.1,
                    100,
                )
            )

    def update(
        self,
        dt: float,
        player: Player,
        platforms: list[Rect],
        particles: list[Particle],
    ) -> tuple[bool, bool]:
        phase_started = False
        attack_started = False
        self.anim_time += dt
        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
        self.invulnerability = max(0.0, self.invulnerability - dt)
        self.hurt_flash = max(0.0, self.hurt_flash - dt)

        if self.health <= 50 and not self.phase_two:
            self.start_phase_two(particles)
            phase_started = True

        self.scream_timer = max(0.0, self.scream_timer - dt)
        if self.scream_timer > 0:
            self.velocity.x *= max(0, 1 - 12 * dt)
            return phase_started, attack_started

        speed = 118 if not self.phase_two else 320
        distance = player.position.x - self.position.x
        if self.phase_two:
            self.flight_time += dt
            desired_y = clamp(
                player.position.y - 125 + math.sin(self.flight_time * 2.5) * 48,
                72,
                GROUND_Y - self.height - 18,
            )
            self.velocity.y = (desired_y - self.position.y) * 3.6
            attack_range = 190
        else:
            attack_range = 80

        distance_2d = math.hypot(distance, player.position.y - self.position.y)
        if distance_2d > attack_range:
            self.facing = 1 if distance > 0 else -1
            self.velocity.x = self.facing * speed
        else:
            self.velocity.x *= max(0, 1 - 9 * dt)
            if self.attack_cooldown <= 0:
                self.attack_timer = 0.36 if not self.phase_two else 0.3
                self.attack_cooldown = 1.35 if not self.phase_two else 0.78
                attack_started = True

        previous_bottom = self.position.y + self.height
        if not self.phase_two:
            self.velocity.y += 1450 * dt
        self.position.x += self.velocity.x * dt
        self.position.x = clamp(self.position.x, 440, WORLD_WIDTH - self.width - 30)
        self.position.y += self.velocity.y * dt

        if not self.phase_two:
            landing = land_on_platform(
                self.position,
                previous_bottom,
                self.velocity.y,
                self.width,
                self.height,
                platforms,
            )
            if landing is not None:
                self.position.y = landing.top - self.height
                self.velocity.y = 0
        return phase_started, attack_started

    def draw(self, surface: Surface, camera_x: float) -> None:
        x = int(self.position.x - camera_x)
        y = int(self.position.y)
        pulse = math.sin(self.anim_time * (8 if self.phase_two else 4))
        cloak = (255, 92, 111) if self.hurt_flash > 0 else ((90, 18, 47) if self.phase_two else (33, 28, 67))
        glow = (255, 51, 89) if self.phase_two else (102, 91, 196)
        scale = 1.38 if self.phase_two else 1.0
        center_x = x + self.width // 2
        feet_y = y + self.height

        pygame.draw.ellipse(
            surface,
            (8, 8, 20),
            (center_x - int(self.width * 0.72), feet_y - 9, int(self.width * 1.45), 22),
        )
        if self.phase_two:
            # Asas e anéis de energia tornam a transformação reconhecível à distância.
            wing_y = y + 58 + int(math.sin(self.anim_time * 4) * 8)
            wing_color = (117, 17, 65)
            pygame.draw.polygon(
                surface,
                wing_color,
                [(center_x - 25, wing_y), (center_x - 132, wing_y - 58),
                 (center_x - 88, wing_y + 18), (center_x - 144, wing_y + 48),
                 (center_x - 22, wing_y + 38)],
            )
            pygame.draw.polygon(
                surface,
                wing_color,
                [(center_x + 25, wing_y), (center_x + 132, wing_y - 58),
                 (center_x + 88, wing_y + 18), (center_x + 144, wing_y + 48),
                 (center_x + 22, wing_y + 38)],
            )
            for radius in (74, 95, 116):
                pygame.draw.arc(
                    surface,
                    (255, 59, 111),
                    Rect(center_x - radius, y + 38 - radius // 3, radius * 2, radius * 2),
                    math.pi * 0.18,
                    math.pi * 0.82,
                    2,
                )
            glow_layer = Surface((260, 260), pygame.SRCALPHA)
            pygame.draw.circle(glow_layer, (*glow, 44), (130, 130), int(82 + pulse * 6))
            surface.blit(glow_layer, (center_x - 130, y - 48))

        # Desenha o cavaleiro em tamanho base e amplia somente a forma de fúria.
        # Isso mantém a arte proporcional e a hitbox alinhada aos pés.
        art = Surface((110, 150), pygame.SRCALPHA)
        ax, ay = 28, 28
        pygame.draw.polygon(
            art,
            cloak,
            [(ax + 31, ay + 29), (ax - 1, ay + 104), (ax + 64, ay + 104)],
        )
        pygame.draw.polygon(
            art,
            (122, 35, 67) if self.phase_two else (54, 49, 94),
            [(ax + 31, ay + 34), (ax + 15, ay + 98), (ax + 48, ay + 98)],
        )
        pygame.draw.polygon(
            art,
            (220, 225, 246),
            [(ax + 13, ay + 30), (ax + 3, ay - 12), (ax + 24, ay + 12),
             (ax + 35, ay - 22), (ax + 43, ay + 12), (ax + 61, ay - 12),
             (ax + 51, ay + 38)],
        )
        pygame.draw.ellipse(art, (18, 14, 39), (ax + 16, ay + 18, 31, 24))
        eye_color = (255, 66, 101) if self.phase_two else (252, 214, 128)
        pygame.draw.circle(art, eye_color, (ax + 25, ay + 29), 3)
        pygame.draw.circle(art, eye_color, (ax + 39, ay + 29), 3)
        if self.phase_two:
            pygame.draw.polygon(
                art,
                (255, 205, 92),
                [(ax + 16, ay + 3), (ax + 23, ay - 16), (ax + 31, ay + 2),
                 (ax + 39, ay - 16), (ax + 47, ay + 3)],
            )

        if scale != 1:
            art = pygame.transform.smoothscale(art, (int(art.get_width() * scale), int(art.get_height() * scale)))
        art_left = int(center_x - (ax + 31) * scale)
        art_top = int(feet_y - (ay + 104) * scale)
        surface.blit(art, (art_left, art_top))

        if self.attack_timer > 0:
            radius = 42 if not self.phase_two else 82
            center = (center_x + (self.width // 2 + 18 if self.facing > 0 else -(self.width // 2 + 18)),
                      y + int(self.height * 0.45))
            rect = Rect(center[0] - radius, center[1] - radius, radius * 2, radius * 2)
            start = -1.1 if self.facing > 0 else 2.04
            end = 1.1 if self.facing > 0 else 4.24
            pygame.draw.arc(surface, glow, rect, start, end, 10 if self.phase_two else 5)

        if self.scream_timer > 0:
            shake = random.randint(-3, 3)
            draw_text(
                surface,
                "GRRRRAAAAH!",
                (center_x + shake, y - 54 + shake),
                28 if self.phase_two else 24,
                (255, 105, 121),
                center=True,
                bold=True,
            )


class Game:
    def __init__(self) -> None:
        pygame.mixer.pre_init(44100, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("Ecos do Abismo")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.running = True
        self.audio = AudioSystem()
        self.reset()

    def reset(self) -> None:
        self.player = Player()
        self.enemy = AbyssKnight()
        self.particles: list[Particle] = []
        self.camera_x = 0.0
        self.elapsed = 0.0
        self.screen_shake = 0.0
        self.message_timer = 0.0
        self.audio_notice_timer = 0.0
        self.audio_notice = ""
        self.phase_banner_timer = 0.0
        self.rift_flash_timer = 0.0
        self.game_over: str | None = None
        self.jump_was_down = False
        self.attack_was_down = False
        self.audio.start_ambience(False)
        self.platforms = [
            Rect(0, GROUND_Y, WORLD_WIDTH, HEIGHT - GROUND_Y),
            Rect(310, 382, 180, 18),
            Rect(820, 335, 185, 18),
            Rect(1170, 400, 220, 18),
            Rect(1490, 320, 180, 18),
            Rect(1630, 415, 170, 18),
        ]

    @property
    def phase_two(self) -> bool:
        return self.enemy.phase_two

    def enter_phase_two_map(self) -> None:
        """Troca a arena por uma geografia quebrada no instante da transformação."""
        self.platforms = [
            Rect(0, 515, WORLD_WIDTH, HEIGHT - 515),
            Rect(70, 408, 235, 16),
            Rect(400, 350, 180, 16),
            Rect(700, 435, 215, 16),
            Rect(1030, 310, 230, 16),
            Rect(1370, 390, 190, 16),
            Rect(1660, 292, 190, 16),
        ]
        self.phase_banner_timer = 3.2
        self.rift_flash_timer = 0.8
        self.screen_shake = 0.8
        for _ in range(56):
            self.particles.append(
                Particle(
                    Vector2(
                        random.uniform(self.camera_x - 80, self.camera_x + WIDTH + 80),
                        random.uniform(80, HEIGHT),
                    ),
                    Vector2(random.uniform(-80, 80), random.uniform(-240, -60)),
                    random.choice([(255, 57, 105), (255, 156, 78), (159, 31, 91)]),
                    random.uniform(2, 7),
                    random.uniform(0.8, 1.8),
                    130,
                )
            )

    def spawn_sparks(self, position: Vector2, color: Color, count: int = 4) -> None:
        for _ in range(count):
            self.particles.append(
                Particle(
                    position.copy(),
                    Vector2(random.uniform(-90, 90), random.uniform(-170, -40)),
                    color,
                    random.uniform(1, 3),
                    0.45,
                    320,
                )
            )

    def handle_input(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                if event.key == pygame.K_r and self.game_over:
                    self.reset()
                if event.key == pygame.K_m:
                    muted = self.audio.toggle_mute()
                    self.audio_notice_timer = 1.8
                    self.audio_notice = "ÁUDIO SILENCIADO" if muted else "ÁUDIO REATIVADO"
                if event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    self.audio.adjust_volume(-0.1)
                    self.audio_notice_timer = 1.8
                    self.audio_notice = f"VOLUME {int(self.audio.master_volume * 100)}%"
                if event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                    self.audio.adjust_volume(0.1)
                    self.audio_notice_timer = 1.8
                    self.audio_notice = f"VOLUME {int(self.audio.master_volume * 100)}%"

        keys = pygame.key.get_pressed()
        jump_down = bool(keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP])
        attack_down = bool(keys[pygame.K_j] or keys[pygame.K_x])
        if not self.game_over:
            if jump_down and not self.jump_was_down:
                self.player.jump(self.particles)
            if attack_down and not self.attack_was_down:
                if self.player.attack(self.particles):
                    self.audio.play("player_attack")
        self.jump_was_down = jump_down
        self.attack_was_down = attack_down

    def update(self, dt: float) -> None:
        self.elapsed += dt
        self.message_timer = max(0, self.message_timer - dt)
        self.audio_notice_timer = max(0, self.audio_notice_timer - dt)
        self.phase_banner_timer = max(0, self.phase_banner_timer - dt)
        self.rift_flash_timer = max(0, self.rift_flash_timer - dt)
        self.screen_shake = max(0, self.screen_shake - dt * 2.2)

        alive_particles: list[Particle] = []
        for particle in self.particles:
            if particle.update(dt):
                alive_particles.append(particle)
        self.particles = alive_particles

        if self.game_over:
            return

        keys = pygame.key.get_pressed()
        self.player.update(dt, keys, self.platforms, self.particles)
        phase_started, enemy_attack_started = self.enemy.update(
            dt, self.player, self.platforms, self.particles
        )
        if phase_started:
            self.enter_phase_two_map()
            self.audio.play("boss_scream")
            self.audio.start_ambience(True)
        if enemy_attack_started:
            self.audio.play("boss_attack")

        if self.player.attack_timer > 0 and self.player.attack_rect.colliderect(self.enemy.rect):
            if self.enemy.take_damage(10, self.particles):
                self.audio.play("impact")
                self.screen_shake = 0.12
                self.spawn_sparks(Vector2(self.enemy.rect.center), (255, 239, 169), 7)

        if self.enemy.attack_timer > 0 and self.enemy.attack_rect.colliderect(self.player.rect):
            if self.player.take_damage(15 if self.phase_two else 10, self.particles):
                self.audio.play("player_hurt")
                self.screen_shake = 0.2

        if self.enemy.phase_two and self.enemy.scream_timer > 0:
            self.screen_shake = max(self.screen_shake, 0.18)

        if self.player.health <= 0:
            self.game_over = "derrota"
        elif self.enemy.health <= 0:
            self.game_over = "vitoria"

        target_camera = self.player.position.x - WIDTH * 0.36
        self.camera_x += (target_camera - self.camera_x) * min(1, dt * 5)
        self.camera_x = clamp(self.camera_x, 0, WORLD_WIDTH - WIDTH)

    def draw_background(self, surface: Surface) -> None:
        if self.phase_two:
            top = (38, 7, 30)
            bottom = (111, 15, 47)
            moon_color = (255, 74, 99)
        else:
            top = (8, 15, 42)
            bottom = (28, 44, 77)
            moon_color = (194, 224, 255)

        for y in range(HEIGHT):
            ratio = y / HEIGHT
            color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
            pygame.draw.line(surface, color, (0, y), (WIDTH, y))

        # Lua e neblina em camadas para dar profundidade sem assets externos.
        moon_x = int(770 - self.camera_x * 0.12)
        pygame.draw.circle(surface, (*moon_color, 26), (moon_x, 104), 72)
        pygame.draw.circle(surface, moon_color, (moon_x, 104), 43)
        pygame.draw.circle(surface, top, (moon_x + 14, 93), 38)

        if self.phase_two:
            # Uma fenda vertical substitui a lua calma da primeira arena.
            rift_x = WIDTH // 2 + int(math.sin(self.elapsed * 1.4) * 34)
            pygame.draw.polygon(
                surface,
                (87, 7, 47),
                [(rift_x - 28, 0), (rift_x + 21, 0), (rift_x + 8, 116),
                 (rift_x + 31, 236), (rift_x - 15, 330), (rift_x - 36, 210)],
            )
            for offset in (-13, 0, 16):
                pygame.draw.line(
                    surface,
                    (255, 55, 100),
                    (rift_x + offset, 6),
                    (rift_x + offset + int(math.sin(self.elapsed * 3 + offset) * 16), 310),
                    2,
                )

        for layer, (color, height, speed) in enumerate(
            [((20, 28, 58), 220, 0.18), ((17, 24, 48), 280, 0.3), ((12, 17, 35), 350, 0.5)]
        ):
            points = []
            for x in range(-100, WIDTH + 140, 100):
                world_x = x + self.camera_x * speed
                peak = height + math.sin(world_x * 0.012 + layer * 2) * 28
                points.append((x, peak))
            points.extend([(WIDTH + 100, HEIGHT), (-100, HEIGHT)])
            pygame.draw.polygon(surface, color, points)

        # Pontos de luz que mudam levemente com o tempo.
        random.seed(12)
        for _ in range(36):
            world_x = random.randint(0, WORLD_WIDTH)
            x = int(world_x - self.camera_x * 0.28)
            y = random.randint(70, 325)
            if -5 < x < WIDTH + 5:
                radius = 1 if random.random() < 0.75 else 2
                brightness = 130 + int(math.sin(self.elapsed * 2 + world_x) * 40)
                pygame.draw.circle(surface, (brightness, brightness, min(255, brightness + 35)), (x, y), radius)
        random.seed()

    def draw_world(self, surface: Surface) -> None:
        # Chão e plataformas com linhas de recorte legíveis durante o combate.
        ground_color = (63, 19, 47) if self.phase_two else (18, 27, 54)
        platform_color = (91, 34, 65) if self.phase_two else (35, 47, 77)
        for platform in self.platforms:
            rect = platform.move(-int(self.camera_x), 0)
            pygame.draw.rect(surface, ground_color if platform.y >= GROUND_Y else platform_color, rect)
            pygame.draw.line(surface, (181, 65, 88) if self.phase_two else (84, 112, 151),
                             (rect.left, rect.top), (rect.right, rect.top), 3)
            if platform.y >= GROUND_Y:
                for x in range(rect.left - 20, rect.right, 42):
                    pygame.draw.line(surface, (42, 18, 43) if self.phase_two else (11, 18, 39),
                                     (x, rect.top + 12), (x + 18, HEIGHT), 2)
            elif self.phase_two:
                # Cristais pendurados deixam a nova arena visualmente diferente.
                for crystal_x in range(rect.left + 18, rect.right - 8, 42):
                    pygame.draw.polygon(
                        surface,
                        (130, 28, 73),
                        [(crystal_x, rect.bottom), (crystal_x + 9, rect.bottom + 18),
                         (crystal_x + 17, rect.bottom)],
                    )

        for particle in self.particles:
            particle.draw(surface, self.camera_x)
        self.enemy.draw(surface, self.camera_x)
        self.player.draw(surface, self.camera_x)

    def draw_hud(self, surface: Surface) -> None:
        # Vida do jogador
        draw_text(surface, "CAVALEIRO", (28, 18), 15, (177, 197, 226), bold=True)
        pygame.draw.rect(surface, (12, 15, 32), (28, 42, 224, 17), border_radius=5)
        player_ratio = self.player.health / 100
        pygame.draw.rect(surface, (93, 197, 224), (31, 45, int(218 * player_ratio), 11), border_radius=4)

        # Vida do chefe
        boss_label = "CAVALEIRO DO ABISMO — FÚRIA" if self.phase_two else "CAVALEIRO DO ABISMO"
        label_color = (255, 100, 124) if self.phase_two else (231, 216, 178)
        draw_text(surface, boss_label, (WIDTH - 32, 18), 15, label_color, center=False, bold=True)
        boss_bar = Rect(WIDTH - 292, 42, 260, 17)
        pygame.draw.rect(surface, (12, 15, 32), boss_bar, border_radius=5)
        ratio = self.enemy.health / self.enemy.max_health
        pygame.draw.rect(surface, (241, 73, 98) if self.phase_two else (202, 122, 89),
                         (boss_bar.x + 3, boss_bar.y + 3, int(254 * ratio), 11), border_radius=4)

        if self.message_timer > 0:
            draw_text(surface, "A lâmina encontrou o ritmo.", (WIDTH // 2, 30), 16, (210, 229, 255), center=True)

        audio_status = "SILÊNCIO" if self.audio.muted else f"{int(self.audio.master_volume * 100)}%"
        draw_text(surface, f"ÁUDIO {audio_status}", (WIDTH - 32, HEIGHT - 50), 13,
                  (180, 197, 226), center=False, bold=True)
        controls = "A/D mover   ESPAÇO pulo duplo   J atacar   M áudio   -/+ volume"
        draw_text(surface, controls, (WIDTH // 2, HEIGHT - 28), 14, (156, 175, 207), center=True)

        if self.audio_notice_timer > 0:
            notice = Surface((260, 42), pygame.SRCALPHA)
            notice.fill((8, 12, 31, 220))
            pygame.draw.rect(notice, (116, 146, 193, 150), notice.get_rect(), 1, border_radius=7)
            draw_text(notice, self.audio_notice, (130, 21), 15, (224, 235, 255), center=True, bold=True)
            surface.blit(notice, (WIDTH // 2 - 130, 58))

    def draw_overlay(self, surface: Surface) -> None:
        if self.rift_flash_timer > 0:
            alpha = int(clamp(self.rift_flash_timer / 0.8, 0, 1) * 120)
            overlay = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((255, 39, 86, alpha))
            surface.blit(overlay, (0, 0))

        if self.enemy.scream_timer > 0:
            alpha = int(45 + math.sin(self.elapsed * 17) * 20)
            overlay = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((128, 5, 28, alpha))
            surface.blit(overlay, (0, 0))
            draw_text(surface, "A ABISMO DESPERTA", (WIDTH // 2, 145), 31, (255, 224, 180), center=True, bold=True)
            draw_text(surface, "A segunda fase começou", (WIDTH // 2, 180), 18, (255, 126, 146), center=True)

        if self.phase_banner_timer > 0 and self.enemy.scream_timer <= 0:
            draw_text(surface, "O REI ALADO DO ABISMO", (WIDTH // 2, 122), 28, (255, 213, 133), center=True, bold=True)
            draw_text(surface, "A arena foi quebrada", (WIDTH // 2, 157), 17, (255, 126, 146), center=True)

        if self.game_over:
            overlay = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((4, 5, 15, 180))
            surface.blit(overlay, (0, 0))
            if self.game_over == "vitoria":
                title = "O ABISMO SILENCIOU"
                subtitle = "Você venceu o guardião."
                color = (184, 240, 255)
            else:
                title = "A ESCURIDÃO VENCEU"
                subtitle = "O cavaleiro caiu, mas a jornada continua."
                color = (255, 136, 154)
            draw_text(surface, title, (WIDTH // 2, 205), 34, color, center=True, bold=True)
            draw_text(surface, subtitle, (WIDTH // 2, 254), 18, (220, 225, 242), center=True)
            draw_text(surface, "Pressione R para tentar novamente", (WIDTH // 2, 316), 16, (171, 185, 212), center=True)

    def draw(self) -> None:
        scene = Surface((WIDTH, HEIGHT))
        self.draw_background(scene)
        self.draw_world(scene)
        self.draw_hud(scene)
        self.draw_overlay(scene)

        shake_x = random.randint(-int(self.screen_shake * 32), int(self.screen_shake * 32)) if self.screen_shake > 0 else 0
        shake_y = random.randint(-int(self.screen_shake * 22), int(self.screen_shake * 22)) if self.screen_shake > 0 else 0
        self.screen.fill((3, 5, 16))
        self.screen.blit(scene, (shake_x, shake_y))
        pygame.display.flip()

    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000, 0.033)
            self.handle_input()
            self.update(dt)
            self.draw()
        self.audio.shutdown()
        pygame.quit()


def main() -> None:
    from pantheon_game import PantheonGame

    PantheonGame().run()


if __name__ == "__main__":
    main()
