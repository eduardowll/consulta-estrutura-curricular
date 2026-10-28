# Trama · Consulta de estrutura curricular

Interface web para explorar matrizes curriculares e comparar consultas em PostgreSQL, MongoDB e Neo4j. O frontend usa HTML, CSS e JavaScript, servido pela própria API FastAPI: não precisa de Node, npm ou build.

## Resumo do trabalho

O projeto recebe estruturas curriculares em JSON e grava os mesmos dados em três modelos: relacional (PostgreSQL), documental (MongoDB) e grafo (Neo4j). A API oferece uma consulta única para pesquisar disciplinas, filtros e cadeias de pré-requisitos; a interface permite navegar por esses dados e comparar o tempo e a equivalência das respostas dos três bancos.

## Teste rápido

Com Docker Desktop aberto e o ambiente virtual já instalado:

```powershell
.\start.ps1
```

Abra **http://127.0.0.1:8000** e faça este roteiro:

1. Pesquise `programacao` e confirme que aparecem disciplinas com e sem acento.
2. Alterne a matriz entre 2015 e 2019 e abra uma disciplina para ver suas conexões.
3. Selecione PostgreSQL, MongoDB e Neo4j no campo **Consultar em**.
4. Abra **Comparar consultas** e confirme que a tela informa resultados iguais.
5. Use **Exportar CSV** para baixar a lista filtrada.

Para conferir o código automaticamente, execute:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
$env:RUN_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

O segundo comando usa os três bancos; eles precisam estar iniciados e carregados.

## Iniciar no Windows

Requisitos: Docker Desktop com containers Linux e Python 3.12 (versão usada na validação).

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env  # apenas se ainda não existir um .env
.\start.ps1 -LoadData
```

Abra **http://127.0.0.1:8000**. A documentação da API está em **http://127.0.0.1:8000/docs**.

Nas próximas vezes, basta ` .\start.ps1 `. A opção `-LoadData` importa novamente as matrizes de exemplo e substitui os dados desses cursos/anos. Para outra porta HTTP: ` .\start.ps1 -Port 8001 `.

O `.env.example` usa a porta **55432** para o PostgreSQL, evitando conflito com instalações locais na porta 5432. Docker Compose e os loaders leem o mesmo `.env`. Reinicie a API depois de alterar a configuração ou recuperar um banco que estava indisponível na inicialização.

Para executar manualmente (ou em outro sistema):

```sh
docker compose up -d --wait
python etl/load_postgres.py data/processed/tads_2015.json data/processed/tads_2019.json
python etl/load_mongo.py data/processed/tads_2015.json data/processed/tads_2019.json
python etl/load_neo4j.py data/processed/tads_2015.json data/processed/tads_2019.json
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Use o Python do ambiente virtual nesses comandos. `Ctrl+C` encerra a API; `docker compose stop` para os bancos, preservando os volumes.

## Interface

- Seleção de curso, ano da matriz e banco consultado.
- Busca instantânea por nome ou código, ignorando acentos e maiúsculas; filtros de natureza e ordenação.
- Detalhes com carga, unidade original, período e cadeias de pré-requisitos/dependentes. Conexões são navegáveis.
- Comparação dos três bancos, com tempo real de cada consulta e verificação de igualdade dos resultados.
- Exportação CSV dos resultados filtrados, compatível com acentos e protegido contra fórmulas injetadas nas células.
- Importação de JSON com prévia e confirmação de substituição, seguida de validação no servidor.
- Layout responsivo, navegação por teclado, atalho `/` para buscar, estados vazios e mensagens de erro.

As fontes DM Sans e Manrope são carregadas do Google Fonts; há alternativas locais se a rede não estiver disponível. Os dados da API continuam locais.

## Dados e limites

O projeto inclui TADS/UFRN: **34 componentes e 17 relações em 2015**, **37 componentes e 18 relações em 2019**. Os JSONs não informam o período; por isso a interface exibe “Não informado”. Cargas em créditos e horas permanecem nas suas unidades, sem conversões presumidas.

“OPTATIVAS” e “ATIVIDADES_COMPLEMENTARES” são blocos agregados na fonte, não uma lista individual de todas as disciplinas optativas. As grafias dos dados são preservadas; a interface só ajusta a capitalização para leitura.

A cadeia mostra dependências estruturais, não uma decisão de elegibilidade para matrícula. Alternativas OU, correquisitos e equivalências aparecem nas condições da disciplina. O comparador mede uma execução sequencial, sujeito a cache e carga; não é um benchmark controlado.

A importação substitui a matriz por curso/ano. PostgreSQL usa transação e pool de conexões; Neo4j usa transação de escrita. **Não há transação distribuída entre os três bancos**, e a substituição no MongoDB standalone não é atômica. Uma falha informa os bancos já atualizados; após corrigir a conexão, reimporte o JSON para reconciliar os dados. Evite importações simultâneas da mesma matriz.

O aplicativo é destinado a uso local. Não há autenticação no endpoint de importação; o servidor de início escuta apenas em `127.0.0.1`.

## Verificação

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Integração: bancos iniciados e dados de exemplo carregados
$env:RUN_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

A suíte contém 11 testes, sendo quatro de integração. Ela verifica:

- JSONs inválidos, duplicidades, referências ausentes e ciclos;
- rotas, parâmetros inválidos, arquivos do frontend e indisponibilidade dos bancos;
- preservação dos resultados individuais no modo `db=all`;
- igualdade das duas matrizes e das **71 cadeias completas** nos três bancos;
- busca com/sem acento, caracteres literais e filtros combinados;
- cadastro/reimportação de curso temporário, tipos de relações e cadeia com 12 níveis;
- rollback de importação com falha e consultas concorrentes no PostgreSQL.

Os testes de integração criam um curso com identificador exclusivo e removem apenas esse curso ao final.

## Organização

- `backend/`: API, conexões e repositórios dos três bancos.
- `frontend/`: interface, estilos e interações sem framework.
- `etl/`: validação, normalização e carga de JSONs.
- `data/processed/`: matrizes canônicas que alimentam os bancos.
- `db/postgres/init.sql`: esquema relacional.
- `tests/`: testes unitários e de integração.

O endpoint `GET /api/status` informa a disponibilidade verificada **na inicialização**. `db=all` retorna `results_by_database`, `results_match` e os tempos; o campo `data` mantém o resultado do PostgreSQL como referência.
