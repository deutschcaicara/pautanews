import { useState, useEffect } from "react";
import { formatDistanceToNow } from "date-fns";
import { ptBR } from "date-fns/locale";
import type { HardNewsEvent, EventAnchor } from "../api/client";
import { AlertCircle, Clock, FastForward, CheckSquare, XSquare, Clock4 } from "lucide-react";
import clsx from "clsx";

interface NewsCardProps {
    event: HardNewsEvent;
    onPautar: (id: number) => void;
    onAdiar: (id: number) => void;
    onDescartar: (id: number) => void;
}

export function NewsCard({ event, onPautar, onAdiar, onDescartar }: NewsCardProps) {
    const [bumping, setBumping] = useState(false);
    const [lastUpdate, setLastUpdate] = useState(event.updated_at || event.last_seen_at);

    // Simulando o "Efeito Bumping" se a prop `last_seen_at` mudar (SSE injetará novas datas)
    useEffect(() => {
        if ((event.updated_at || event.last_seen_at) !== lastUpdate) {
            setBumping(true);
            setLastUpdate(event.updated_at || event.last_seen_at);
            const timer = setTimeout(() => setBumping(false), 2000); // Pisca por 2s
            return () => clearTimeout(timer);
        }
    }, [event.last_seen_at, event.updated_at, lastUpdate]);

    const timeAgo = formatDistanceToNow(new Date(event.last_seen_at || event.created_at), {
        addSuffix: true,
        locale: ptBR,
    });

    const isHot = event.status === "HOT" || event.score > 90;
    const isHydrating = event.status === "HYDRATING";

    const getLaneColor = (lane?: string | null) => {
        if (!lane) return "bg-zinc-200 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400";
        const lower = lane.toLowerCase();
        if (lower === "politica") return "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400";
        if (lower === "economia") return "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400";
        if (lower === "justica" || lower === "policia") return "bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-400";
        return "bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300";
    };

    const hasViralRisk = event.flags_json?.UNVERIFIED_VIRAL === true;

    // Render Anchors (CNPJs, Valores)
    const renderAnchors = (anchors: EventAnchor[]) => {
        // Pegar apenas os 3 primeiros para não poluir
        const unique = Array.from(new Set(anchors.map((a) => `${a.type}:${a.value}`))).slice(0, 3);
        return unique.map((u, i) => {
            const [type, val] = u.split(":");
            return (
                <span key={i} className="text-[10px] font-mono bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 whitespace-nowrap overflow-hidden text-ellipsis max-w-[100px]">
                    {type}: {val}
                </span>
            );
        });
    };

    return (
        <div
            className={clsx(
                "group relative flex flex-col p-3 rounded-lg border text-sm transition-all duration-300 cursor-pointer min-h-[140px]",
                // Status classes
                isHot ? "border-red-500/50 dark:border-red-500/40 shadow-sm" : "border-zinc-200 dark:border-zinc-800",
                // Bumping flash animation
                bumping ? "bg-yellow-100 dark:bg-yellow-900/30 ring-2 ring-yellow-400" : "bg-white dark:bg-zinc-900 hover:border-zinc-300 dark:hover:border-zinc-700"
            )}
        >
            {/* Header do Card */}
            <div className="flex justify-between items-start mb-2">
                <div className="flex gap-2 items-center">
                    <span className={clsx("text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-sm tracking-wider", getLaneColor(event.lane))}>
                        {event.lane || "GERAL"}
                    </span>
                    <span className="text-xs text-zinc-500 flex items-center gap-1">
                        <Clock className="w-3 h-3" /> {timeAgo}
                    </span>
                </div>

                {/* Termômetro (Score) */}
                <div className={clsx(
                    "font-bold text-xs px-1.5 py-0.5 rounded flex items-center gap-1",
                    event.score > 80 ? "bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-400" : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-400"
                )}>
                    Score: {Math.round(event.score)}
                </div>
            </div>

            {/* Manchete Consolidada */}
            <h3 className="font-semibold text-zinc-900 dark:text-zinc-100 leading-snug mb-2 line-clamp-3">
                {event.summary || "Buscando consolidação dos fatos..."}
            </h3>

            {/* Metadata e Provas Rápidas (Âncoras) */}
            <div className="flex flex-wrap gap-1 mt-auto">
                {renderAnchors(event.anchors || [])}
            </div>

            {/* Footer do Card com Alertas */}
            <div className="flex justify-between items-center mt-3 pt-2 border-t border-zinc-100 dark:border-zinc-800">
                <div className="flex gap-3 text-xs text-zinc-500 font-medium">
                    <span title="Fontes agrupadas neste fato">{event.source_count} Fontes</span>
                    <span title="Deltas documentais rastreados" className="flex items-center gap-1">
                        <FastForward className="w-3 h-3" /> {event.doc_count}
                    </span>
                </div>

                {/* Alertas Críticos de Gating Visual */}
                {isHydrating && (
                    <span className="text-[10px] flex items-center font-bold text-orange-600 dark:text-orange-400 uppercase bg-orange-50 dark:bg-orange-950/30 px-1.5 py-0.5 rounded animate-pulse">
                        A aguardar Dok Oficial...
                    </span>
                )}
                {hasViralRisk && (
                    <span className="text-[10px] flex items-center font-bold text-red-600 dark:text-red-400 uppercase bg-red-50 dark:bg-red-950/30 px-1.5 py-0.5 rounded">
                        <AlertCircle className="w-3 h-3 mr-1" /> Risco Boato
                    </span>
                )}
            </div>

            {/* 
        INBOX ZERO HOVER ACTIONS 
        Aparecem apenas quando o mouse passa por cima (group-hover). 
        Botões estritamente funcionais. 
      */}
            <div className="absolute inset-0 bg-white/95 dark:bg-zinc-900/95 backdrop-blur-sm rounded-lg opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2 pointer-events-none group-hover:pointer-events-auto">
                <button
                    onClick={(e) => { e.stopPropagation(); onPautar(event.id); }}
                    className="flex flex-col items-center justify-center bg-green-100 hover:bg-green-200 text-green-700 dark:bg-green-900/40 dark:hover:bg-green-800/60 dark:text-green-400 p-2 rounded w-20 h-20 transition-colors shadow-sm"
                >
                    <CheckSquare className="w-6 h-6 mb-1" />
                    <span className="text-xs font-bold">Pautar</span>
                </button>

                <button
                    onClick={(e) => { e.stopPropagation(); onAdiar(event.id); }}
                    className="flex flex-col items-center justify-center bg-zinc-100 hover:bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:hover:bg-zinc-700 dark:text-zinc-300 p-2 rounded w-20 h-20 transition-colors"
                >
                    <Clock4 className="w-6 h-6 mb-1" />
                    <span className="text-xs font-semibold">Adiar</span>
                </button>

                <button
                    onClick={(e) => { e.stopPropagation(); onDescartar(event.id); }}
                    className="flex flex-col items-center justify-center bg-red-50 hover:bg-red-100 text-red-600 dark:bg-red-950/30 dark:hover:bg-red-900/50 dark:text-red-400 p-2 rounded w-20 h-20 transition-colors"
                >
                    <XSquare className="w-6 h-6 mb-1" />
                    <span className="text-xs font-semibold">Descartar</span>
                </button>
            </div>
        </div>
    );
}
