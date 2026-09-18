"""Versão dirigida do MVP: entrada, telegráfico, impacto e transformação."""
from __future__ import annotations

import math
import random

import pygame
from pygame import Surface
from pygame.math import Vector2

from mvp_game import (
    HEIGHT,
    WIDTH,
    Boss,
    DirectorGame if False else Game,
    Particle,
    Shockwave,
    clamp,
    glow,
    text,
)

# O alias acima não é válido como import em Python; mantemos o módulo explícito
# abaixo para deixar o arquivo autocontido e compatível com Python 3.13.
from mvp_game import Game


class DirectorBoss(Boss):
    """Adiciona eventos discretos sem duplicar a lógica do combate."""

    def __init__(self):
        super().__init__()
        self.attack_serial = 0
        self.phase_event = False

    def enter_phase_two(self, particles):
        super().enter_phase_two(particles)
        self.phase_event = True

    def update(self, dt, player, platforms, hazards, particles):
        previous_timer = self.attack_timer
        previous_phase = self.phase
        super().update(dt, player, platforms, hazards, particles)
        if self.attack_timer > 0 and previous_timer <= 0:
            self.attack_serial += 1
        if previous_phase == 1 and self.phase == 2:
            self.phase_event = True


class DirectorGame(Game):
    """Camada de direção visual sobre o loop do MVP."""

    def reset(self):
        super().reset()
        self.boss = DirectorBoss()
        self.cinematic_time = 0.0
        self.telegraph_flash = 0.0
        self.impact_flash = 0.0
        self.phase_flash = 0.0
        self.arena_pulse = 0.0
        self.last_attack_serial = 0

    def burst_directed(self, position, color, amount=18, *, upward=False, inward=False):
        for _ in range(amount):
            angle = random.uniform(0, math.tau)
            if upward:
                angle = random.uniform(math.pi * 1.08, math.pi * 1.92)
            speed = random.uniform(100, 360)
            velocity = Vector2(math.cos(angle) * speed, math.sin(angle) * speed)
            if inward:
                velocity *= -0.7
            self.particles.append(Particle(Vector2(position), velocity, color, random.uniform(2, 6), random.uniform(.35, .9), random.uniform(-40, 240), 1.5))

    def update(self, dt):
        self.cinematic_time += dt
        self.telegraph_flash = max(0.0, self.telegraph_flash - dt * 2.8)
        self.impact_flash = max(0.0, self.impact_flash - dt * 5.0)
        self.phase_flash = max(0.0, self.phase_flash - dt * 1.7)
        self.arena_pulse = max(0.0, self.arena_pulse - dt * 2.5)

        previous_health = self.player.health
        previous_boss_health = self.boss.health
        super().update(dt)

        if self.state == "fight" and self.boss.attack_serial != self.last_attack_serial:
            self.last_attack_serial = self.boss.attack_serial
            self.telegraph_flash = 1.0
            self.arena_pulse = max(self.arena_pulse, .55)
            color = (255, 220, 137) if self.boss.phase == 1 else (255, 70, 112)
            self.burst_directed(self.boss.rect.center, color, 10, inward=True)

        if self.boss.phase_event:
            self.boss.phase_event = False
            self.phase_flash = 1.0
            self.arena_pulse = 1.0
            self.screen_shake = max(self.screen_shake, 1.0)
            self.hit_stop = max(self.hit_stop, .10)
            self.burst_directed(self.boss.rect.center, (255, 70, 112), 55, upward=True)
            self.shockwaves.append(Shockwave(Vector2(self.boss.rect.center), (255, 55, 105), radius=24, life=.9, width=6))

        if self.player.health < previous_health:
            self.impact_flash = 1.0
            self.shockwaves.append(Shockwave(Vector2(self.player.rect.center), (255, 80, 120), radius=18, life=.55, width=5))
            self.burst_directed(self.player.rect.center, (255, 90, 125), 18)
        if self.boss.health < previous_boss_health:
            self.impact_flash = 1.0
            self.burst_directed(self.boss.rect.center, (255, 235, 160), 14, inward=True)

    def draw_director_overlay(self, surface):
        boss_center = (int(self.boss.rect.centerx - self.camera), int(self.boss.rect.centery))

        if self.state == "intro":
            progress = clamp(1.0 - self.state_timer / 2.8, 0.0, 1.0)
            reveal = progress * progress * (3 - 2 * progress)
            letterbox = int(54 * (1 - reveal))
            pygame.draw.rect(surface, (2, 2, 10), (0, 0, WIDTH, letterbox))
            pygame.draw.rect(surface, (2, 2, 10), (0, HEIGHT - letterbox, WIDTH, letterbox))
            pulse = 70 + int(abs(math.sin(self.cinematic_time * 4)) * 28)
            glow(surface, boss_center, (115, 55, 210), 75 + int(reveal * 45), pulse)
            pygame.draw.circle(surface, (245, 185, 110), boss_center, 24 + int(reveal * 78), 2)
            for ray in range(12):
                angle = self.cinematic_time * .8 + ray * math.tau / 12
                length = 35 + int(reveal * 110)
                pygame.draw.line(surface, (255, 80, 120), boss_center, (boss_center[0] + int(math.cos(angle) * length), boss_center[1] + int(math.sin(angle) * length)), 2)
            title = Surface((WIDTH, 120), pygame.SRCALPHA)
            text(title, "O REI DO ABISMO", (WIDTH // 2, 28), 34, (255, 225, 170), center=True, bold=True)
            text(title, "A COROA QUE ACORDA", (WIDTH // 2, 72), 17, (255, 105, 135), center=True, bold=True)
            title.set_alpha(int(clamp(math.sin(reveal * math.pi) * 1.5, 0, 1) * 255))
            surface.blit(title, (0, 132))

        if self.telegraph_flash > 0 and self.state == "fight":
            alpha = int(120 * self.telegraph_flash)
            warning = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            warning.fill((255, 185, 70, alpha // 5))
            surface.blit(warning, (0, 0))
            pygame.draw.rect(surface, (255, 207, 110), (18, 108, WIDTH - 36, HEIGHT - 145), 2)

        if self.impact_flash > 0:
            impact = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            impact.fill((255, 245, 210, int(140 * self.impact_flash)))
            surface.blit(impact, (0, 0))

        if self.phase_flash > 0:
            progress = 1.0 - self.phase_flash
            veil = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            veil.fill((150, 5, 45, int(100 * self.phase_flash)))
            surface.blit(veil, (0, 0))
            ring = int(55 + (progress * progress * (3 - 2 * progress)) * 310)
            pygame.draw.circle(surface, (255, 55, 105), boss_center, ring, max(2, int(8 * self.phase_flash)))
            pygame.draw.circle(surface, (255, 225, 150), boss_center, max(10, ring - 28), 2)
            for index in range(16):
                angle = self.cinematic_time * .7 + index * math.tau / 16
                start = Vector2(boss_center) + Vector2(math.cos(angle), math.sin(angle)) * 30
                end = Vector2(boss_center) + Vector2(math.cos(angle), math.sin(angle)) * (ring + 45)
                pygame.draw.line(surface, (255, 86, 125), start, end, 2)
            text(surface, "A ABISMO DESPERTA", (WIDTH // 2, 130), 30, (255, 230, 180), center=True, bold=True)
            text(surface, "A ARENA PERTENCE AO REI", (WIDTH // 2, 172), 16, (255, 110, 140), center=True, bold=True)

        if self.arena_pulse > 0 and self.state == "fight":
            alpha = int(90 * self.arena_pulse)
            layer = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.rect(layer, (255, 35, 90, alpha), (8, 92, WIDTH - 16, HEIGHT - 120), 3)
            surface.blit(layer, (0, 0))

    def draw(self):
        # Copia o pipeline do MVP sem chamar Game.draw(), evitando dois flips por frame.
        scene = Surface((WIDTH, HEIGHT))
        self.background(scene)
        for platform in self.platforms:
            rect = platform.move(-int(self.camera), 0)
            pygame.draw.rect(scene, (18, 28, 54) if platform.top >= 468 else (35, 47, 77), rect)
            pygame.draw.line(scene, (180, 70, 100) if self.boss.phase == 2 else (95, 125, 165), (rect.left, rect.top), (rect.right, rect.top), 3)
        for shock in self.shockwaves:
            shock.draw(scene, self.camera)
        for particle in self.particles:
            particle.draw(scene, self.camera)
        for hazard in self.hazards:
            hazard.draw(scene, self.camera, self.boss.phase)
        self.boss.draw(scene, self.camera)
        self.player.draw(scene, self.camera)
        self.draw_hud(scene)
        self.draw_director_overlay(scene)

        shake = int(self.screen_shake * 22)
        self.screen.fill((3, 5, 16))
        offset = (random.randint(-shake, shake), random.randint(-shake, shake)) if shake else (0, 0)
        self.screen.blit(scene, offset)
        pygame.display.flip()


if __name__ == "__main__":
    DirectorGame().run()
