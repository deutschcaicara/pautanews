import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchEventDetail, sendToCMS, expressFeedback } from "../api/client";
import { X, ExternalLink, Loader2, CheckSquare, XSquare, Clock4, AlertTriangle, FileText } from "lucide-react";

interface PeekModalProps {
    eventId: number | null;
    onClose: () => void;
}

export function PeekModal({ eventId, onClose }: PeekModalProps) {

    const { data: event, isLoading, error } = useQuery({
        queryKey: ["event", eventId],
        queryFn: () => fetchEventDetail(eventId!),
        enabled: !!eventId, // Só roda se tivermos ID
    });

    // Hotkey ESC para fechar
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [onClose]);

    if (!eventId) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-end bg-black/60 backdrop-blur-sm transition-all duration-300">

            {/* 
        Container Principal: Split-Screen ocupando 90% da tela (Drawer Lateral)
      */}
            <div className="w-full sm:w-[90vw] max-w-7xl h-full sm:h-[95vh] bg-zinc-50 dark:bg-zinc-950 sm:rounded-l-2xl shadow-2xl flex flex-col sm:flex-row overflow-hidden animate-in slide-in-from-right duration-300">

                {/* =========================================
            LADO ESQUERDO: INTELIGÊNCIA EDITORIAL
        ========================================= */}
                <div className="w-full sm:w-[45%] h-full flex flex-col border-r border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 relative">

                    {/* Header Esquerdo (Ações Rápidas & Voltar) */}
                    <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-zinc-800 shrink-0">
                        <button onClick={onClose} className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-md text-zinc-500 transition-colors" title="Fechar (ESC)">
                            <X className="w-5 h-5" />
                        </button>

                        <div className="flex gap-2">
                            <button
                                onClick={() => expressFeedback(eventId, "IGNORE").then(onClose)}
                                disabled={isLoading}
                                className="px-3 py-1.5 text-sm font-semibold text-zinc-600 bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700 rounded-md transition-colors flex items-center gap-2 disabled:opacity-50"
                            >
                                <XSquare className="w-4 h-4" />
                                Descartar
                            </button>
                            <button
                                onClick={() => sendToCMS(eventId).then(onClose)}
                                disabled={isLoading || event?.status === "HYDRATING"}
                                className="px-4 py-1.5 text-sm font-bold text-white bg-green-600 hover:bg-green-700 rounded-md transition-colors flex items-center gap-2 shadow-sm disabled:opacity-50 disabled:bg-zinc-400"
                            >
                                <CheckSquare className="w-4 h-4" />
                                {event?.status === "HYDRATING" ? "Aguardando Fonte..." : "Pautar Notícia"}
                            </button>
                        </div>
                    </div>

                    {/* Área de Risco / Alerts */}
                    {event?.flags_json?.UNVERIFIED_VIRAL && (
                        <div className="mx-4 mt-4 bg-red-100 dark:bg-red-950/40 border border-red-300 dark:border-red-900 text-red-800 dark:text-red-400 p-3 rounded-lg flex gap-3 text-sm shrink-0">
                            <AlertTriangle className="w-5 h-5 shrink-0" />
                            <p><strong>Atenção (Risco Alto):</strong> Notícia viral de rede social sem lastro em domínio confiável identificado. Verifique a fonte à direita.</p>
                        </div>
                    )}

                    {isLoading ? (
                        <div className="flex-1 flex flex-col items-center justify-center text-zinc-500">
                            <Loader2 className="w-8 h-8 animate-spin mb-4" />
                            <p className="font-semibold">Gerando Dossiê...</p>
                        </div>
                    ) : error ? (
                        <div className="flex-1 flex items-center justify-center p-6 text-red-500 text-center">
                            <p>Erro ao carregar o dossiê. O evento falhou ou não existe.</p>
                        </div>
                    ) : (
                        <div className="flex-1 overflow-y-auto p-6 scrollbar-thin flex flex-col gap-6">

                            {/* Manchete Editorial Central */}
                            <div>
                                <span className="text-xs font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 px-2 py-1 rounded inline-block mb-3">
                                    {event.lane || "Geral"}
                                </span>
                                <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100 leading-tight mb-4">
                                    {event.summary || "Título indisponível"}
                                </h1>

                                <div className="flex gap-4 text-sm text-zinc-500 font-medium">
                                    <span className="flex items-center gap-1"><FileText className="w-4 h-4" /> {event.doc_count || 1} Docs Agrupados</span>
                                    <span className="flex items-center gap-1"><Clock4 className="w-4 h-4" /> Origem: {new Date(event.created_at).toLocaleTimeString("pt-BR")}</span>
                                    <div className="px-2 bg-zinc-100 dark:bg-zinc-800 rounded font-mono text-zinc-700 dark:text-zinc-300">Score: {event.score ? Math.round(event.score) : 0}</div>
                                </div>
                            </div>

                            {/* Linha do Tempo da Pauta (Timeline) */}
                            <div className="flex flex-col gap-4 mt-4">
                                <h3 className="text-sm font-bold uppercase text-zinc-400 dark:text-zinc-500 border-b border-zinc-200 dark:border-zinc-800 pb-2">
                                    Evolução do Fato (Plantão)
                                </h3>

                                {/* 
                  TODO: Consumir evento real event.state_history / docs. 
                  Criando mock visual nativo estático pro layout (Sem lib)
                */}
                                <div className="relative pl-4 border-l-2 border-zinc-200 dark:border-zinc-800 flex flex-col gap-6 w-full">
                                    <div className="relative">
                                        <span className="absolute -left-[21px] top-1 w-3 h-3 rounded-full bg-red-500 ring-4 ring-white dark:ring-zinc-900" />
                                        <p className="text-xs text-zinc-500 font-mono mb-1">AGORA</p>
                                        <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">O robô sugeriu a Pauta baseado no cruzamento de 3 sites.</p>
                                    </div>

                                    <div className="relative opacity-70">
                                        <span className="absolute -left-[21px] top-1 w-3 h-3 rounded-full bg-zinc-300 dark:bg-zinc-700 ring-4 ring-white dark:ring-zinc-900" />
                                        <p className="text-xs text-zinc-500 font-mono mb-1">Há 15 minutos</p>
                                        <p className="text-sm text-zinc-700 dark:text-zinc-300">Primeira Citação Encontrada no Diário Oficial. Baixando conteúdo...</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* =========================================
            LADO DIREITO: TEXTO BRUTO / PROVA DE FATO
        ========================================= */}
                <div className="w-full sm:w-[55%] h-full bg-white text-zinc-900 flex flex-col relative">

                    <div className="h-12 bg-zinc-100 border-b border-zinc-200 flex items-center justify-between px-4 shrink-0">
                        <div className="flex items-center gap-2">
                            <FileText className="w-4 h-4 text-zinc-400" />
                            <span className="text-sm font-bold text-zinc-700">Fonte Primária (Documento Isolado)</span>
                        </div>

                        <button className="flex items-center gap-2 text-xs font-semibold text-blue-600 hover:text-blue-800 transition-colors">
                            Ver Original <ExternalLink className="w-3 h-3" />
                        </button>
                    </div>

                    {/* Área de Visualização do Iframe/Extrato do texto nativamente Limpo e Claro (Modo Leitura) */}
                    <div className="flex-1 p-8 overflow-y-auto font-serif text-lg leading-relaxed text-zinc-800 prose prose-zinc max-w-none">
                        {isLoading ? (
                            <div className="flex w-full h-full items-center justify-center">
                                <span className="text-zinc-400 font-sans text-sm">Carregando Prova...</span>
                            </div>
                        ) : (
                            <article>
                                {event?.anchors && event.anchors.length > 0 ? (
                                    <div>
                                        <p className="mb-4 text-sm text-zinc-500 font-sans border-b pb-2">
                                            Foram encontradas {event.anchors.length} evidências extraídas pelo motor NLP.
                                        </p>

                                        {/* Simulação de extrato bruto do CMS com Regex Replace Nativo (Evidence Highlighter) */}
                                        <div className="space-y-4">
                                            <p>
                                                (Extrato Primário da Fonte - O texto abaixo contêm as extrações faturais).
                                            </p>

                                            <p className="whitespace-pre-wrap leading-relaxed py-2">
                                                {(() => {
                                                    // Texto Base Falso para demonstração até rota real retornar 'clean_text' no detalhe
                                                    let text = `A medida provisória que altera as diretrizes do fundo partidário foi publicada hoje. O texto indica que R$ 4.5 Bilhões poderão ser realocados se as prefeituras não enviarem a contrapartida.`;

                                                    // Highlight dinâmico via replace (substituindo textos por JSX) 
                                                    // *Nota: uma implementação real mais robusta usaria dompurify/html-react-parser
                                                    event.anchors.forEach((anchor: { value: string }) => {
                                                        if (text.includes(anchor.value)) {
                                                            const regex = new RegExp(anchor.value, 'g');
                                                            // Marca as palavras encontradas
                                                            text = text.replace(regex, `@@MARK@@${anchor.value}@@ENDMARK@@`);
                                                        }
                                                    });

                                                    return text.split('@@MARK@@').map((part, i) => {
                                                        if (part.includes('@@ENDMARK@@')) {
                                                            const [marked, rest] = part.split('@@ENDMARK@@');
                                                            return (
                                                                <span key={i}>
                                                                    <mark className="bg-yellow-200 px-1 rounded text-zinc-900 border border-yellow-400 font-bold">{marked}</mark>
                                                                    {rest}
                                                                </span>
                                                            );
                                                        }
                                                        return <span key={i}>{part}</span>;
                                                    });

                                                })()}
                                            </p>
                                        </div>
                                    </div>
                                ) : (
                                    <p>Texto original não possui dados estruturados consolidados.</p>
                                )}
                            </article>
                        )}
                    </div>

                </div>

            </div>
        </div>
    );
}
