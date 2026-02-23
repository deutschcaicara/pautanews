# Tarefas de Desenvolvimento Frontend (Radar.News)

## Objetivo
Criar a interface (SPA) para jornalistas e editores monitorarem Hard News em tempo real, baseada em colunas (estilo TweetDeck) com alta densidade, performance e foco total em produtividade via teclado.

## Sprint 1: Fundação, Theming e Layout Macro
- [ ] Inicializar projeto React + Vite com TypeScript (`/home/diego/pautanews/frontend`)
- [ ] Instalar dependências base: Tailwind CSS, Zustand, React Router, Lucide-react
- [ ] Configurar roteamento básico
- [ ] Configurar layout base (100vh/100vw sem scroll global lateral)
- [ ] Implementar Theming: Modo Papel (Light) e Modo Coruja (Dark)
- [ ] Criar estrutura do "Top Ticker" (Barra de Plantão Extremo)
- [ ] Criar Sidebar mínima (Navegação principal)

## Sprint 2: Colunas Virtuais e Cards de Notícia
- [ ] Configurar `@tanstack/react-virtual` para listas longas
- [ ] Criar o componente de Coluna (Stream)
- [ ] Implementar estrutura das 3 colunas padrão (Plantão, Oceano Azul, Monitoramento)
- [ ] Criar componente `NewsCard` (alta densidade)
- [ ] Implementar botões de ação rápida no card ("Pautar", "Adiar", "Descartar") - *sem usar termos técnicos em inglês*
- [ ] Construir API Client (Networking) para buscar dados Reais de `/api/plantao` e `/api/oceano-azul`.
- [ ] Lógica visual de "Bumping" (card volta pro topo e pisca ao receber atualização)
- [ ] Implementar botão de "Pausar Fluxo" (Freeze mode) na barra superior

## Sprint 3: O Dossiê Peek (Split-Screen)
- [x] Criar componente Drawer Modal lateral ocupando 75%-85% da tela
- [x] Construir layout Split-Screen 50/50 do dossiê
- [x] Lado Esquerdo: Manchete, Resumo Editorial, Cronologia (Timeline - consumindo `/api/events/{id}/state-history`) e Área de Ação (POST `/api/cms/draft/{id}`).
- [x] Action Gating: Desabilitar botões se `status == 'HYDRATING'`. Se `flags_json` contiver `UNVERIFIED_VIRAL`, mudar cor do botão para vermelho.
- [x] Lado Direito: Visualizador de Documento Oficial focado em contraste claro. Embutir os textos brutos das Fontes Oficiais.
- [ ] Implementar Evidence Highlighter (Destacar termos/valores com `<mark>` combinando `event.anchors` com o texto).

## Sprint 4: Redes (SSE), Atalhos e Produtividade (Teclado)
- [x] Configurar conexão Server-Sent Events (SSE) nativa em `/events/stream` via React `useEffect` ou TanStack.
- [x] Implementar API Clients (`/api/plantao`, `/api/oceano-azul`, POST `/api/events/{event_id}/feedback` para Ignorar/Snooze).
- [x] Implementar Command Palette (`cmdk` ou similar)
- [x] Adicionar atalhos globais de navegação (J/K para subir/descer cards, Setas laterais para trocar de coluna)
- [x] Adicionar atalhos de ação (Espaço para Pausar fluxo, Enter para abrir Dossiê, P para Exportar p/ CMS, I para Enviar Feedback de Ignorar).
