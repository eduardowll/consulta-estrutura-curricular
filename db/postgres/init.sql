-- Modelo relacional (3FN) da estrutura curricular.
-- Idempotente (IF NOT EXISTS): roda no primeiro `docker compose up` (pasta de init do
-- container) e também é reaplicado por etl/load_postgres.py.
--
-- Ideias do modelo:
--   * curso 1:N estrutura_curricular (um curso tem várias versões: 2015, 2019...)
--   * componente = identidade da disciplina no curso (curso + código), igual entre anos
--   * estrutura_componente = atributos da disciplina NAQUELA estrutura (nome, carga, natureza...)
--   * relacao_componente = N:N auto-referenciada POR estrutura: os pré-requisitos mudam
--     de um ano para outro (ex.: TAD0029 em 2015 x 2019).
--   * Para outro curso basta inserir outro `curso`: nada mais muda no esquema.

CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- busca por nome parcial com índice

CREATE TABLE IF NOT EXISTS curso (
    id          SERIAL PRIMARY KEY,
    sigla       TEXT NOT NULL UNIQUE,
    nome        TEXT NOT NULL,
    instituicao TEXT
);

CREATE TABLE IF NOT EXISTS estrutura_curricular (
    id       SERIAL PRIMARY KEY,
    curso_id INT  NOT NULL REFERENCES curso (id) ON DELETE CASCADE,
    ano      INT  NOT NULL,
    fonte    TEXT,
    UNIQUE (curso_id, ano)
);

CREATE TABLE IF NOT EXISTS componente (
    id       SERIAL PRIMARY KEY,
    curso_id INT  NOT NULL REFERENCES curso (id) ON DELETE CASCADE,
    codigo   TEXT NOT NULL,
    UNIQUE (curso_id, codigo)
);

CREATE TABLE IF NOT EXISTS estrutura_componente (
    estrutura_id  INT  NOT NULL REFERENCES estrutura_curricular (id) ON DELETE CASCADE,
    componente_id INT  NOT NULL REFERENCES componente (id)           ON DELETE CASCADE,
    nome          TEXT NOT NULL,
    carga         INT,
    unidade_carga TEXT,
    natureza      TEXT NOT NULL
        CHECK (natureza IN ('obrigatoria', 'optativa', 'atividade_complementar', 'outra')),
    periodo       INT,
    PRIMARY KEY (estrutura_id, componente_id)
);

-- origem é pré-requisito de destino. tipo: PRE (pré-requisito), CO (co-requisito),
-- EQUIV (equivalência). logica: E (todas as setas contínuas) ou OU (alternativas).
CREATE TABLE IF NOT EXISTS relacao_componente (
    estrutura_id INT  NOT NULL,
    origem_id    INT  NOT NULL,
    destino_id   INT  NOT NULL,
    tipo         TEXT NOT NULL DEFAULT 'PRE' CHECK (tipo IN ('PRE', 'CO', 'EQUIV')),
    logica       TEXT NOT NULL DEFAULT 'E'   CHECK (logica IN ('E', 'OU')),
    PRIMARY KEY (estrutura_id, origem_id, destino_id, tipo),
    CHECK (origem_id <> destino_id),
    -- as duas pontas precisam pertencer à MESMA estrutura
    FOREIGN KEY (estrutura_id, origem_id)
        REFERENCES estrutura_componente (estrutura_id, componente_id) ON DELETE CASCADE,
    FOREIGN KEY (estrutura_id, destino_id)
        REFERENCES estrutura_componente (estrutura_id, componente_id) ON DELETE CASCADE
);

-- Índices das consultas: descer (pré-requisitos de X) e subir (o que X libera)
CREATE INDEX IF NOT EXISTS idx_rel_destino ON relacao_componente (estrutura_id, destino_id);
CREATE INDEX IF NOT EXISTS idx_rel_origem  ON relacao_componente (estrutura_id, origem_id);
CREATE INDEX IF NOT EXISTS idx_ec_nome_trgm
    ON estrutura_componente USING gin (nome gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_ec_natureza ON estrutura_componente (estrutura_id, natureza);