import { useState } from "react"
import { ThemeProvider } from "./components/theme-provider"
import { ThemeToggle } from "./components/theme-toggle"
import { StreamColumn } from "./components/stream-column"
import { PeekModal } from "./components/peek-modal"
import { CommandPalette } from "./components/command-palette"
import { SseProvider, useSSE } from "./providers/sse-provider"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Search, MonitorPlay } from "lucide-react"

const queryClient = new QueryClient();

// Header que reage ao SSE em tempo real
function TickerHeader() {
  const { latestEvent, isConnected } = useSSE();

  return (
    <div className={`h-8 flex items-center shrink-0 overflow-hidden relative transition-colors ${isConnected ? "bg-red-600" : "bg-zinc-600"}`}>
      <div className={`absolute inset-y-0 left-0 font-bold px-3 flex items-center z-10 shadow-md ${isConnected ? "bg-red-700 text-white" : "bg-zinc-700 text-zinc-300"}`}>
        {isConnected ? "PLANTÃO LIVE" : "OFFLINE"}
      </div>
      <div className="flex whitespace-nowrap overflow-hidden z-0">
        <div className="animate-[marquee_20s_linear_infinite] inline-block px-4 ml-32">
          <span className="font-semibold px-2 uppercase text-xs text-white">
            {latestEvent
              ? `[NOVA ATUALIZAÇÃO] ${latestEvent.summary}`
              : "[INFO] Conectado ao terminal de Hard News. Aguardando novos eventos do motor..."}
          </span>
        </div>
      </div>
    </div>
  )
}

function App() {
  const [isPaused, setIsPaused] = useState(false);
  const [activeEventId, setActiveEventId] = useState<number | null>(null);

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider defaultTheme="dark" storageKey="radar-theme">
        <SseProvider>
          <CommandPalette />
          <div className="flex flex-col h-screen w-full overflow-hidden bg-zinc-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-50">

            <TickerHeader />

            {/* B. HEADER */}
            <header className="h-14 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between px-4 shrink-0 bg-white dark:bg-zinc-900">
              <div className="flex items-center gap-4">
                <h1 className="font-bold text-lg tracking-tight flex items-center gap-2">
                  <MonitorPlay className="w-5 h-5 text-zinc-400 dark:text-zinc-500" />
                  Radar.News
                </h1>

                <div className="relative ml-4">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-zinc-500" />
                  <input
                    type="text"
                    placeholder="Busca Global (Cmd + K)"
                    className="h-9 w-[300px] rounded-md bg-zinc-100 dark:bg-zinc-800/50 pl-9 pr-4 text-sm outline-none focus:ring-1 focus:ring-zinc-400 focus:dark:ring-zinc-600 transition-shadow"
                  />
                </div>
              </div>

              <div className="flex items-center gap-2">
                <div className="flex items-center px-3 py-1 rounded bg-zinc-100 dark:bg-zinc-800 text-xs font-semibold mr-2 border border-zinc-200 dark:border-zinc-700">
                  <div className="w-2 h-2 rounded-full bg-green-500 mr-2 animate-pulse"></div>
                  API Conectada
                </div>

                <button
                  onClick={() => setIsPaused(!isPaused)}
                  className={`flex items-center gap-2 text-sm font-medium border px-3 py-1.5 rounded-md transition-colors ${isPaused
                    ? "bg-amber-100 border-amber-300 text-amber-800 dark:bg-amber-900/40 dark:border-amber-700 dark:text-amber-400"
                    : "border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-700"
                    }`}
                >
                  {isPaused ? "Fluxo Congelado" : "Pausar Fluxo"}
                  <kbd className="hidden sm:inline-block bg-black/10 dark:bg-white/10 text-xs px-1.5 rounded ml-1">Espaço</kbd>
                </button>
                <div className="w-px h-6 bg-zinc-200 dark:bg-zinc-800 mx-1"></div>
                <ThemeToggle />
              </div>
            </header>

            {/* C. MULTI-STREAMS E ESPAÇO DE TRABALHO */}
            <main className="flex-1 overflow-x-auto overflow-y-hidden flex p-3 gap-3">

              {/* Colunas Reais ligadas as Tasks */}
              <StreamColumn title="Plantão Urgente (Firehose)" type="PLANTAO" isPaused={isPaused} onEventClick={setActiveEventId} />
              <StreamColumn title="Furos & Oceano Azul" type="OCEANO_AZUL" isPaused={isPaused} onEventClick={setActiveEventId} />

              <div className="w-[350px] flex-shrink-0 border-2 border-dashed border-zinc-200 dark:border-zinc-800 rounded-lg flex flex-col items-center justify-center text-zinc-400 dark:text-zinc-600 bg-zinc-50/50 dark:bg-zinc-950/50">
                <span className="text-sm font-semibold">+ Adicionar Coluna (Ex: Monitoramento)</span>
              </div>

            </main>
          </div>

          {/* Modal de Detalhes (Renderizado sobre tudo quando activeEventId != null) */}
          <PeekModal eventId={activeEventId} onClose={() => setActiveEventId(null)} />

        </SseProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )
}

export default App
