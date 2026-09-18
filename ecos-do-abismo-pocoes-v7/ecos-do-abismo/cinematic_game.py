"""Apresentação cinematográfica do Rei do Abismo.

Camada de direção sobre o MVP: não altera o núcleo de colisão, mas transforma
entrada, telegráficos, transição e presença da arena em eventos visuais claros.
"""
from __future__ import annotations

import math
import random

import pygame
from pygame import Surface
from pygame.math import Vector2

from director_game import DirectorGame
from mvp_game import HEIGHT, WIDTH, Particle, Shockwave, clamp, glow, text


class CinematicGame(DirectorGame):
    """Versão de apresentação com encenação forte e leitura preservada."""

    def reset(self):
        super().reset()
        self.cinema_flash = 0.0
        self.damage_flash = 0.0
        self.pressure = 0.0
        self.vortex_time = 0.0
        self.last_phase = self.boss.phase
        self.last_health = self.player.health
        self.last_boss_health = self.boss.health

    def vortex(self, center, color, count=6, inward=False):
        """Cria partículas em espiral, usadas como assinatura do domínio."""
        for index in range(count):
            angle = self.vortex_time * 2.2 + index * math.tau / max(1, count)
            radius = random.uniform(45, 145)
            position = Vector2(center) + Vector2(math.cos(angle), math.sin(angle) * .62) * radius
            tangent = Vector2(-math.sin(angle), math.cos(angle) * .62)
            velocity = tangent * random.uniform(90, 210)
            if inward:
                velocity += (Vector2(center) - position) * 1.3
            self.particles.append(Particle(position, velocity, color, random.uniform(2, 5), random.uniform(.45, 1.0), 0, 1.0))

    def update(self, dt):
        self.vortex_time += dt
        self.cinema_flash = max(0.0, self.cinema_flash - dt * 2.4)
        self.damage_flash = max(0.0, self.damage_flash - dt * 5.5)
        self.pressure = max(0.0, self.pressure - dt * 1.8)
        previous_phase = self.boss.phase
        previous_player_health = self.player.health
        previous_boss_health = self.boss.health
        super().update(dt)

        if self.state == "intro":
            self.pressure = max(self.pressure, .35)
            if random.random() < min(1.0, dt * 15):
                self.vortex(self.boss.rect.center, (170, 70, 210), 3, inward=True)

        if self.state == "fight":
            if self.boss.attack_serial != self.last_attack_serial:
                self.pressure = max(self.pressure, .65)
                self.cinema_flash = max(self.cinema_flash, .35)
                self.vortex(self.boss.rect.center, (255, 207, 111) if self.boss.phase == 1 else (255, 60, 112), 7, inward=True)

            if self.boss.phase == 2 and random.random() < min(1.0, dt * 18):
                self.vortex(self.boss.rect.center, (255, 45, 105), 4)
                self.pressure = max(self.pressure, .25)

        if previous_phase != self.boss.phase:
            self.cinema_flash = 1.0
            self.pressure = 1.0
            self.vortex(self.boss.rect.center, (255, 65, 112), 42, inward=False)
            self.shockwaves.append(Shockwave(Vector2(self.boss.rect.center), (255, 48, 105), radius=20, life=1.0, width=8))

        if self.player.health < previous_player_health or self.boss.health < previous_boss_health:
            self.damage_flash = 1.0
            self.pressure = max(self.pressure, .5)

    def draw_cinematic_layer(self, surface):
        center = (int(self.boss.rect.centerx - self.camera), int(self.boss.rect.centery))

        # Intro em três batidas: silêncio, revelação da coroa e assinatura do nome.
        if self.state == "intro":
            progress = clamp(1.0 - self.state_timer / 2.8, 0.0, 1.0)
            reveal = progress * progress * (3.0 - 2.0 * progress)
            bars = int(62 * (1.0 - reveal))
            pygame.draw.rect(surface, (1, 1, 7), (0, 0, WIDTH, bars))
            pygame.draw.rect(surface, (1, 1, 7), (0, HEIGHT - bars, WIDTH, bars))
            glow(surface, center, (105, 42, 190), 80 + int(reveal * 65), 55 + int(reveal * 40))
            pygame.draw.circle(surface, (255, 208, 125), center, 22 + int(reveal * 84), 2)
            for index in range(18):
                angle = self.vortex_time * .65 + index * math.tau / 18
                radius = 30 + int(reveal * 125)
                start = Vector2(center) + Vector2(math.cos(angle), math.sin(angle) * .65) * 28
                end = Vector2(center) + Vector2(math.cos(angle), math.sin(angle) * .65) * radius
                pygame.draw.line(surface, (255, 63, 112), start, end, 2)
            title = Surface((WIDTH, 150), pygame.SRCALPHA)
            text(title, "O REI DO ABISMO", (WIDTH // 2, 32), 38, (255, 229, 177), center=True, bold=True)
            text(title, "A COROA QUE ACORDA", (WIDTH // 2, 82), 18, (255, 99, 132), center=True, bold=True)
            title.set_alpha(int(clamp(math.sin(progress * math.pi) * 1.6, 0, 1) * 255))
            surface.blit(title, (0, 128))

        # O telegráfico é quente e fino; o dano vira vermelho e ocupa a tela.
        if self.telegraph_flash > 0 and self.state == "fight":
            alpha = int(150 * self.telegraph_flash)
            layer = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            layer.fill((255, 172, 48, alpha // 7))
            surface.blit(layer, (0, 0))
            pygame.draw.rect(surface, (255, 218, 115), (15, 94, WIDTH - 30, HEIGHT - 120), 3)
            pygame.draw.rect(surface, (255, 118, 42), (28, 107, WIDTH - 56, HEIGHT - 146), 1)
            text(surface, "PREPARE-SE", (WIDTH // 2, 105), 13, (255, 224, 151), center=True, bold=True)

        if self.damage_flash > 0:
            layer = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            layer.fill((255, 35, 75, int(115 * self.damage_flash)))
            surface.blit(layer, (0, 0))

        # A transformação reescreve o espaço: anéis, raios, vinheta e pressão.
        if self.cinema_flash > 0 and self.boss.phase == 2:
            progress = 1.0 - self.cinema_flash
            ease_value = progress * progress * (3.0 - 2.0 * progress)
            veil = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            veil.fill((145, 4, 43, int(120 * self.cinema_flash)))
            surface.blit(veil, (0, 0))
            radius = int(50 + ease_value * 340)
            pygame.draw.circle(surface, (255, 48, 105), center, radius, max(2, int(9 * self.cinema_flash)))
            pygame.draw.circle(surface, (255, 230, 157), center, max(12, radius - 35), 2)
            for index in range(24):
                angle = self.vortex_time * .8 + index * math.tau / 24
                start = Vector2(center) + Vector2(math.cos(angle), math.sin(angle) * .65) * 30
                end = Vector2(center) + Vector2(math.cos(angle), math.sin(angle) * .65) * (radius + 55)
                pygame.draw.line(surface, (255, 70, 122), start, end, 2)
            text(surface, "A ABISMO DESPERTA", (WIDTH // 2, 126), 32, (255, 231, 180), center=True, bold=True)
            text(surface, "A ARENA PERTENCE AO REI", (WIDTH // 2, 169), 17, (255, 104, 140), center=True, bold=True)

        # O quadro pulsa mesmo quando não há ataque: o domínio nunca desaparece.
        if self.pressure > 0 and self.state == "fight":
            alpha = int(85 * self.pressure)
            layer = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.rect(layer, (255, 30, 88, alpha), (7, 87, WIDTH - 14, HEIGHT - 112), 3)
            pygame.draw.line(layer, (255, 60, 110, alpha), (0, GROUND_Y - 4), (WIDTH, GROUND_Y - 4), 2)
            surface.blit(layer, (0, 0))

    def draw(self):
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
        self.draw_cinematic_layer(scene)
        shake = int(self.screen_shake * 22)
        offset = (random.randint(-shake, shake), random.randint(-shake, shake)) if shake else (0, 0)
        self.screen.fill((3, 5, 16))
        self.screen.blit(scene, offset)
        pygame.display.flip()


if __name__ == "__main__":
    CinematicGame().run()
