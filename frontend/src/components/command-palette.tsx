import { useEffect, useState } from "react"
import { Command } from "cmdk"
import { Search, Hash, MonitorPlay, Zap } from "lucide-react"

export function CommandPalette() {
    const [open, setOpen] = useState(false)

    // Toggle Command Palette (CMD+K / CTRL+K)
    useEffect(() => {
        const down = (e: KeyboardEvent) => {
            if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                setOpen((open) => !open)
            }
        }

        document.addEventListener("keydown", down)
        return () => document.removeEventListener("keydown", down)
    }, [])

    if (!open) return null

    return (
        <div className="fixed inset-0 z-[100] bg-black/40 backdrop-blur-sm flex items-start justify-center pt-[15vh]">
            <div className="w-full max-w-[600px] bg-white dark:bg-zinc-900 rounded-xl shadow-2xl border border-zinc-200 dark:border-zinc-800 overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-200">

                <Command label="Command Palette" className="flex flex-col w-full bg-transparent">
                    <div className="flex items-center border-b border-zinc-100 dark:border-zinc-800 px-4">
                        <Search className="w-5 h-5 text-zinc-400 shrink-0" />
                        <Command.Input
                            autoFocus
                            placeholder="Buscar notícia ou escolher ação..."
                            className="flex-1 bg-transparent border-0 outline-none h-14 px-3 text-zinc-900 dark:text-zinc-100 font-medium placeholder:text-zinc-400"
                        />
                        <button onClick={() => setOpen(false)} className="p-1 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-500 text-xs font-mono shrink-0 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition">
                            ESC
                        </button>
                    </div>

                    <Command.List className="max-h-[300px] overflow-y-auto p-2 scrollbar-thin">
                        <Command.Empty className="py-6 text-center text-sm text-zinc-500">
                            Nenhuma ação encontrada.
                        </Command.Empty>

                        <Command.Group heading="Ações Globais" className="text-xs font-semibold text-zinc-500 px-2 py-2">
                            <Command.Item
                                onSelect={() => setOpen(false)}
                                className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 rounded-md cursor-pointer hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors mt-1"
                            >
                                <MonitorPlay className="w-4 h-4 text-zinc-400" />
                                <span>Pausar fluxo de notícias</span>
                                <kbd className="ml-auto bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 px-1.5 rounded text-xs font-mono">Espaço</kbd>
                            </Command.Item>
                            <Command.Item
                                onSelect={() => setOpen(false)}
                                className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 rounded-md cursor-pointer hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors mt-1"
                            >
                                <Zap className="w-4 h-4 text-zinc-400" />
                                <span>Adicionar coluna de Inteligência</span>
                            </Command.Item>
                        </Command.Group>

                        <Command.Separator className="h-px bg-zinc-100 dark:bg-zinc-800 my-1" />

                        <Command.Group heading="Busca Rápida de Entidades" className="text-xs font-semibold text-zinc-500 px-2 py-2">
                            <Command.Item
                                onSelect={() => setOpen(false)}
                                className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 rounded-md cursor-pointer hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors mt-1"
                            >
                                <Hash className="w-4 h-4 text-blue-400" />
                                <span>#STF</span>
                            </Command.Item>
                            <Command.Item
                                onSelect={() => setOpen(false)}
                                className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 rounded-md cursor-pointer hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors mt-1"
                            >
                                <Hash className="w-4 h-4 text-blue-400" />
                                <span>#Fazenda</span>
                            </Command.Item>
                        </Command.Group>

                    </Command.List>
                </Command>

            </div>
        </div>
    )
}
