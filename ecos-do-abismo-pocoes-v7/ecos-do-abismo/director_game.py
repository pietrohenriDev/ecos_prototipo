"""Camada de direção visual para a demo do Rei do Abismo.

Mantém o núcleo de combate enxuto e concentra o polimento em três momentos:
entrada, telegráfico/impacto e transformação. Não depende de assets externos.
"""
from __future__ import annotations

import math
import random

import pygame
from pygame import Rect, Surface
from pygame.math import Vector2

from mvp_game import HEIGHT, WIDTH, Boss, Game, Particle, Shockwave, clamp, glow, text


class DirectorBoss(Boss):
    """Boss base com eventos visuais explícitos para a camada de direção."""

    def __init__(self):
        super().__init__()
        self.attack_serial = 0
        self.last_attack_phase = 1
        self.phase_event = False

    def enter_phase_two(self, particles):
        super().enter_phase_two(particles)
        self.phase_event = True

    def update(self, dt, player, platforms, hazards, particles):
        before_timer = self.attack_timer
        before_phase = self.phase
        super().update(dt, player, platforms, hazards, particles)
        if self.attack_timer > 0 and before_timer <= 0:
            self.attack_serial += 1
            self.last_attack_phase = self.phase
        if before_phase == 1 and self.phase == 2:
            self.phase_event = True


class DirectorGame(Game):
    """Versão dirigida: o combate continua simples, mas cada beat tem encenação."""

    def reset(self):
        super().reset()
        self.boss = DirectorBoss()
        self.cinematic_time = 0.0
        self.telegraph_flash = 0.0
        self.impact_flash = 0.0
        self.phase_flash = 0.0
        self.arena_pulse = 0.0
        self.last_attack_serial = 0
        self.phase_particles_spawned = False

    def burst_directed(self, position, color, amount=18, *, upward=False, inward=False):
        for _ in range(amount):
            angle = random.uniform(0, math.tau)
            if upward:
                angle = random.uniform(math.pi * 1.08, math.pi * 1.92)
            speed = random.uniform(100, 360)
            velocity = Vector2(math.cos(angle) * speed, math.sin(angle) * speed)
            if inward:
                velocity *= -0.7
            self.particles.append(
                Particle(Vector2(position), velocity, color, random.uniform(2, 6), random.uniform(.35, .9), random.uniform(-40, 240), 1.5)
            )

    def update(self, dt):
        self.cinematic_time += dt
        self.telegraph_flash = max(0.0, self.telegraph_flash - dt * 2.8)
        self.impact_flash = max(0.0, self.impact_flash - dt * 5.0)
        self.phase_flash = max(0.0, self.phase_flash - dt * 1.7)
        self.arena_pulse = max(0.0, self.arena_pulse - dt * 2.5)
        super().update(dt)

        if self.state == "intro":
            self.cinematic_time += dt * 0.8

        if self.state == "fight" and self.boss.attack_serial != self.last_attack_serial:
            self.last_attack_serial = self.boss.attack_serial
            self.telegraph_flash = 1.0
            self.arena_pulse = max(self.arena_pulse, .55)
            # O aviso nasce com uma família de partículas diferente por fase.
            center = Vector2(self.boss.rect.center)
            self.burst_directed(center, (255, 220, 137) if self.boss.phase == 1 else (255, 70, 112), 10, inward=True)

        if self.boss.phase_event:
            self.boss.phase_event = False
            self.phase_flash = 1.0
            self.arena_pulse = 1.0
            self.screen_shake = max(self.screen_shake, 1.0)
            self.hit_stop = max(self.hit_stop, .10)
            self.burst_directed(self.boss.rect.center, (255, 70, 112), 55, upward=True)
            self.shockwaves.append(Shockwave(Vector2(self.boss.rect.center), (255, 55, 105), radius=24, life=.9, width=6))

    def draw_director_overlay(self, surface):
        boss_center = (int(self.boss.rect.centerx - self.camera), int(self.boss.rect.centery))

        # Entrada: silhueta, pulsação e barras de cinema antes do controle voltar.
        if self.state == "intro":
            progress = 1.0 - self.state_timer / 2.8
            reveal = clamp(progress, 0.0, 1.0)
            letterbox = int(54 * (1.0 - ease(reveal)))
            pygame.draw.rect(surface, (2, 2, 10), (0, 0, WIDTH, letterbox))
            pygame.draw.rect(surface, (2, 2, 10), (0, HEIGHT - letterbox, WIDTH, letterbox))
            pulse = 70 + int(abs(math.sin(self.cinematic_time * 4)) * 28)
            glow(surface, boss_center, (115, 55, 210), 75 + int(reveal * 45), pulse)
            pygame.draw.circle(surface, (245, 185, 110), boss_center, 24 + int(reveal * 78), 2)
            for ray in range(12):
                angle = self.cinematic_time * .8 + ray * math.tau / 12
                length = 35 + int(reveal * 110)
                pygame.draw.line(surface, (255, 80, 120), boss_center,
                                 (boss_center[0] + int(math.cos(angle) * length), boss_center[1] + int(math.sin(angle) * length)), 2)
            alpha = int(clamp(math.sin(reveal * math.pi) * 1.5, 0, 1) * 255)
            title_layer = Surface((WIDTH, 120), pygame.SRCALPHA)
            text(title_layer, "O REI DO ABISMO", (WIDTH // 2, 28), 34, (255, 225, 170), center=True, bold=True)
            text(title_layer, "A COROA QUE ACORDA", (WIDTH // 2, 72), 17, (255, 105, 135), center=True, bold=True)
            title_layer.set_alpha(alpha)
            surface.blit(title_layer, (0, 132))

        # A preparação é dourada e fina; o dano é vermelho, largo e instantâneo.
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

        # A transformação domina o quadro e não apenas o sprite.
        if self.phase_flash > 0:
            progress = 1.0 - self.phase_flash
            veil = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            veil.fill((150, 5, 45, int(100 * self.phase_flash)))
            surface.blit(veil, (0, 0))
            center = boss_center
            ring = int(55 + ease(progress) * 310)
            pygame.draw.circle(surface, (255, 55, 105), center, ring, max(2, int(8 * self.phase_flash)))
            pygame.draw.circle(surface, (255, 225, 150), center, max(10, ring - 28), 2)
            for index in range(16):
                angle = self.cinematic_time * .7 + index * math.tau / 16
                start = Vector2(center) + Vector2(math.cos(angle), math.sin(angle)) * 30
                end = Vector2(center) + Vector2(math.cos(angle), math.sin(angle)) * (ring + 45)
                pygame.draw.line(surface, (255, 86, 125), start, end, 2)
            text(surface, "A ABISMO DESPERTA", (WIDTH // 2, 130), 30, (255, 230, 180), center=True, bold=True)
            text(surface, "A ARENA PERTENCE AO REI", (WIDTH // 2, 172), 16, (255, 110, 140), center=True, bold=True)

        # Pulso periférico: o chefe parece controlar o espaço inteiro.
        if self.arena_pulse > 0 and self.state == "fight":
            alpha = int(90 * self.arena_pulse)
            layer = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.rect(layer, (255, 35, 90, alpha), (8, 92, WIDTH - 16, HEIGHT - 120), 3)
            surface.blit(layer, (0, 0))

    def update(self, dt):
        before_player_health = self.player.health
        before_boss_health = self.boss.health
        super().update(dt)
        if self.player.health < before_player_health:
            self.impact_flash = 1.0
            self.shockwaves.append(Shockwave(Vector2(self.player.rect.center), (255, 80, 120), radius=18, life=.55, width=5))
            self.burst_directed(self.player.rect.center, (255, 90, 125), 18)
        if self.boss.health < before_boss_health:
            self.impact_flash = 1.0
            self.burst_directed(self.boss.rect.center, (255, 235, 160), 14, inward=True)

    def draw(self):
        super().draw()
        # A segunda camada é aplicada sobre a cena já composta, preservando o
        # pipeline do MVP e permitindo iterar a direção sem reescrever o jogo.
        self.draw_director_overlay(self.screen)
        pygame.display.flip()


if __name__ == "__main__":
    DirectorGame().run()
