"""Ecos do Abismo: demo vertical focada no Rei do Abismo.

Um boss, duas fases, feedback visual legível e efeitos sem assets externos.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

import pygame
from pygame import Rect, Surface
from pygame.math import Vector2

WIDTH, HEIGHT, FPS = 960, 540, 60
GROUND_Y, WORLD_WIDTH = 468, 1500
SAVE_FILE = Path("panteao_save.json")
WHITE = (240, 245, 255)


def clamp(value, low, high):
    return max(low, min(high, value))


def ease(value):
    value = clamp(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def text(surface, value, position, size, color, center=False, bold=False):
    font = pygame.font.SysFont("dejavusans", size, bold=bold)
    image = font.render(value, True, color)
    rect = image.get_rect(center=position if center else None)
    if not center:
        rect.topleft = position
    surface.blit(image, rect)


def glow(surface, center, color, radius, alpha=60):
    radius = max(4, int(radius))
    layer = Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
    middle = layer.get_width() // 2
    for index in range(4, 0, -1):
        r = radius * index // 4
        pygame.draw.circle(layer, (*color, alpha * index // 8), (middle, middle), r)
    surface.blit(layer, (center[0] - middle, center[1] - middle))


def land(position, previous_bottom, velocity_y, width, height, platforms):
    if velocity_y < 0:
        return None
    current = Rect(int(position.x), int(position.y), width, height)
    candidates = [p for p in platforms if current.right > p.left and current.left < p.right
                  and previous_bottom <= p.top + 4 and current.bottom >= p.top]
    return min(candidates, key=lambda p: p.top) if candidates else None


@dataclass
class Particle:
    position: Vector2
    velocity: Vector2
    color: tuple[int, int, int]
    radius: float
    life: float
    gravity: float = 0.0
    drag: float = 0.0

    def update(self, dt):
        self.position += self.velocity * dt
        self.velocity *= max(0.0, 1.0 - self.drag * dt)
        self.velocity.y += self.gravity * dt
        self.life -= dt
        self.radius *= 0.985
        return self.life > 0 and self.radius > 0.5

    def draw(self, surface, camera):
        alpha = int(clamp(self.life / 0.75, 0, 1) * 255)
        layer = Surface((24, 24), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*self.color, alpha), (12, 12), max(1, int(self.radius)))
        surface.blit(layer, (int(self.position.x - camera - 12), int(self.position.y - 12)))


@dataclass
class Shockwave:
    position: Vector2
    color: tuple[int, int, int]
    radius: float = 8
    life: float = 0.45
    width: int = 3

    def update(self, dt):
        self.radius += (260 - self.radius) * min(1, dt * 9)
        self.life -= dt
        return self.life > 0

    def draw(self, surface, camera):
        alpha = int(clamp(self.life / 0.45, 0, 1) * 220)
        layer = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.ellipse(layer, (*self.color, alpha),
                             (int(self.position.x - camera - self.radius), int(self.position.y - self.radius * .45),
                              int(self.radius * 2), int(self.radius * .9)), self.width)
        surface.blit(layer, (0, 0))


@dataclass
class Hazard:
    position: Vector2
    velocity: Vector2
    radius: int
    damage: int
    kind: str
    delay: float
    life: float = 2.0
    age: float = 0.0
    hit: bool = False

    @property
    def armed(self):
        return self.age >= self.delay

    def update(self, dt):
        self.age += dt
        self.life -= dt
        self.position += self.velocity * dt
        return self.life > 0 and not self.hit

    def draw(self, surface, camera, phase):
        x, y = int(self.position.x - camera), int(self.position.y)
        color = (255, 75, 107) if phase == 2 else (220, 83, 101)
        if not self.armed:
            pulse = int(4 + math.sin(self.age * 24) * 3)
            pygame.draw.circle(surface, (255, 215, 137), (x, y), self.radius + 10 + pulse, 2)
            pygame.draw.line(surface, (255, 190, 100), (x - 18, y), (x + 18, y), 2)
            return
        glow(surface, (x, y), color, self.radius * 3, 55)
        if self.kind == "ring":
            pygame.draw.circle(surface, color, (x, y), self.radius + int(self.age * 34), 6)
            pygame.draw.circle(surface, WHITE, (x, y), max(3, self.radius // 3), 2)
        else:
            pygame.draw.circle(surface, color, (x, y), self.radius)
            pygame.draw.circle(surface, (255, 225, 150), (x - 3, y - 3), max(2, self.radius // 3))


class Player:
    def __init__(self):
        self.position = Vector2(130, GROUND_Y - 72)
        self.velocity = Vector2()
        self.width, self.height = 42, 72
        self.facing = 1
        self.health = 100
        self.jumps = 2
        self.attack_timer = self.attack_cooldown = 0.0
        self.dodge_timer = self.dodge_cooldown = 0.0
        self.invulnerable = self.hurt_flash = 0.0
        self.walk_time = 0.0
        self.afterimages: list[tuple[Vector2, float]] = []

    @property
    def rect(self):
        return Rect(int(self.position.x), int(self.position.y), self.width, self.height)

    @property
    def attack_rect(self):
        x = self.position.x + (self.width if self.facing > 0 else -76)
        return Rect(int(x), int(self.position.y + 17), 76, 34)

    def jump(self, particles):
        if self.jumps <= 0:
            return
        self.velocity.y = -620 if self.jumps == 2 else -540
        self.jumps -= 1
        for _ in range(8):
            particles.append(Particle(Vector2(self.rect.centerx, self.rect.bottom), Vector2(random.uniform(-70, 70), random.uniform(-110, -20)), (170, 210, 235), 3, .45, 160))

    def attack(self, particles):
        if self.attack_timer > 0 or self.attack_cooldown > 0:
            return False
        self.attack_timer, self.attack_cooldown = .22, .28
        for _ in range(7):
            particles.append(Particle(Vector2(self.attack_rect.center), Vector2(random.uniform(40, 150) * self.facing, random.uniform(-45, 45)), (220, 245, 255), 3, .28, 0, 3))
        return True

    def dodge(self, particles):
        if self.dodge_timer > 0 or self.dodge_cooldown > 0:
            return False
        self.dodge_timer, self.dodge_cooldown, self.invulnerable = .18, .78, .30
        self.velocity = Vector2(self.facing * 760, 0)
        for _ in range(12):
            particles.append(Particle(Vector2(self.rect.center), Vector2(-self.facing * random.uniform(100, 280), random.uniform(-70, 70)), (160, 220, 255), 4, .35, 150))
        return True

    def damage(self, amount, particles):
        if self.invulnerable > 0:
            return False
        self.health = max(0, self.health - amount)
        self.invulnerable, self.hurt_flash = .85, .20
        self.velocity.x = -240 if self.facing > 0 else 240
        for _ in range(16):
            particles.append(Particle(Vector2(self.rect.center), Vector2(random.uniform(-180, 180), random.uniform(-180, 40)), (255, 105, 135), 4, .55, 320))
        return True

    def update(self, dt, keys, platforms, particles):
        for name in ("attack_timer", "attack_cooldown", "dodge_timer", "dodge_cooldown", "invulnerable", "hurt_flash"):
            setattr(self, name, max(0.0, getattr(self, name) - dt))
        self.afterimages = [(p, life - dt * 2) for p, life in self.afterimages if life - dt * 2 > 0]
        if self.dodge_timer > 0:
            self.position.x = clamp(self.position.x + self.velocity.x * dt, 20, WORLD_WIDTH - self.width - 20)
            self.afterimages.append((Vector2(self.position), .55))
            return
        direction = (1 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0) - (1 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0)
        if direction:
            self.facing, self.velocity.x = direction, direction * 300
            self.walk_time += dt * 12
        else:
            self.velocity.x *= max(0, 1 - 13 * dt)
            self.walk_time += dt * 3
        previous_bottom = self.position.y + self.height
        self.velocity.y += 1450 * dt
        self.position.x = clamp(self.position.x + self.velocity.x * dt, 20, WORLD_WIDTH - self.width - 20)
        self.position.y += self.velocity.y * dt
        landing = land(self.position, previous_bottom, self.velocity.y, self.width, self.height, platforms)
        if landing:
            self.position.y, self.velocity.y, self.jumps = landing.top - self.height, 0, 2

    def draw(self, surface, camera):
        if self.invulnerable > 0 and int(self.invulnerable * 18) % 2 == 0:
            return
        x, y = int(self.position.x - camera), int(self.position.y + math.sin(self.walk_time) * (2 if abs(self.velocity.x) > 20 else 0))
        cloak = (255, 140, 155) if self.hurt_flash > 0 else WHITE
        for position, life in self.afterimages:
            ghost = Surface((58, 80), pygame.SRCALPHA)
            pygame.draw.polygon(ghost, (*cloak, int(35 * clamp(life, 0, 1))), [(29, 15), (5, 72), (53, 72)])
            surface.blit(ghost, (int(position.x - camera - 8), int(position.y)))
        pygame.draw.ellipse(surface, (8, 12, 28), (x - 5, y + 61, 52, 14))
        pygame.draw.polygon(surface, (36, 42, 74), [(x + 21, y + 27), (x + 3, y + 69), (x + 39, y + 69)])
        pygame.draw.polygon(surface, cloak, [(x + 12, y + 19), (x + 7, y - 3), (x + 18, y + 8), (x + 24, y - 8), (x + 31, y + 8), (x + 39, y - 3), (x + 34, y + 23)])
        pygame.draw.ellipse(surface, (17, 21, 44), (x + 15, y + 12, 19, 17))
        pygame.draw.circle(surface, (175, 220, 255), (x + 21, y + 20), 2)
        pygame.draw.circle(surface, (175, 220, 255), (x + 29, y + 20), 2)
        if self.attack_timer > 0:
            progress = 1 - self.attack_timer / .22
            radius = int(34 + progress * 18)
            center = (x + (44 if self.facing > 0 else -2), y + 35)
            pygame.draw.arc(surface, (225, 247, 255), Rect(center[0] - radius, center[1] - radius, radius * 2, radius * 2), -1.2 if self.facing > 0 else 2, 1.2 if self.facing > 0 else 4.4, 5)


class Boss:
    def __init__(self):
        self.position = Vector2(1050, GROUND_Y - 110)
        self.width, self.height = 68, 110
        self.health = self.max_health = 240
        self.phase = 1
        self.facing = -1
        self.velocity = Vector2()
        self.attack_timer = self.attack_cooldown = .7
        self.invulnerable = self.hurt_flash = 0.0
        self.transition = 0.0
        self.anim_time = 0.0
        self.attack_kind = ""

    @property
    def rect(self):
        return Rect(int(self.position.x), int(self.position.y), self.width, self.height)

    @property
    def attack_rect(self):
        reach = 86 if self.phase == 1 else 125
        x = self.position.x + (self.width if self.facing > 0 else -reach)
        return Rect(int(x), int(self.position.y + 25), reach, 58)

    def damage(self, amount, particles):
        if self.invulnerable > 0 or self.transition > 0:
            return False
        self.health = max(0, self.health - amount)
        self.invulnerable, self.hurt_flash = .16, .16
        self.velocity.x = -100 * self.facing
        for _ in range(12):
            particles.append(Particle(Vector2(self.rect.center), Vector2(random.uniform(-160, 160), random.uniform(-180, 60)), (255, 225, 135), 4, .55, 260))
        return True

    def enter_phase_two(self, particles):
        self.phase = 2
        self.transition = 2.8
        self.width, self.height = 104, 154
        self.position.y = GROUND_Y - self.height
        self.velocity = Vector2(0, -100)
        for _ in range(58):
            angle, speed = random.uniform(0, math.tau), random.uniform(120, 360)
            particles.append(Particle(Vector2(self.rect.center), Vector2(math.cos(angle) * speed, math.sin(angle) * speed), random.choice([(255, 55, 100), (255, 170, 82), (160, 45, 110)]), random.uniform(3, 8), random.uniform(.7, 1.5), 100))

    def update(self, dt, player, platforms, hazards, particles):
        self.anim_time += dt
        for name in ("attack_timer", "attack_cooldown", "invulnerable", "hurt_flash", "transition"):
            setattr(self, name, max(0.0, getattr(self, name) - dt))
        if self.health <= self.max_health * .5 and self.phase == 1:
            self.enter_phase_two(particles)
        if self.transition > 0:
            return
        distance = player.position.x - self.position.x
        self.facing = 1 if distance > 0 else -1
        self.velocity.x = self.facing * (250 if self.phase == 2 else 125)
        if abs(distance) < (175 if self.phase == 2 else 120):
            self.velocity.x *= .15
        if self.phase == 1:
            self.velocity.y += 1400 * dt
        else:
            target_y = clamp(player.position.y - 120 + math.sin(self.anim_time * 2.4) * 45, 70, GROUND_Y - self.height - 18)
            self.velocity.y = (target_y - self.position.y) * 3.2
        if self.attack_cooldown <= 0:
            self.attack_cooldown = .95 if self.phase == 1 else .68
            self.attack_timer = .36 if self.phase == 1 else .48
            self.attack_kind = "CÍRCULO DO ABISMO" if self.phase == 2 else "CORTE DA COROA"
            direction = 1 if distance > 0 else -1
            center = Vector2(self.rect.center)
            if self.phase == 1:
                hazards.append(Hazard(center, Vector2(direction * 230, 0), 19, 14, "slash", .28, 1.8))
                hazards.append(Hazard(Vector2(player.position.x + direction * 35, GROUND_Y - 30), Vector2(), 20, 12, "burst", .18, 1.4))
            else:
                hazards.append(Hazard(Vector2(player.position.x, GROUND_Y - 38), Vector2(), 30, 17, "ring", .28, 1.8))
                hazards.append(Hazard(center, Vector2(direction * 300, 0), 24, 16, "slash", .22, 1.8))
                hazards.append(Hazard(Vector2(player.position.x, 65), Vector2(), 23, 14, "burst", .18, 1.4))
        previous_bottom = self.position.y + self.height
        self.position.x = clamp(self.position.x + self.velocity.x * dt, 700, WORLD_WIDTH - self.width - 20)
        self.position.y += self.velocity.y * dt
        if self.phase == 1:
            landing = land(self.position, previous_bottom, self.velocity.y, self.width, self.height, platforms)
            if landing:
                self.position.y, self.velocity.y = landing.top - self.height, 0

    def draw(self, surface, camera):
        x, y = int(self.position.x - camera), int(self.position.y)
        center = x + self.width // 2
        pulse = math.sin(self.anim_time * (8 if self.phase == 2 else 4))
        cloak = (255, 85, 108) if self.hurt_flash > 0 else ((90, 18, 47) if self.phase == 2 else (35, 29, 70))
        glow_color = (255, 50, 92) if self.phase == 2 else (110, 90, 195)
        pygame.draw.ellipse(surface, (8, 8, 20), (center - int(self.width * .75), y + self.height - 9, int(self.width * 1.5), 22))
        if self.phase == 2:
            wing_y = y + 60 + int(pulse * 8)
            for side in (-1, 1):
                pygame.draw.polygon(surface, (120, 16, 60), [(center + side * 25, wing_y), (center + side * 135, wing_y - 58), (center + side * 88, wing_y + 18), (center + side * 145, wing_y + 48), (center + side * 22, wing_y + 38)])
            for radius in (78, 102, 126):
                pygame.draw.arc(surface, (255, 55, 105), Rect(center - radius, y + 38 - radius // 3, radius * 2, radius * 2), .55, 2.6, 2)
            glow(surface, (center, y + 55), glow_color, 100, 50)
        pygame.draw.polygon(surface, cloak, [(center, y + 28), (center - self.width // 2, y + self.height - 5), (center + self.width // 2, y + self.height - 5)])
        pygame.draw.polygon(surface, (125, 35, 70) if self.phase == 2 else (55, 49, 94), [(center, y + 32), (center - self.width // 4, y + self.height - 12), (center + self.width // 4, y + self.height - 12)])
        head = Rect(center - int(self.width * .31), y + 14, int(self.width * .62), int(self.height * .25))
        pygame.draw.ellipse(surface, (220, 228, 246), head)
        pygame.draw.polygon(surface, (238, 242, 255), [(head.left + 7, head.top + 10), (head.left - 14, head.top - 15), (center - 5, head.top + 7), (center, head.top - 25), (center + 5, head.top + 7), (head.right + 14, head.top - 15), (head.right - 7, head.top + 10)])
        pygame.draw.ellipse(surface, (13, 11, 31), head.inflate(-10, -7))
        eye = (255, 65, 102) if self.phase == 2 else (252, 214, 128)
        glow(surface, (center, head.centery), eye, 28, 55)
        pygame.draw.circle(surface, eye, (center - 8, head.centery), 3 + self.phase)
        pygame.draw.circle(surface, eye, (center + 8, head.centery), 3 + self.phase)
        if self.phase == 1:
            pygame.draw.lines(surface, (255, 211, 116), False, [(center - 25, y - 20), (center - 17, y - 43), (center - 4, y - 28), (center + 5, y - 48), (center + 15, y - 29), (center + 28, y - 39)], 3)
        if self.attack_timer > 0:
            radius = 48 if self.phase == 1 else 82
            center_attack = (center + (self.width // 2 + 17 if self.facing > 0 else -(self.width // 2 + 17)), y + int(self.height * .45))
            pygame.draw.arc(surface, glow_color, Rect(center_attack[0] - radius, center_attack[1] - radius, radius * 2, radius * 2), -1.1 if self.facing > 0 else 2.05, 1.1 if self.facing > 0 else 4.25, 8)
            text(surface, self.attack_kind, (center, y - 50), 14, (255, 202, 137), center=True, bold=True)
        if self.transition > 0:
            text(surface, "O ABISMO DESPERTA", (center, y - 70), 28, (255, 224, 175), center=True, bold=True)


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Ecos do Abismo — Rei do Abismo")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.running = True
        self.reset()

    def reset(self):
        self.player, self.boss = Player(), Boss()
        self.particles, self.shockwaves, self.hazards = [], [], []
        self.camera = self.screen_shake = self.hit_stop = 0.0
        self.elapsed = 0.0
        self.state = "intro"
        self.state_timer = 2.8
        self.jump_down = self.attack_down = self.dodge_down = False
        self.platforms = [Rect(0, GROUND_Y, WORLD_WIDTH, HEIGHT - GROUND_Y), Rect(280, 390, 170, 18), Rect(650, 330, 190, 18), Rect(1010, 390, 210, 18), Rect(1260, 300, 180, 18)]

    def input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                if event.key == pygame.K_r and self.state in {"win", "lose"}:
                    self.reset()
        keys = pygame.key.get_pressed()
        jump = bool(keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP])
        attack = bool(keys[pygame.K_j] or keys[pygame.K_x])
        dodge = bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
        if self.state == "fight":
            if jump and not self.jump_down:
                self.player.jump(self.particles)
            if attack and not self.attack_down:
                self.player.attack(self.particles)
            if dodge and not self.dodge_down:
                self.player.dodge(self.particles)
        self.jump_down, self.attack_down, self.dodge_down = jump, attack, dodge

    def burst(self, position, color, amount=18):
        for _ in range(amount):
            angle, speed = random.uniform(0, math.tau), random.uniform(100, 360)
            self.particles.append(Particle(Vector2(position), Vector2(math.cos(angle) * speed, math.sin(angle) * speed), color, random.uniform(2, 6), random.uniform(.35, .9), random.uniform(-40, 240), 1.5))

    def update(self, dt):
        self.elapsed += dt
        self.screen_shake = max(0, self.screen_shake - dt * 2.6)
        self.hit_stop = max(0, self.hit_stop - dt)
        self.particles = [p for p in self.particles if p.update(dt)]
        self.shockwaves = [s for s in self.shockwaves if s.update(dt)]
        if self.hit_stop > 0:
            return
        if self.state == "intro":
            self.state_timer -= dt
            self.boss.anim_time += dt
            if self.state_timer <= 0:
                self.state = "fight"
            return
        if self.state != "fight":
            return
        self.player.update(dt, pygame.key.get_pressed(), self.platforms, self.particles)
        self.boss.update(dt, self.player, self.platforms, self.hazards, self.particles)
        for hazard in list(self.hazards):
            if hazard.update(dt) and hazard.armed and hazard.position.distance_to(self.player.rect.center) < hazard.radius + 25:
                if self.player.damage(hazard.damage, self.particles):
                    hazard.hit = True
                    self.screen_shake = .25
                    self.shockwaves.append(Shockwave(Vector2(self.player.rect.center), (255, 90, 120)))
        self.hazards = [h for h in self.hazards if h.life > 0 and not h.hit]
        if self.player.attack_timer > 0 and self.player.attack_rect.colliderect(self.boss.rect):
            if self.boss.damage(12, self.particles):
                self.hit_stop, self.screen_shake = .065, .16
                self.shockwaves.append(Shockwave(Vector2(self.boss.rect.center), (255, 225, 145)))
                self.burst(self.boss.rect.center, (255, 238, 165), 9)
        if self.boss.health <= 0:
            self.state, self.state_timer = "win", 3.4
        elif self.player.health <= 0:
            self.state, self.state_timer = "lose", 2.0
        target = self.player.position.x - WIDTH * .36
        self.camera += (target - self.camera) * min(1, dt * 5)
        self.camera = clamp(self.camera, 0, WORLD_WIDTH - WIDTH)

    def background(self, surface):
        phase = self.boss.phase == 2
        top, bottom = ((38, 7, 30), (111, 15, 47)) if phase else ((8, 15, 42), (28, 44, 77))
        for y in range(HEIGHT):
            ratio = y / HEIGHT
            pygame.draw.line(surface, tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)), (0, y), (WIDTH, y))
        moon = (255, 75, 105) if phase else (194, 224, 255)
        mx = int(770 - self.camera * .12)
        glow(surface, (mx, 104), moon, 90, 35)
        pygame.draw.circle(surface, moon, (mx, 104), 42)
        if phase:
            rift = WIDTH // 2 + int(math.sin(self.elapsed * 1.4) * 35)
            pygame.draw.polygon(surface, (85, 5, 45), [(rift - 24, 0), (rift + 20, 0), (rift + 8, 150), (rift + 30, 280), (rift - 30, 360)])
            for offset in (-14, 0, 15):
                pygame.draw.line(surface, (255, 55, 100), (rift + offset, 0), (rift + offset + int(math.sin(self.elapsed * 3 + offset) * 16), 320), 2)
        for layer, (color, height, speed) in enumerate([((20, 28, 58), 220, .18), ((17, 24, 48), 280, .3), ((12, 17, 35), 350, .5)]):
            points = [(x, height + math.sin((x + self.camera * speed) * .012 + layer * 2) * 28) for x in range(-100, WIDTH + 140, 100)]
            points += [(WIDTH + 100, HEIGHT), (-100, HEIGHT)]
            pygame.draw.polygon(surface, color, points)

    def draw_hud(self, surface):
        text(surface, "LIRA", (24, 18), 14, (185, 205, 235), bold=True)
        pygame.draw.rect(surface, (12, 15, 32), (24, 40, 230, 16), border_radius=5)
        pygame.draw.rect(surface, (95, 205, 235), (27, 43, int(224 * self.player.health / 100), 10), border_radius=4)
        label = "REI DO ABISMO — FÚRIA" if self.boss.phase == 2 else "REI DO ABISMO"
        text(surface, label, (WIDTH - 300, 18), 14, (255, 105, 130) if self.boss.phase == 2 else (235, 215, 180), bold=True)
        pygame.draw.rect(surface, (12, 15, 32), (WIDTH - 300, 40, 276, 16), border_radius=5)
        pygame.draw.rect(surface, (245, 75, 100), (WIDTH - 297, 43, int(270 * self.boss.health / self.boss.max_health), 10), border_radius=4)
        dodge = "PRONTA" if self.player.dodge_cooldown <= 0 else f"{self.player.dodge_cooldown:.1f}s"
        text(surface, f"SHIFT ESQUIVA: {dodge}", (24, 68), 11, (180, 225, 255), bold=True)
        text(surface, "A/D mover   ESPAÇO pular   J/X atacar   SHIFT esquivar   R reiniciar", (WIDTH // 2, HEIGHT - 22), 12, (165, 185, 215), center=True)

    def draw(self):
        scene = Surface((WIDTH, HEIGHT))
        self.background(scene)
        for platform in self.platforms:
            rect = platform.move(-int(self.camera), 0)
            pygame.draw.rect(scene, (18, 28, 54) if platform.top >= GROUND_Y else (35, 47, 77), rect)
            pygame.draw.line(scene, (180, 70, 100) if self.boss.phase == 2 else (95, 125, 165), (rect.left, rect.top), (rect.right, rect.top), 3)
        for shock in self.shockwaves:
            shock.draw(scene, self.camera)
        for p in self.particles:
            p.draw(scene, self.camera)
        for h in self.hazards:
            h.draw(scene, self.camera, self.boss.phase)
        self.boss.draw(scene, self.camera)
        self.player.draw(scene, self.camera)
        self.draw_hud(scene)
        if self.state == "intro":
            overlay = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((2, 2, 12, 150))
            scene.blit(overlay, (0, 0))
            text(scene, "O REI DO ABISMO", (WIDTH // 2, 190), 34, (255, 224, 170), center=True, bold=True)
            text(scene, "A COROA QUE ACORDA", (WIDTH // 2, 235), 18, (255, 110, 135), center=True, bold=True)
        elif self.state in {"win", "lose"}:
            overlay = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((3, 4, 14, 185))
            scene.blit(overlay, (0, 0))
            title = "O ABISMO SILENCIOU" if self.state == "win" else "A ESCURIDÃO VENCEU"
            color = (190, 240, 255) if self.state == "win" else (255, 135, 155)
            text(scene, title, (WIDTH // 2, 210), 34, color, center=True, bold=True)
            text(scene, "Pressione R para lutar novamente", (WIDTH // 2, 270), 17, (220, 225, 240), center=True)
        shake = int(self.screen_shake * 22)
        self.screen.fill((3, 5, 16))
        self.screen.blit(scene, (random.randint(-shake, shake), random.randint(-shake, shake)) if shake else (0, 0))
        pygame.display.flip()

    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000, .033)
            self.input()
            self.update(dt)
            self.draw()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
