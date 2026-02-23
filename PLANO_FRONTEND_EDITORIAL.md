PLANO DE EXECUÇÃO FRONTEND: TERMINAL DE HARD NEWS B2B (RADAR.NEWS)

Contexto para o Agente de IA: Este documento dita a construção da SPA Frontend de um produto B2B (Radar de Pautas) vendido para redações de jornais e revistas focado em Hard News. O backend (FastAPI + Celery + Postgres) já providencia a inteligência: agrupamento de clusters (dedup.py), análise de deltas textuais (deltas.py) e uma taxonomia sólida de fontes (source_taxonomy.py).
O objetivo agora é construir uma Interface de Utilizador focada em performance extrema, acessibilidade visual (Light/Dark Mode), alta densidade de dados e velocidade de triagem baseada em teclado para a rotina caótica de um plantão.

1. Filosofia de Design, Referências e Stack (2026 State-of-the-Art)

Este sistema é uma ferramenta de trabalho intensivo. O utilizador final é um Editor ou Plantonista (pessoas focadas em texto e factos, sem background de TI) que lê centenas de ecrãs por hora.

Referências de UX: Bloomberg Terminal / Reuters Eikon (Densidade e Split-Screen), TweetDeck (Múltiplas colunas real-time), Linear / Superhuman (Velocidade e Atalhos de teclado "Inbox Zero").

Stack Obrigatória: React 18/19 (TypeScript), Vite, Tailwind CSS v3/v4, Zustand (estado global e atalhos), TanStack Query (cache de APIs), TanStack Virtualizer (obrigatório para renderizar listas longas de notícias sem quebrar o DOM), Radix UI / Shadcn UI (componentes acessíveis) e Lucide-react (Ícones).

1.1 Theming: Modo Coruja (Dark) e Modo Papel (Light)

A aplicação deve suportar next-themes (ou padrão Tailwind de classes dark:).

Modo Papel (Light): Fundos em zinc-50 a white. Textos em zinc-900. Focado no alto contraste para redações diurnas e redução de fadiga visual em ambientes muito iluminados.

Modo Coruja (Dark): Muted Dark Mode. Proibido preto absoluto (#000000). Fundos em zinc-950/zinc-900. Cores semânticas devem ser tons pastéis e opacos (Ex: boato usa text-orange-400 com bg-orange-950/20).

1.2 Glossário Editorial (Proibido jargões de TI na UI)

A interface não pode exibir termos de base de dados.

"Delta" $\rightarrow$ "Evolução" ou "Novos Detalhes".

"Cluster/Dedup" $\rightarrow$ "Cobertura Consolidada".

"Hydrating" $\rightarrow$ "A aguardar documento oficial...".

"Log/Audit" $\rightarrow$ "Cronologia do Facto".

2. A Estrutura Multi-Streams (Colunas Simultâneas)

O layout ocupa 100vh e 100vw, abandonando menus laterais obsoletos. O ecrã principal é dividido em colunas lado a lado.

A. Top Ticker (Barra de Plantão Extremo)

Fica fixa no topo (h-8). Tem um fundo de alerta de alto contraste (ex: vermelho escuro).

Rola horizontalmente (marquee CSS ou Framer Motion) apenas eventos com Score extremo (> 95) ou bandeiras críticas (ex: Presidência, STF, Polícia Federal).

B. Workspace e Modo Freeze (Anti-Jump)

Barra de ferramentas de topo contendo a Busca Global, estado da ligação SSE e um Botão "Pausar Fluxo" (Spacebar). Este botão congela a injeção de novos cards nas colunas para o editor poder ler sem o ecrã "pular". Novas notícias acumulam num badge de notificação temporal.

C. As Colunas Virtuais de Triagem

Cada coluna deve usar useVirtualizer para suportar scroll infinito de milhares de itens.

Coluna 1 (Firehose / Feed Geral): Agrupa os eventos HOT gerados pelo dedup.py.

Coluna 2 (Oceano Azul): Pautas onde a source_taxonomy.py detetou Diários Oficiais e PDFs, mas que a grande mídia ainda não cobriu.

Coluna 3 (Triagem/Monitorização): Pautas marcadas com "Snooze" ou na Watchlist do utilizador.

D. O "Card de Notícia" (Inbox Zero)

Design super denso. Fonte compacta, sem espaçamentos inúteis.

Bumping Factor: Se o backend envia um Delta (evolução) para uma notícia que já está na lista, o card não se duplica. Ele "salta" para o topo da coluna e o fundo pisca a amarelo (flash animation) durante 2 segundos. O delta (ex: "Número de vítimas subiu") aparece no meio do card.

Inbox Zero (Ações Hover): Ao passar o rato no card, revelam-se pequenos botões de atalho: [Pautar (Enviar para o CMS)], [Snooze] e [Descartar]. O editor despacha a pauta num clique.

3. O Fator UAU: O Dossiê Peek em Tela Dividida (Split-Screen)

Quando o editor clica num card (ou carrega em Enter), um Drawer (Modal lateral deslizando da direita) abre a ocupar entre 75% a 85% do ecrã. O modal divide-se em duas partes iguais (50/50).

Metade Esquerda (A Narrativa Editorial):

Acompanha o tema do utilizador (Light/Dark).

Manchete destacada e Resumo Editorial (Clean Text).

Cronologia (Timeline visual) baseada no first_seen_at das diversas fontes associadas.

Rodapé Fixo com a Action Bar (Botão Principal: Enviar para o CMS, e botões secundários).

Regra de Gating: Se a flag for HYDRATING, o botão principal fica disabled com um ícone a rodar. Se a flag for UNVERIFIED_VIRAL, o botão fica vermelho com aviso: Pautar Rascunho (Não Verificado).

Metade Direita (O Visualizador de Prova Oficial):

Inversão de Tema Permanente: Esta área simula a leitura de um documento de arquivo. Terá sempre o fundo claro (zinc-50) e texto escuro (zinc-800) e fonte serif ou monospace, independentemente do tema geral da aplicação. O contraste psicológico foca o cérebro: Isto é a prova original.

Evidence Highlighter: O backend envia as âncoras (ex: "CNPJ", "R$ 10.000"). A interface deve envolver exatamente essas palavras num elemento <mark> (marca-texto amarelo fluorescente, como o bg-yellow-300).

4. Teclado como Primeira Classe (Atalhos)

Um editor não tem tempo para arrastar o rato. Implementar cmdk (Command Palette).

J / K ou Setas: Navegar para cima e para baixo nos cards.

H / L ou Setas Laterais: Mudar de coluna ativa.

Espaço: Pausa/Retoma a entrada de novas notícias (Modo Freeze).

Enter: Abre o Dossiê Modal Peek do card selecionado.

P: Despacha a pauta focada para o CMS.

I: Ignora a pauta.

Cmd + K: Busca Global e troca rápida de vistas.

5. Roteiro de Execução (Sprints) para o Agente IA

Atue como Engenheiro Front-end Sénior e Especialista de UI/UX. Construa a SPA passo-a-passo. Pare após cada Sprint para eu rever o seu código. Não invente jargões.

Sprint 1 (Fundação, Theming e Layout Macro):
Configure o Vite, Tailwind (com suporte Light/Dark), Zustand. Crie a estrutura principal de Workspace contendo o Top Ticker animado, a Sidebar mínima e o contentor para as Colunas. Crie o "Theme Toggle" para garantir que o Modo Papel e o Modo Coruja funcionam perfeitamente. Entregue o código.

Sprint 2 (Colunas Virtuais e Cards Inteligentes):
Implemente as 3 Colunas principais. Atenção: Use obrigatoriamente @tanstack/react-virtual no contentor de listas para suportar centenas de itens sem lag. Crie o componente NewsCard com a mecânica de animação de "Bumping" e os botões rápidos no hover (Inbox Zero). Adicione o botão de Freeze (Pausa de feed) no header. Crie um Mock Data avançado. Entregue o código.

Sprint 3 (O Dossiê Peek em Split-Screen):
Construa o Modal lateral. Implemente o Split-Screen 50/50. Faça o lado esquerdo com a Cronologia (Timeline) e a Action Bar com Action Gating (bloqueio se status for HYDRATING). Crie o lado direito com o Evidence Highlighter, garantindo que tem um aspeto de "documento num fundo claro" em permanência, usando tags <mark>. Entregue o código.

Sprint 4 (Produtividade e Integração):
Implemente o cmdk para a Command Palette e adicione os atalhos de teclado (J/K para navegação de cards, P para pautar). Configure o skeleton do TanStack Query para consumo das APIs REST e gestão de Server-Sent Events (SSE). Entregue o código.

Responda apenas com: "Compreendido. Arquitetura Terminal Hard News B2B validada para 2026 (Alta Performance, Light/Dark Mode, Multi-Streams e Atalhos). A preparar a Fundação do Sprint 1."