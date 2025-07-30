import os
import uvicorn
from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import requests
from io import BytesIO
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app = FastAPI()

# Habilitar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar arquivos estáticos para permitir acesso a HTML e outros recursos
app.mount("/static", StaticFiles(directory="."), name="static")

HTML_PATH = Path(__file__).resolve().parent / "index_amigavel.html"

@app.get("/", response_class=HTMLResponse)
def home_page():
    if HTML_PATH.exists():
        return HTML_PATH.read_text(encoding="utf-8")
    return "<h2>Interface não encontrada no servidor</h2>"

@app.post("/upload_excel/")
async def upload_excel(file: UploadFile):
    try:
        df = pd.read_excel(file.file)

        # Buscar série Selic anualizada (% a.a.)
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados?formato=json"
        data = requests.get(url, timeout=10).json()
        selic = pd.DataFrame(data)

        # Conversão de data
        selic['data'] = pd.to_datetime(selic['data'], format='%d/%m/%Y')

        # Opcional: filtrar apenas anos recentes
        selic = selic[selic['data'] >= '2020-01-01']

        # Agrupar por mês
        selic['ano_mes'] = selic['data'].dt.to_period('M')
        selic_mes = selic.groupby('ano_mes').last().reset_index()

        # Criar coluna ano-mês no arquivo Excel
        df['ano_mes'] = df['Data'].dt.to_period('M')

        # Merge com a taxa correta
        df_merged = df.merge(selic_mes, left_on='ano_mes', right_on='ano_mes', how='left')
        df_merged = df_merged.rename(columns={'valor': 'Taxa Selic Anual (%)'})

        # ============================
        # Calcular taxa mensal composta
        # ============================
        taxa_anual = df_merged['Taxa Selic Anual (%)'] / 100
        taxa_mensal = (1 + taxa_anual) ** (1 / 12) - 1

        # Calcular valor atualizado
        df_merged['Valor Atualizado'] = df_merged['Valor Inicial'] * (1 + taxa_mensal)

        # Formatar resultado
        df_merged['Valor Atualizado'] = df_merged['Valor Atualizado'].round(2)
        df_merged['Taxa Selic Anual (%)'] = df_merged['Taxa Selic Anual (%)'].round(2)

        # Exportar Excel
        output = BytesIO()
        df_merged[['Data', 'Valor Inicial', 'Taxa Selic Anual (%)', 'Valor Atualizado']].to_excel(output, index=False)
        output.seek(0)
        return StreamingResponse(output,
                                 media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                 headers={"Content-Disposition": "attachment; filename=result_selic.xlsx"})
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)