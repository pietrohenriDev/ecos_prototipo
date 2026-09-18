# Ecos do Abismo — Demo Vertical

## Direção desta versão

Esta branch concentra a experiência em um único confronto: **Rei do Abismo**.
O objetivo é provar o núcleo do jogo antes de expandir o Panteão.

- uma arena desenhada para leitura e posicionamento;
- duas fases com padrões diferentes;
- telegráficos claros antes de cada golpe;
- esquiva com invulnerabilidade curta;
- hit-stop, screen shake, shockwaves, afterimages e partículas direcionais;
- transformação com ruptura visual da arena;
- vitória e derrota reiniciáveis sem estado de teste.

## Executar no Windows

```powershell
py -3 -m pip install pygame
py -3 main.py
```

## Controles

- **A/D** ou setas: mover
- **Espaço/W/↑**: pular, com pulo duplo
- **J/X**: atacar
- **Shift**: esquivar
- **R**: reiniciar após vencer ou perder
- **Esc**: sair

## Critério de qualidade

A demo deve ser julgada pelo ritmo do combate: o jogador precisa reconhecer o telegráfico, reagir, encontrar uma janela de ataque e sentir cada impacto. Novos chefes só entram depois que este confronto estiver divertido em playtest.
