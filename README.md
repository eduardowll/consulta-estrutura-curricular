# Trama · Consulta de estrutura curricular

Interface web para explorar matrizes curriculares e comparar consultas em PostgreSQL, MongoDB e Neo4j. O frontend usa HTML, CSS e JavaScript, servido pela própria API FastAPI: não precisa de Node, npm ou build.

## Resumo do trabalho

O projeto recebe estruturas curriculares em JSON e grava os mesmos dados em três modelos: relacional (PostgreSQL), documental (MongoDB) e grafo (Neo4j). A API oferece uma consulta única para pesquisar disciplinas, filtros e cadeias de pré-requisitos; a interface permite navegar por esses dados e comparar o tempo e a equivalência das respostas dos três bancos.

## Diagrama Lógico

Visão geral da arquitetura de dados e esquema lógico nos três bancos utilizados (PostgreSQL, Neo4J e MongoDB) e processo de ETL:

<img width="1408" height="768" alt="Modelo Lógico dos bancos" src="https://github.com/user-attachments/assets/ee2ee6df-837e-4d61-b261-9bba8d1ebcd6" />

## Teste rápido

Com Docker Desktop aberto e o ambiente virtual já instalado:

```powershell
.\start.ps1
