import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useQuery } from "@tanstack/react-query";
import { NewsCard } from "./news-card";
import { fetchPlantao, fetchOceanoAzul } from "../api/client";
import type { HardNewsEvent } from "../api/client";
import { Loader2, AlertCircle } from "lucide-react";

interface ColumnProps {
    title: string;
    type: "PLANTAO" | "OCEANO_AZUL";
    isPaused: boolean;
    onEventClick: (id: number) => void;
}

export function StreamColumn({ title, type, isPaused, onEventClick }: ColumnProps) {
    const parentRef = useRef<HTMLDivElement>(null);

    // TanStack Query: Buscando eventos do Backend Real (FastAPI)
    const { data: events = [], isLoading, isError, refetch } = useQuery<HardNewsEvent[]>({
        queryKey: ["stream", type],
        queryFn: () => (type === "PLANTAO" ? fetchPlantao(50) : fetchOceanoAzul(50)),
        refetchInterval: isPaused ? false : 10000, // DB Polling até implementar SSE 100% no Ticker
    });

    // TanStack Virtualizer: Mantém alta performance com centenas de cards (descarrega o que tá fora da tela)
    const virtualizer = useVirtualizer({
        count: events.length,
        getScrollElement: () => parentRef.current,
        estimateSize: () => 180, // Tamanho base estimado do NewsCard
        overscan: 5,
    });

    // Mock de actions para essa Sprint
    const handlePautar = (id: number) => console.log("Pautar Evento", id);
    const handleAdiar = (id: number) => console.log("Adiar Evento", id);
    const handleDescartar = (id: number) => console.log("Descartar Evento", id);

    return (
        <div className="flex flex-col w-[350px] flex-shrink-0 bg-zinc-50 dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden relative shadow-sm">

            {/* Column Header Fixo */}
            <div className="h-12 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 flex items-center justify-between px-4 z-10 shrink-0">
                <h2 className="font-bold text-sm tracking-tight text-zinc-800 dark:text-zinc-100 uppercase">{title}</h2>
                <span className="text-xs bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 px-2 py-0.5 rounded font-mono">
                    {events.length}
                </span>
            </div>

            {isLoading && (
                <div className="flex flex-col items-center justify-center flex-1 text-zinc-400">
                    <Loader2 className="w-8 h-8 animate-spin mb-2" />
                    <span className="text-xs font-semibold">Carregando Fluxos...</span>
                </div>
            )}

            {isError && (
                <div className="flex flex-col items-center justify-center flex-1 text-zinc-400 p-4 text-center">
                    <AlertCircle className="w-8 h-8 text-red-400 mb-2" />
                    <span className="text-xs">Falha na conexão com a Fonte (Backend Indisponível).</span>
                    <button onClick={() => refetch()} className="mt-4 text-xs bg-zinc-200 dark:bg-zinc-800 px-3 py-1 rounded">
                        Tentar Novamente
                    </button>
                </div>
            )}

            {/* Viewport Virtualizado (Permite scroll de 10 mil itens a 60fps) */}
            {!isLoading && !isError && (
                <div ref={parentRef} className="flex-1 overflow-y-auto overflow-x-hidden p-2 scrollbar-thin">
                    <div
                        style={{
                            height: `${virtualizer.getTotalSize()}px`,
                            width: "100%",
                            position: "relative",
                        }}
                    >
                        {virtualizer.getVirtualItems().map((virtualItem) => {
                            const row = events[virtualItem.index];
                            return (
                                <div
                                    key={row.id}
                                    onClick={() => onEventClick(row.id)}
                                    style={{
                                        position: "absolute",
                                        top: 0,
                                        left: 0,
                                        width: "100%",
                                        height: `${virtualItem.size}px`,
                                        transform: `translateY(${virtualItem.start}px)`,
                                        paddingBottom: "8px", // Gap entre cards
                                    }}
                                >
                                    <NewsCard
                                        event={row}
                                        onPautar={handlePautar}
                                        onAdiar={handleAdiar}
                                        onDescartar={handleDescartar}
                                    />
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}
