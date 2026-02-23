import axios from 'axios';

// URL do Backend FastAPI
const API_BASE_URL = 'http://localhost:8000/api';

export const apiClient = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Tipos base para o Frontend espelhando o Backend Event
export interface EventAnchor {
    type: string;
    value: string;
}

export interface HardNewsEvent {
    id: number;
    status: string;
    summary: string | null;
    lane: string | null;
    score: number;
    score_oceano_azul: number | null;
    created_at: string;
    updated_at?: string;
    last_seen_at: string;
    flags_json: Record<string, any> | null;
    anchors: EventAnchor[];
    doc_count: number;
    source_count: number;
}

// Calls Reais
export const fetchPlantao = async (limit = 30): Promise<HardNewsEvent[]> => {
    const { data } = await apiClient.get<HardNewsEvent[]>('/plantao', { params: { limit } });
    return data;
};

export const fetchOceanoAzul = async (limit = 30): Promise<HardNewsEvent[]> => {
    const { data } = await apiClient.get<HardNewsEvent[]>('/oceano-azul', { params: { limit } });
    return data;
};

// Detalhe Completo do Evento (Usado no Modal)
export const fetchEventDetail = async (eventId: number) => {
    // API Route simulada baseado em \`main.py\` padrão para items
    const { data } = await apiClient.get(`/events/${eventId}`);
    return data;
};

// Actions (CTAs)
export const sendToCMS = async (eventId: number) => {
    const { data } = await apiClient.post(`/cms/draft/${eventId}`);
    return data;
};

// Feedback Actions -> Ignorar/Snooze
export const expressFeedback = async (eventId: number, action: 'SNOOZE' | 'IGNORE' | 'NOT_NEWS') => {
    const { data } = await apiClient.post(`/events/${eventId}/feedback`, { action });
    return data;
};
