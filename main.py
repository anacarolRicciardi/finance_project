import os
import uvicorn
from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import requests
from io import BytesIO
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Habilitar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar arquivos estáticos para permitir acesso a recursos locais
app.mount("/static", StaticFiles(directory="."), name="static")

# ============================
#  Página inicial (HTML)
# ============================
from pathlib import Path
HTML_PATH = Path(__file__).resolve().parent / "index_amigavel.html"

@app.get("/", response_class=HTMLResponse)
def home_page():
    if HTML_PATH.exists():
        return HTML_PATH.read_text(encoding="utf-8")
    return "<h2>Interface não encontrada no servidor</h2>"

# ============================
#  Upload do Excel e cálculo Selic
# ============================
@app.post("/upload_excel/")
async def upload_excel(file: UploadFile):
    try:
        df = pd.read_excel(file.file)

        # Buscar série Selic do Bacen
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados?formato=json"
        data = requests.get(url, timeout=10).json()
        selic = pd.DataFrame(data)
        selic['data'] = pd.to_datetime(selic['data'], format='%d/%m/%Y')
        selic['valor'] = selic['valor'].str.replace(',', '.').astype(float)

        # Validar colunas
        if 'Data' not in df.columns or 'Valor Inicial' not in df.columns:
            return {"error": "O arquivo Excel deve conter as colunas: Data e Valor Inicial"}

        # Processar datas e mesclar com Selic
        df['Data'] = pd.to_datetime(df['Data'], dayfirst=True)
        df_merged = df.merge(selic, left_on=df['Data'].dt.to_period('M'),
                             right_on=selic['data'].dt.to_period('M'), how='left')
        df_merged = df_merged.rename(columns={'valor': 'Taxa Selic (%)'})

        # Calcular valor atualizado
        df_merged['Valor Atualizado'] = df_merged['Valor Inicial'] * (1 + df_merged['Taxa Selic (%)'] / 100)

        # Exportar Excel
        output = BytesIO()
        df_merged[['Data', 'Valor Inicial', 'Taxa Selic (%)', 'Valor Atualizado']].to_excel(output, index=False)
        output.seek(0)
        return StreamingResponse(output,
                                 media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                 headers={"Content-Disposition": "attachment; filename=result_selic.xlsx"})
    except Exception as e:
        return {"error": str(e)}

# ============================
#  Inicialização no Render
# ============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
