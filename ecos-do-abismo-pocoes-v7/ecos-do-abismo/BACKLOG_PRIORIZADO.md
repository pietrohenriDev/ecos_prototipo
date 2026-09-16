+# Backlog priorizado
+
+Critério: **P1** é trabalho que melhora diretamente a diversão ou reduz risco de demo. Impacto, risco e esforço usam escala de 1 a 5, onde 5 é maior. A prioridade considera impacto alto, risco de produto e esforço baixo.
+
+| Ordem | Item | Impacto | Risco | Esforço | Status | Critério de aceite |
+|---:|---|---:|---:|---:|---|---|
+| 1 | Testar a demo vertical com 5 jogadores | 5 | 5 | 1 | Próximo | Cada jogador vence ou abandona o primeiro chefe com motivo registrado |
+| 2 | Balancear o primeiro chefe e os 3 padrões de ataque | 5 | 4 | 3 | Próximo | Jogador entende cada telegráfico e a taxa de vitória fica entre 30% e 60% |
+| 3 | Criar checkpoints entre fases e ao desbloquear guardião | 5 | 4 | 3 | Próximo | Morte não apaga progresso e reinício não gera estado inconsistente |
+| 4 | Adicionar telemetria local de mortes, dano e tempo por fase | 4 | 3 | 2 | Planejado | Um arquivo de sessão mostra causa da morte, fase e duração |
+| 5 | Implementar upgrades de poção, esquiva e ataque | 5 | 4 | 4 | Planejado | Cada upgrade muda uma decisão de combate, não só um número |
+| 6 | Testes automatizados de colisão, save e desbloqueio | 4 | 5 | 3 | Planejado | Casos de projétil rápido, escudo quebrado e save corrompido cobertos |
+| 7 | Melhorar acessibilidade: remapeamento, contraste e modo sem tremor | 4 | 3 | 3 | Planejado | Controles podem ser remapeados e efeitos visuais intensos podem ser reduzidos |
+| 8 | Dar assinatura mecânica única aos 9 guardiões | 5 | 3 | 6 | Planejado | Nenhum chefe depende apenas de trocar cor, vida ou velocidade |
+| 9 | Expandir narrativa com cenas curtas entre guardiões | 3 | 2 | 5 | Planejado | Cada vitória revela uma consequência para Lira e Noa em menos de 30 segundos |
+| 10 | Polimento de áudio, mixagem e feedback de impacto | 3 | 2 | 3 | Planejado | Ataque, dano, esquiva, escudo e fase têm sons distinguíveis |
+| 11 | Empacotar build reproduzível para Windows | 4 | 5 | 3 | Próximo | Pessoa sem Python instalado inicia a build e carrega o save |
+| 12 | Página de apresentação e vídeo curto de gameplay | 2 | 2 | 3 | Depois da demo | Vídeo mostra o loop principal em até 45 segundos |
+| 13 | Validar a finalização mecha com playtest focado em ritmo e emoção | 5 | 4 | 2 | Próximo | Jogadores entendem a entrada no mecha, sentem os impactos e vencem sem tela de loading |
+
+## Riscos de gestão
+
+- **Escopo inchado:** há 9 guardiões, 3 fases e múltiplos gêneros. Não criar novos chefes antes de validar o primeiro.
+- **Balanceamento invisível:** efeitos bonitos podem esconder ataques injustos. A telemetria e o playtest vêm antes de mais conteúdo.
+- **Build frágil:** Pygame é dependência crítica. A entrega precisa de uma build executável e um teste limpo em outra máquina.
+- **Progresso perdido:** save, checkpoints e desbloqueios devem ser tratados como sistema de produto, não detalhe de protótipo.
+
+## Regra de decisão
+
+Se uma tarefa não melhora **clareza**, **resposta do combate**, **retensão** ou **confiabilidade da build**, ela fica fora da próxima milestone.
