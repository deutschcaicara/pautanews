import { useEffect, useState, createContext, useContext } from 'react';

// Contexto do SSE (Streaming via Push)
interface SseContextType {
    latestEvent: any | null;
    isConnected: boolean;
}

const SseContext = createContext<SseContextType>({ latestEvent: null, isConnected: false });

export const useSSE = () => useContext(SseContext);

export function SseProvider({ children }: { children: React.ReactNode }) {
    const [latestEvent, setLatestEvent] = useState<any | null>(null);
    const [isConnected, setIsConnected] = useState(false);

    useEffect(() => {
        // Escutando Server-Sent Events nativo
        const eventSource = new EventSource('http://localhost:8000/api/events/stream');

        eventSource.onopen = () => setIsConnected(true);

        eventSource.onmessage = (event) => {
            try {
                const parsed = JSON.parse(event.data);
                // Se for evento util que deve dar bump nas colunas
                if (parsed.type === "new_event" || parsed.type === "update") {
                    setLatestEvent(parsed.payload);
                }
            } catch (e) {
                console.error("SSE parse erro:", e);
            }
        };

        eventSource.onerror = () => {
            setIsConnected(false);
            eventSource.close();

            // Tentativa de reconexão boba (fallback)
            setTimeout(() => {
                setIsConnected(false); // Força retrigger do hook indiretamente
            }, 5000);
        };

        return () => {
            eventSource.close();
        };
    }, []);

    return (
        <SseContext.Provider value={{ latestEvent, isConnected }}>
            {children}
        </SseContext.Provider>
    )
}
