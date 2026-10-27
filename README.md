# Pulse API

API REST para cadastrar serviços, verificar seus endereços HTTP e guardar o último resultado em SQLite.

## Recursos

- Cadastro, listagem, consulta e remoção de monitores.
- Verificação HTTP assíncrona com timeout de cinco segundos.
- Persistência local em SQLite.
- Documentação interativa gerada pelo FastAPI.
- Respostas com código HTTP, latência e horário da última verificação.

## Requisitos

- Python 3.12 ou superior.

## Executar localmente

No PowerShell:

    py -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    uvicorn app.main:app --reload

Abra http://127.0.0.1:8000/docs para explorar os endpoints.

## Rotas principais

| Método | Rota | Ação |
| --- | --- | --- |
| GET | /health | Estado da API |
| GET | /api/v1/monitors | Lista monitores |
| POST | /api/v1/monitors | Cadastra um monitor |
| GET | /api/v1/monitors/{id} | Consulta um monitor |
| POST | /api/v1/monitors/{id}/check | Verifica o endereço cadastrado |
| DELETE | /api/v1/monitors/{id} | Remove um monitor |

Exemplo de corpo para criar um monitor:

    {
      "name": "Meu site",
      "url": "https://example.com"
    }

O banco é criado em data/pulse.db na primeira inicialização. Para escolher outro local, defina a variável de ambiente PULSE_DB_PATH.

## Próximos passos

- Adicionar autenticação e controle de acesso.
- Criar verificações agendadas em segundo plano.
- Registrar o histórico completo e calcular disponibilidade.
- Separar persistência e lógica de negócio em módulos.

## Tecnologias

Python · FastAPI · Pydantic · HTTPX · SQLite
