# Ecos do Abismo - Panteão

## Windows

Extraia tudo na mesma pasta e instale uma vez:

```powershell
py -3 -m pip install pygame
```

Execute `run_game.bat` ou `py -3 main.py`.

## Pacote desta versão

- Esquiva curta com Shift, invulnerabilidade durante o movimento, cooldown e rastro visual.
- Hit-stop curto em acertos para dar peso ao combate.
- Feedback explícito de impacto, dano recebido e ataque telegrafado.
- HUD mostra o estado da esquiva e mantém a leitura de vida e escudo.
- Dois novos guardiões: Serafim da Brasa e Arconte do Último Voto.
- O Arconte tem uma finalização em tempo real: Lira entra no Mecha do Voto e o jogador precisa golpear em sequência para quebrar o núcleo.
- O build de teste deixa os 11 guardiões desbloqueados no menu.
- A finalização foi ajustada para teste: o Arconte tem 720 de vida no Mecha, 36 impactos, 20 segundos e entra em execução aos 12%.
- Raios, beams e círculos possuem telegráfico: ficar parado é punido, andar antes do disparo evita o dano.
- Aos 12% de vida, a arena vira uma perspectiva 3D e pede uma tecla para o golpe que lança o guardião ao sol.

- As fases de nave agora têm três poções visíveis em posições diferentes da arena. Elas flutuam, brilham e recuperam 40% da vida quando Lira está ferida.
- O dano da nave foi reforçado com colisão varrida para raios, tiros verticais, ondas, anéis e tubarões. Projéteis rápidos não atravessam mais a personagem.
- Quando um tiro acerta, o jogo mostra se o escudo absorveu o impacto ou se Lira recebeu dano real.
- O HUD da nave mostra a vida e o escudo da Lira, e as colisões continuam deixando sangue, marcas e partículas.
- Tudo continua compatível com Pygame 2.6.1 no Windows.

## Controles

- Nave vertical: A/D e W/S ou setas movem, Espaço atira rajadas triplas.
- Normal: A/D ou setas movem, Espaço/W/↑ pula, J/X ataca.
- Normal: Shift faz uma esquiva horizontal com cooldown.
- QTE: Espaço, J ou X repetidamente.
- Finalização do Arconte: pressione Espaço, J ou X rapidamente durante a Ascensão Final.
- M silencia, -/+ ajustam volume, R reinicia, Esc volta ao Panteão.

## Próximo passo

O plano priorizado está em `BACKLOG_PRIORIZADO.md`. A regra de escopo é simples: primeiro tornar o primeiro chefe divertido e legível, depois expandir conteúdo.
