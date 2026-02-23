# Análise do Backend (pautanews vs news legado)

Esta análise detalha a situação do backend atual (`/home/diego/pautanews`) em comparação com o projeto legado (`/home/diego/news`) e atesta a capacidade técnica de suportar a visão de "Plantão de Hard News".

## 1. O que o Backend Atual (`pautanews`) já faz muito bem
Ao analisar a pasta `/home/diego/pautanews/backend/app`, foi constatado que a arquitetura moderna atende perfeitamente à necessidade de velocidade e escala de um Radar de Pautas Quentes:
- **Assincronismo e Velocidade**: O uso de Celery (`celery_app.py`, `workers/`) permite que a captação de notícias e extração de PDFs (Workers de OCR/Integração) aconteça de forma paralela sem travar o sistema.
- **Deduplicação e Agrupamento (Clusters)**: Os módulos `dedup.py`, `merge_service.py` e `split_service.py` são fundamentais para pegar 20 notícias sobre o mesmo assalto e juntá-las num único evento na tela do jornalista.
- **Evolução de Fatos (Deltas)**: O módulo `deltas.py` já estrutura a lógica de perceber que uma informação mudou de ontem para hoje (ex: número de vítimas mudou).
- **Integração com o Publicador (CMS)**: O módulo `cms.py` garante o botão de "Criar Pauta no CMS" descrito no frontend.

## 2. O que resgatamos do Legado (`news`)
Embora o backend atual seja sólido estruturalmente, o projeto legado tinha a **"Inteligência Jornalística"** crua. Nós integramos dois motores essenciais para que a ferramenta entenda o que é "quente":
1. **Taxonomia de Fontes (`source_taxonomy.py`)**: Sem isso, o Radar trataria o G1 e um blog de bairro com o mesmo peso. Esse módulo recém-módulo ensina ao sistema quem é Tier 1, o que é Diário Oficial e o que é mídia independente, influenciando diretamente o `scoring`.
2. **Similaridade de Texto (`text_similarity.py`)**: Um algoritmo de NLP forte (SimHash) trazido do legado que melhora a forma como o `dedup.py` identifica se dois parágrafos estão falando do mesmo "Furo" ou não.

## 3. Conclusão da Análise
O backend de `/home/diego/pautanews` está **100% aderente** às necessidades de um Plantão Hard News. 
- **O sistema sabe pegar o que é quente?** Sim. O motor de `scoring` (somado à recém-trazida Taxonomia) é feito para elevar notas de fatos que são confirmados por fontes Tier 1 em pouco tempo.
- **O sistema suporta a UI/UX prática?** Sim. A UI baseia-se num sistema de Websockets/Polling de eventos agregados. O endpoint já entrega o cluster mastigado para a tela, exigindo apenas que o frontend saiba organizá-los de modo limpo e rápido.
